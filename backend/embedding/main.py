import json
import boto3
import base64
from datetime import datetime
import uuid
import os
import time
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

# 初始化客户端
s3_client = boto3.client('s3')
bedrock_client = boto3.client('bedrock-runtime')

# 配置
OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT')
OPENSEARCH_INDEX = os.environ.get('OPENSEARCH_INDEX', 'embeddings')
TITAN_MODEL_ID = 'amazon.titan-embed-image-v1'
MARENG0_MODEL_ID = 'twelvelabs.marengo-embed-2-7-v1:0'
VECTOR_DIMENSION = 1024

def handler(event, context):
    """
    S3触发的Embedding处理Lambda
    """
    try:
        # 初始化OpenSearch客户端
        opensearch_client = get_opensearch_client()
        create_index_if_not_exists(opensearch_client)
        
        # 解析S3事件
        for record in event['Records']:
            bucket_name = record['s3']['bucket']['name']
            object_key = record['s3']['object']['key']
            s3_uri = f"s3://{bucket_name}/{object_key}"
            
            print(f"Processing file: {s3_uri}")
            
            # 跳过Bedrock输出文件
            if 'bedrock-outputs/' in object_key or 'temp/' in object_key:
                print(f"Skipping Bedrock output or temp file: {object_key}")
                continue
            
            # 判断文件类型
            file_ext = object_key.split('.')[-1].lower()
            
            if file_ext in ['png', 'jpeg', 'jpg', 'webp']:
                # 图片文件 - 使用Marengo模型
                embedding = get_embedding_from_marengo('image', s3_uri, bucket_name)
                store_embedding(opensearch_client, s3_uri, embedding, file_ext)
            elif file_ext in ['mp4', 'mov']:
                # 视频文件 - 使用Marengo模型
                embedding = get_embedding_from_marengo('video', s3_uri, bucket_name)
                store_embedding(opensearch_client, s3_uri, embedding, file_ext)
            elif file_ext in ['wav', 'mp3', 'm4a']:
                # 音频文件 - 使用Marengo模型的audio功能
                embedding = get_embedding_from_marengo('audio', s3_uri, bucket_name)
                store_embedding(opensearch_client, s3_uri, embedding, file_ext)
            else:
                print(f"Unsupported file type: {file_ext}")
                continue
            
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Embedding processing completed'})
        }
        
    except Exception as e:
        print(f"Error processing embedding: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def get_opensearch_client():
    """初始化OpenSearch客户端"""
    if not OPENSEARCH_ENDPOINT:
        raise ValueError("OPENSEARCH_ENDPOINT environment variable not set")
    
    # 提取主机名（移除所有https://前缀）
    host = OPENSEARCH_ENDPOINT.replace("https://", "").replace("https://", "")
    region = os.environ.get('AWS_REGION', 'us-east-1')
    
    # 创建AWS签名认证
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, region, 'aoss')
    
    # 创建OpenSearch客户端
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20
    )
    return client

def create_index_if_not_exists(client):
    """创建索引（如果不存在）"""
    if not client.indices.exists(OPENSEARCH_INDEX):
        index_body = {
            'settings': {
                'index': {
                    'knn': True
                }
            },
            'mappings': {
                'properties': {
                    'visual_embedding': {
                        'type': 'knn_vector',
                        'dimension': VECTOR_DIMENSION
                    },
                    'text_embedding': {
                        'type': 'knn_vector',
                        'dimension': VECTOR_DIMENSION
                    },
                    'audio_embedding': {
                        'type': 'knn_vector',
                        'dimension': VECTOR_DIMENSION
                    },
                    's3_uri': {'type': 'keyword'},
                    'file_type': {'type': 'keyword'},
                    'timestamp': {'type': 'date'}
                }
            }
        }
        client.indices.create(OPENSEARCH_INDEX, body=index_body)
        print(f"Created index: {OPENSEARCH_INDEX}")

def get_embedding_from_marengo(media_type, s3_uri, bucket_name):
    """
    使用 Twelvelabs Marengo 模型获取嵌入向量
    """
    try:
        # 获取账户ID作为bucket owner
        sts_client = boto3.client('sts')
        account_id = sts_client.get_caller_identity()['Account']
        
        # 为输出结果生成一个唯一的S3路径
        output_key = f"bedrock-outputs/{uuid.uuid4()}/result.json"
        output_s3_uri = f"s3://{bucket_name}/{output_key}"
        
        print(f"media_type: {media_type}, s3_uri: {s3_uri}")
        
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
            
        # 构建输出数据配置
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
        max_attempts = 60  # 最多等待5分钟
        attempt = 0
        
        while attempt < max_attempts:
            try:
                res = bedrock_client.get_async_invoke(invocationArn=invocation_arn)
                print(f"Status (attempt {attempt + 1}): {res['status']}")
                
                if res["status"] == "Completed":
                    # 从实际输出路径读取结果
                    if "outputDataConfig" in res and "s3OutputDataConfig" in res["outputDataConfig"]:
                        actual_output_s3_uri = res["outputDataConfig"]["s3OutputDataConfig"]["s3Uri"]
                        print(f"Using actual output S3 URI: {actual_output_s3_uri}")

                        alt_bucket, alt_prefix = extract_s3_uri(actual_output_s3_uri)
                        output_key = alt_prefix + "/output.json" if alt_prefix else "output.json"

                        try:
                            output_resp = s3_client.get_object(Bucket=alt_bucket, Key=output_key)
                            output_json = json.loads(output_resp["Body"].read().decode("utf-8"))
                            print("output_json", output_json)
                            # 处理视频的多个embedding
                            if media_type == "video":
                                embeddings = {}
                                for item in output_json["data"]:
                                    if item["embeddingOption"] == "visual-image":
                                        embeddings["visualImageEmbedding"] = item["embedding"]
                                    elif item["embeddingOption"] == "visual-text":
                                        embeddings["visualTextEmbedding"] = item["embedding"]
                                    elif item["embeddingOption"] == "audio":
                                        embeddings["audioEmbedding"] = item["embedding"]
                                return embeddings
                            elif media_type == "audio":
                                # 音频文件只有audio embedding
                                return {"audioEmbedding": output_json["data"][0]["embedding"]}
                            else:
                                # 图片只有一个embedding
                                return output_json["data"][0]
                        except Exception as s3_error:
                            print(f"Failed to read output.json from path: {output_key}")
                            raise s3_error
                        
                elif res["status"] in ("Failed", "Cancelled"):
                    error_msg = res.get("failureMessage", "Unknown error")
                    raise ValueError(f"Async invoke failed: {error_msg}")
                    
                # 等待5秒后重试
                time.sleep(5)
                attempt += 1
                
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise e
                print(f"Error checking status (attempt {attempt + 1}): {str(e)}")
                time.sleep(5)
                attempt += 1
            
        raise TimeoutError("Async invoke timed out after maximum attempts")
            
    except Exception as e:
        print(f"Error in get_embedding_from_marengo: {str(e)}")
        raise e

def extract_s3_uri(s3_uri):
    """
    从S3 URI中提取bucket和prefix
    """
    if not s3_uri.startswith('s3://'):
        raise ValueError(f"Invalid S3 URI: {s3_uri}")
    
    path = s3_uri[5:]  # 移除 's3://'
    parts = path.split('/', 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ''
    
    return bucket, prefix

def store_embedding(client, s3_uri, embedding_data, file_type):
    """
    存储embedding到OpenSearch（统一向量空间）
    """
    document = {
        's3_uri': s3_uri,
        'file_type': file_type,
        'timestamp': datetime.now().isoformat()
    }
    
    # 根据embedding数据结构存储
    if 'embedding' in embedding_data:
        # 图片只有一个视觉embedding
        document['visual_embedding'] = embedding_data['embedding']
    else:
        # 视频或音频有多种embedding类型
        if 'visualImageEmbedding' in embedding_data:
            document['visual_embedding'] = embedding_data['visualImageEmbedding']
        if 'visualTextEmbedding' in embedding_data:
            document['text_embedding'] = embedding_data['visualTextEmbedding']
        if 'audioEmbedding' in embedding_data:
            document['audio_embedding'] = embedding_data['audioEmbedding']
    
    response = client.index(
        index=OPENSEARCH_INDEX,
        body=document
    )
    
    print(f"Stored embeddings for {s3_uri}: {response}")
    return response