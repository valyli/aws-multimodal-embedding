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
                store_embedding(opensearch_client, 'image', s3_uri, embedding, file_ext)
            elif file_ext in ['mp4', 'mov']:
                # 视频文件 - 使用Marengo模型
                embedding = get_embedding_from_marengo('video', s3_uri, bucket_name)
                store_embedding(opensearch_client, 'video', s3_uri, embedding, file_ext)
            elif file_ext in ['wav', 'mp3', 'm4a']:
                # 音频文件 - 使用Marengo模型的audio功能
                embedding = get_embedding_from_marengo('audio', s3_uri, bucket_name)
                store_embedding(opensearch_client, 'audio', s3_uri, embedding, file_ext)
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
                    'knn': True,
                    "mapping.total_fields.limit": 5000
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
                    'media_type': {'type': 'keyword'},
                    'file_type': {'type': 'keyword'},
                    'timestamp': {'type': 'date'},
                    'segment_index': {'type': 'integer'},
                    'start_time': {'type': 'float'},
                    'end_time': {'type': 'float'},
                    'duration': {'type': 'float'}
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
                            # 处理不同媒体类型的embedding
                            if media_type == "video":
                                # 视频文件：返回所有时间段的embedding数据
                                return output_json["data"]
                            elif media_type == "audio":
                                # 音频文件：返回所有时间段的embedding数据
                                return output_json["data"]
                            elif media_type == "image":
                                # 图片文件：只有一个embedding
                                return output_json["data"]
                            elif media_type == "text":
                                # 文本：只有一个embedding
                                return output_json["data"]
                            return output_json["data"]
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

def store_embedding(client, media_type, s3_uri, embedding_data, file_type):
    """
    存储embedding到OpenSearch（支持多时间段）
    """
    responses = []
    
    # 处理多个时间段的embedding数据
    for i, item in enumerate(embedding_data):
        document = {
            's3_uri': s3_uri,
            'media_type': media_type,
            'file_type': file_type,
            'timestamp': datetime.now().isoformat(),
            'segment_index': i,  # 添加段落索引
        }
        
        # 添加时间信息（如果有）
        if 'startSec' in item and item['startSec'] is not None:
            document['start_time'] = item['startSec']
        if 'endSec' in item and item['endSec'] is not None:
            document['end_time'] = item['endSec']
            # 计算duration
            if 'startSec' in item and item['startSec'] is not None:
                document['duration'] = item['endSec'] - item['startSec']
            
        # 根据媒体类型和embeddingOption存储对应的embedding
        if media_type == "video":
            embedding_option = item.get('embeddingOption')
            if embedding_option == 'visual-image':
                document['visual_embedding'] = item['embedding']
            elif embedding_option == 'visual-text':
                document['text_embedding'] = item['embedding']
            elif embedding_option == 'audio':
                document['audio_embedding'] = item['embedding']
        elif media_type == "audio":
            document['audio_embedding'] = item['embedding']
        elif media_type == "image":
            document['visual_embedding'] = item['embedding']
        elif media_type == "text":
            document['text_embedding'] = item['embedding']
        
        # 存储到OpenSearch
        response = client.index(
            index=OPENSEARCH_INDEX,
            body=document
        )
        responses.append(response)
        
        print(f"Stored embedding segment {i} for {s3_uri} (option: {item.get('embeddingOption', 'N/A')})")
    
    print(f"Stored {len(responses)} embedding segments for {s3_uri}")
    return responses