import json
import boto3
import base64
from datetime import datetime
import uuid
import os
import time
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

# 初始化客户端
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')
bedrock_client = boto3.client('bedrock-runtime')

# 配置
SEARCH_TABLE_NAME = os.environ.get('SEARCH_TABLE_NAME')
OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT')
OPENSEARCH_INDEX = os.environ.get('OPENSEARCH_INDEX', 'embeddings')
UPLOAD_BUCKET = os.environ.get('UPLOAD_BUCKET', 'multimodal-usw2-uploads')
MARENG0_MODEL_ID = 'twelvelabs.marengo-embed-2-7-v1:0'

def handler(event, context):
    """
    搜索处理Worker - 异步处理搜索任务
    """
    try:
        # 处理SQS消息
        for record in event['Records']:
            message_body = json.loads(record['body'])
            search_id = message_body['search_id']
            
            print(f"Processing search task: {search_id}")
            
            # 更新状态为处理中
            update_search_status(search_id, 'processing')
            
            try:
                # 执行搜索
                results = process_search(message_body)
                
                # 更新状态为完成
                update_search_status(search_id, 'completed', results=results)
                
            except Exception as e:
                print(f"Error processing search {search_id}: {str(e)}")
                update_search_status(search_id, 'failed', error=str(e))
                
        return {'statusCode': 200}
        
    except Exception as e:
        print(f"Error in worker: {str(e)}")
        return {'statusCode': 500}

def process_search(message):
    """处理搜索任务"""
    search_id = message['search_id']
    search_type = message.get('search_type', 'file')  # 'file' 或 'text'
    search_mode = message.get('search_mode', 'visual-image')  # 搜索模式
    
    print(f"Processing search: type={search_type}, mode={search_mode}")
    
    if search_type == 'text':
        # 文本搜索
        query_text = message['query_text']
        query_embedding = get_text_embedding_from_marengo(query_text)
        embedding_field = 'text_embedding'
        search_media_type = 'text'
    else:
        # 文件搜索
        file_name = message['file_name']
        file_type = message['file_type']
        s3_key = message['s3_key']
        
        # 判断媒体类型
        file_ext = file_name.split('.')[-1].lower()
        if file_ext in ['png', 'jpeg', 'jpg', 'webp']:
            media_type = 'image'
            search_media_type = 'image'
        elif file_ext in ['mp4', 'mov']:
            media_type = 'video'
            search_media_type = 'video'
        elif file_ext in ['wav', 'mp3', 'm4a']:
            media_type = 'audio'
            search_media_type = 'audio'
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")
        
        # 根据搜索模式选择正确的embedding字段
        if search_mode == 'audio':
            embedding_field = 'audio_embedding'
        elif search_mode == 'visual-text':
            embedding_field = 'text_embedding'
        else:  # visual-image 或其他
            embedding_field = 'visual_embedding'
        
        s3_uri = f"s3://{UPLOAD_BUCKET}/{s3_key}"
        # 使用用户选择的搜索模式
        query_embedding = get_embedding_from_marengo(media_type, s3_uri, UPLOAD_BUCKET, search_mode)
        
        # 清理临时文件
        try:
            s3_client.delete_object(Bucket=UPLOAD_BUCKET, Key=s3_key)
        except:
            pass
    
    # 在OpenSearch中搜索相似内容
    opensearch_client = get_opensearch_client()
    search_results = search_similar_embeddings(opensearch_client, query_embedding, embedding_field, search_media_type)
    
    return search_results

def get_text_embedding_from_marengo(text):
    """使用Marengo模型获取文本embedding（异步调用）"""
    try:
        # 获取账户ID
        sts_client = boto3.client('sts')
        account_id = sts_client.get_caller_identity()['Account']
        
        # 生成输出路径
        output_key = f"bedrock-outputs/{uuid.uuid4()}/result.json"
        output_s3_uri = f"s3://{UPLOAD_BUCKET}/{output_key}"
        
        # 文本输入
        model_input = {
            "inputType": "text",
            "inputText": text
        }
        
        # 输出配置
        output_data_config = {
            "s3OutputDataConfig": {
                "s3Uri": output_s3_uri
            }
        }
        
        print(f"Starting async text embedding for: {text[:50]}...")
        
        # 异步调用
        start_resp = bedrock_client.start_async_invoke(
            modelId=MARENG0_MODEL_ID,
            modelInput=model_input,
            outputDataConfig=output_data_config
        )
        
        invocation_arn = start_resp["invocationArn"]
        print("Text embedding invocation ARN:", invocation_arn)
        
        # 轮询结果
        max_attempts = 30  # 文本处理通常很快
        attempt = 0
        
        while attempt < max_attempts:
            try:
                res = bedrock_client.get_async_invoke(invocationArn=invocation_arn)
                print(f"Text embedding status (attempt {attempt + 1}): {res['status']}")
                
                if res["status"] == "Completed":
                    if "outputDataConfig" in res and "s3OutputDataConfig" in res["outputDataConfig"]:
                        actual_output_s3_uri = res["outputDataConfig"]["s3OutputDataConfig"]["s3Uri"]
                        alt_bucket, alt_prefix = extract_s3_uri(actual_output_s3_uri)
                        output_key = alt_prefix + "/output.json" if alt_prefix else "output.json"
                        
                        output_resp = s3_client.get_object(Bucket=alt_bucket, Key=output_key)
                        output_json = json.loads(output_resp["Body"].read().decode("utf-8"))
                        
                        return output_json['data'][0]['embedding']
                        
                elif res["status"] in ("Failed", "Cancelled"):
                    error_msg = res.get("failureMessage", "Unknown error")
                    raise ValueError(f"Text embedding async invoke failed: {error_msg}")
                    
                time.sleep(2)  # 文本处理较快，2秒间隔
                attempt += 1
                
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise e
                time.sleep(2)
                attempt += 1
        
        raise TimeoutError("Text embedding async invoke timed out")
        
    except Exception as e:
        print(f"Error in get_text_embedding_from_marengo: {str(e)}")
        raise e

def get_embedding_from_marengo(media_type, s3_uri, bucket_name, search_mode='visual-image'):
    """使用Marengo模型获取embedding"""
    try:
        # 获取账户ID
        sts_client = boto3.client('sts')
        account_id = sts_client.get_caller_identity()['Account']
        
        # 生成输出路径
        output_key = f"bedrock-outputs/{uuid.uuid4()}/result.json"
        output_s3_uri = f"s3://{bucket_name}/{output_key}"
        
        # 构建模型输入
        if media_type == "image":
            model_input = {
                "inputType": "image",
                "mediaSource": {
                    "s3Location": {
                        "uri": s3_uri,
                        "bucketOwner": account_id
                    }
                }
            }
        elif media_type == "video":
            model_input = {
                "inputType": "video",
                "mediaSource": {
                    "s3Location": {
                        "uri": s3_uri,
                        "bucketOwner": account_id
                    }
                }
                # 不指定embeddingTypes，获取所有可用的embedding类型
            }
        elif media_type == "audio":
            model_input = {
                "inputType": "audio",
                "mediaSource": {
                    "s3Location": {
                        "uri": s3_uri,
                        "bucketOwner": account_id
                    }
                }
            }
        else:
            raise ValueError(f"Unsupported media type: {media_type}")
            
        # 构建输出配置
        output_data_config = {
            "s3OutputDataConfig": {
                "s3Uri": output_s3_uri
            }
        }
        
        print(f"Starting async invoke with output to: {output_s3_uri}")
        
        # 发起异步调用
        start_resp = bedrock_client.start_async_invoke(
            modelId=MARENG0_MODEL_ID,
            modelInput=model_input,
            outputDataConfig=output_data_config
        )
            
        invocation_arn = start_resp["invocationArn"]
        print("Invocation ARN:", invocation_arn)
        
        # 轮询结果
        max_attempts = 60
        attempt = 0
        
        while attempt < max_attempts:
            try:
                res = bedrock_client.get_async_invoke(invocationArn=invocation_arn)
                print(f"Status (attempt {attempt + 1}): {res['status']}")
                
                if res["status"] == "Completed":
                    # 读取结果
                    if "outputDataConfig" in res and "s3OutputDataConfig" in res["outputDataConfig"]:
                        actual_output_s3_uri = res["outputDataConfig"]["s3OutputDataConfig"]["s3Uri"]
                        alt_bucket, alt_prefix = extract_s3_uri(actual_output_s3_uri)
                        output_key = alt_prefix + "/output.json" if alt_prefix else "output.json"

                        output_resp = s3_client.get_object(Bucket=alt_bucket, Key=output_key)
                        output_json = json.loads(output_resp["Body"].read().decode("utf-8"))
                        
                        # 根据搜索模式返回对应的embedding
                        if media_type == "audio":
                            # 音频文件直接返回embedding
                            return output_json["data"][0]['embedding']
                        elif media_type == "video":
                            # 视频文件根据搜索模式返回对应embedding
                            for item in output_json["data"]:
                                if search_mode == 'visual-image' and item.get("embeddingOption") == "visual-image":
                                    return item["embedding"]
                                elif search_mode == 'visual-text' and item.get("embeddingOption") == "visual-text":
                                    return item["embedding"]
                                elif search_mode == 'audio' and item.get("embeddingOption") == "audio":
                                    return item["embedding"]
                            # 如果没有找到对应模式，返回第一个
                            return output_json["data"][0]["embedding"]
                        else:
                            # 图片文件直接返回embedding
                            return output_json["data"][0]['embedding']
                        
                elif res["status"] in ("Failed", "Cancelled"):
                    error_msg = res.get("failureMessage", "Unknown error")
                    raise ValueError(f"Async invoke failed: {error_msg}")
                    
                time.sleep(5)
                attempt += 1
                
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise e
                time.sleep(5)
                attempt += 1
            
        raise TimeoutError("Async invoke timed out after maximum attempts")
            
    except Exception as e:
        print(f"Error in get_embedding_from_marengo: {str(e)}")
        raise e

def extract_s3_uri(s3_uri):
    """从S3 URI中提取bucket和prefix"""
    if not s3_uri.startswith('s3://'):
        raise ValueError(f"Invalid S3 URI: {s3_uri}")
    
    path = s3_uri[5:]
    parts = path.split('/', 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ''
    
    return bucket, prefix

def get_opensearch_client():
    """初始化OpenSearch客户端"""
    if not OPENSEARCH_ENDPOINT:
        raise ValueError("OPENSEARCH_ENDPOINT environment variable not set")
    
    host = OPENSEARCH_ENDPOINT.replace("https://", "")
    region = os.environ.get('AWS_REGION', 'us-east-1')
    
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, region, 'aoss')
    
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20
    )
    return client

def search_similar_embeddings(client, query_embedding, embedding_field, search_media_type='file', top_k=20):
    """在OpenSearch中搜索相似embedding - 智能跨模态搜索"""
    results = []
    embedding_types = ['visual_embedding', 'text_embedding', 'audio_embedding']
    
    # 根据搜索类型和目标媒体类型进行智能匹配
    search_embeddings = {embedding_field: query_embedding}
    
    for search_embedding_type, search_embedding in search_embeddings.items():
        if search_embedding is None:
            continue
            
        for target_embedding_type in embedding_types:
            can_search = False
            target_media_types = ["image", "text", "audio", "video"]
            
            # 实现智能跨模态匹配逻辑
            if search_media_type == "image":
                if search_embedding_type == 'visual_embedding':
                    if target_embedding_type == 'visual_embedding':
                        can_search = True
            elif search_media_type == "text":
                if search_embedding_type == 'text_embedding':
                    if target_embedding_type == 'text_embedding' or target_embedding_type == 'visual_embedding' or target_embedding_type == 'audio_embedding':
                        can_search = True
            elif search_media_type == "audio":
                if search_embedding_type == 'audio_embedding':
                    if target_embedding_type == 'audio_embedding':
                        can_search = True
            elif search_media_type == "video":
                if search_embedding_type == 'text_embedding':
                    if target_embedding_type == 'text_embedding':
                        can_search = True
                elif search_embedding_type == 'visual_embedding':
                    if target_embedding_type == 'visual_embedding':
                        can_search = True
                elif search_embedding_type == 'audio_embedding':
                    if target_embedding_type == 'audio_embedding':
                        can_search = True
            elif search_media_type == "file":
                # 文件搜索默认使用visual_embedding
                if search_embedding_type == 'visual_embedding':
                    if target_embedding_type == 'visual_embedding':
                        can_search = True
                        
            if not can_search:
                continue
                
            # 根据目标embedding类型设置文件类型过滤
            file_type_filter = []
            if target_embedding_type == 'visual_embedding':
                file_type_filter = ["png", "jpg", "jpeg", "webp", "mp4", "mov"]
            elif target_embedding_type == 'text_embedding':
                file_type_filter = ["mp4", "mov"]
            elif target_embedding_type == 'audio_embedding':
                file_type_filter = ["wav", "mp3", "m4a", "mp4", "mov"]
                
            search_body = {
                "size": top_k,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "knn": {
                                    target_embedding_type: {
                                        "vector": search_embedding,
                                        "k": top_k
                                    }
                                }
                            },
                            {
                                "terms": {
                                    "file_type": file_type_filter
                                }
                            }
                        ]
                    }
                },
                "_source": ["s3_uri", "file_type", "timestamp", "media_type"]
            }
            
            print(f"Searching for {search_embedding_type} with {target_embedding_type} in OpenSearch index: {OPENSEARCH_INDEX}")
            
            response = client.search(index=OPENSEARCH_INDEX, body=search_body)
            
            for hit in response['hits']['hits']:
                source = hit['_source']
                score = hit['_score']
                
                # 生成预签名URL
                s3_key = source['s3_uri'].replace(f's3://{UPLOAD_BUCKET}/', '')
                image_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': UPLOAD_BUCKET, 'Key': s3_key},
                    ExpiresIn=3600
                )
                
                results.append({
                    'id': hit['_id'],
                    'score': score,
                    'similarity_percentage': f"{(score * 100):.2f}%",
                    's3_uri': source['s3_uri'],
                    'search_media_type': search_media_type,
                    'search_embedding_type': search_embedding_type,
                    'target_embedding_type': target_embedding_type,
                    'media_type': source.get('media_type', 'unknown'),
                    'file_type': source['file_type'],
                    'timestamp': source['timestamp'],
                    'image_url': image_url
                })
    
    # 按分数排序并返回前top_k个结果
    results.sort(key=lambda x: x['score'], reverse=True)
    all_hits = results  # [:top_k]
    
    return [{
        'score': hit['score'],
        's3_uri': hit['s3_uri'],
        'file_type': hit['file_type'],
        'timestamp': hit['timestamp'],
        'image_url': hit['image_url'],
        'search_info': {
            'search_media_type': hit['search_media_type'],
            'search_embedding_type': hit['search_embedding_type'],
            'target_embedding_type': hit['target_embedding_type'],
            'target_media_type': hit['media_type']
        }
    } for hit in all_hits]

def update_search_status(search_id, status, results=None, error=None):
    """更新搜索任务状态"""
    try:
        table = dynamodb.Table(SEARCH_TABLE_NAME)
        
        update_expression = "SET #status = :status, updated_at = :updated_at"
        expression_attribute_names = {"#status": "status"}
        expression_attribute_values = {
            ":status": status,
            ":updated_at": datetime.now().isoformat()
        }
        
        if results is not None:
            update_expression += ", results = :results"
            expression_attribute_values[":results"] = json.dumps(results)
            
        if error is not None:
            update_expression += ", #error = :error"
            expression_attribute_names["#error"] = "error"
            expression_attribute_values[":error"] = error
        
        table.update_item(
            Key={'search_id': search_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )
        
        print(f"Updated search {search_id} status to {status}")
        
    except Exception as e:
        print(f"Error updating search status: {str(e)}")