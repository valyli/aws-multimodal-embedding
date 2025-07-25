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
UPLOAD_BUCKET = 'cloudscape-demo-uploads'
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
        embedding_field = 'text_embedding'  # 标记为文本搜索，在search_similar_embeddings中会分别处理
    else:
        # 文件搜索
        file_name = message['file_name']
        file_type = message['file_type']
        s3_key = message['s3_key']
        
        # 判断媒体类型
        file_ext = file_name.split('.')[-1].lower()
        if file_ext in ['png', 'jpeg', 'jpg', 'webp']:
            media_type = 'image'
        elif file_ext in ['mp4', 'mov']:
            media_type = 'video'
        elif file_ext in ['wav', 'mp3', 'm4a']:
            media_type = 'audio'
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")
        
        # 文件搜索统一使用visual_embedding
        embedding_field = 'visual_embedding'
        
        s3_uri = f"s3://{UPLOAD_BUCKET}/{s3_key}"
        # 文件搜索统一使用visual-image模式
        query_embedding = get_embedding_from_marengo(media_type, s3_uri, UPLOAD_BUCKET, 'visual-image')
        
        # 清理临时文件
        try:
            s3_client.delete_object(Bucket=UPLOAD_BUCKET, Key=s3_key)
        except:
            pass
    
    # 在OpenSearch中搜索相似内容
    opensearch_client = get_opensearch_client()
    search_results = search_similar_embeddings(opensearch_client, query_embedding, embedding_field)
    
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
                },
                "embeddingTypes": [search_mode]  # 根据搜索模式指定embedding类型
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
                        data = output_json["data"][0]
                        if media_type == "audio":
                            # 音频文件直接返回embedding
                            return data['embedding']
                        elif search_mode == 'visual-image' and 'visualImageEmbedding' in data:
                            return data['visualImageEmbedding']
                        elif search_mode == 'visual-text' and 'visualTextEmbedding' in data:
                            return data['visualTextEmbedding']
                        elif search_mode == 'audio' and 'audioEmbedding' in data:
                            return data['audioEmbedding']
                        elif 'embedding' in data:
                            return data['embedding']
                        else:
                            raise ValueError(f"No {search_mode} embedding found in output.json")
                        
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

def search_similar_embeddings(client, query_embedding, embedding_field, top_k=10):
    """在OpenSearch中搜索相似embedding"""
    # 如果是文本搜索，分别对图片和视频文件进行搜索
    if embedding_field == 'text_embedding':
        # 搜索图片文件：text的embedding 与 图片的visual_embedding 匹配
        image_search_body = {
            "size": top_k // 3,  # 分配三分之一给图片
            "query": {
                "bool": {
                    "must": [
                        {
                            "knn": {
                                "visual_embedding": {
                                    "vector": query_embedding,
                                    "k": top_k // 3
                                }
                            }
                        },
                        {
                            "terms": {
                                "file_type": ["png", "jpeg", "jpg", "webp"]
                            }
                        }
                    ]
                }
            },
            "_source": ["s3_uri", "file_type", "timestamp"]
        }
        
        # 搜索视频文件：text的embedding 与 视频的text_embedding 匹配
        video_search_body = {
            "size": top_k // 3,  # 分配三分之一给视频
            "query": {
                "bool": {
                    "must": [
                        {
                            "knn": {
                                "text_embedding": {
                                    "vector": query_embedding,
                                    "k": top_k // 3
                                }
                            }
                        },
                        {
                            "terms": {
                                "file_type": ["mp4", "mov"]
                            }
                        }
                    ]
                }
            },
            "_source": ["s3_uri", "file_type", "timestamp"]
        }
        
        # 搜索音频文件：text的embedding 与 音频的audio_embedding 匹配
        audio_search_body = {
            "size": top_k // 3,  # 分配三分之一给音频
            "query": {
                "bool": {
                    "must": [
                        {
                            "knn": {
                                "audio_embedding": {
                                    "vector": query_embedding,
                                    "k": top_k // 3
                                }
                            }
                        },
                        {
                            "terms": {
                                "file_type": ["wav", "mp3", "m4a"]
                            }
                        }
                    ]
                }
            },
            "_source": ["s3_uri", "file_type", "timestamp"]
        }
        
        # 执行三次搜索
        image_response = client.search(index=OPENSEARCH_INDEX, body=image_search_body)
        video_response = client.search(index=OPENSEARCH_INDEX, body=video_search_body)
        audio_response = client.search(index=OPENSEARCH_INDEX, body=audio_search_body)
        
        # 合并结果
        all_hits = []
        all_hits.extend(image_response['hits']['hits'])
        all_hits.extend(video_response['hits']['hits'])
        all_hits.extend(audio_response['hits']['hits'])
        
        # 按分数排序
        all_hits.sort(key=lambda x: x['_score'], reverse=True)
        
        # 取前top_k个结果
        all_hits = all_hits[:top_k]
        
    else:
        # 文件搜索：统一使用visual_embedding进行搜索
        search_body = {
            "size": top_k,
            "query": {
                "knn": {
                    "visual_embedding": {  # 文件搜索统一使用visual_embedding
                        "vector": query_embedding,
                        "k": top_k
                    }
                }
            },
            "_source": ["s3_uri", "file_type", "timestamp"]
        }
        
        response = client.search(index=OPENSEARCH_INDEX, body=search_body)
        all_hits = response['hits']['hits']
    
    # 处理结果
    results = []
    for hit in all_hits:
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
            'score': score,
            's3_uri': source['s3_uri'],
            'file_type': source['file_type'],
            'timestamp': source['timestamp'],
            'image_url': image_url
        })
    
    return results

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