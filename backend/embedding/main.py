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
dynamodb = boto3.resource('dynamodb')

# DynamoDB表名
STATUS_TABLE_NAME = os.environ.get('STATUS_TABLE_NAME', 'multimodal-search-embedding-status')

# 配置
OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT')
OPENSEARCH_INDEX = os.environ.get('OPENSEARCH_INDEX', 'embeddings')
TITAN_MODEL_ID = 'amazon.titan-embed-image-v1'
MARENG0_MODEL_ID = 'twelvelabs.marengo-embed-2-7-v1:0'
VECTOR_DIMENSION = 1024

def handler(event, context):
    """
    SQS触发的Embedding处理Lambda
    """
    try:
        # 初始化OpenSearch客户端
        opensearch_client = get_opensearch_client()
        create_index_if_not_exists(opensearch_client)
        
        # 解析SQS消息中的S3事件
        print(f"Received {len(event['Records'])} SQS records")
        for sqs_record in event['Records']:
            print(f"Processing SQS record: {sqs_record.get('messageId', 'unknown')}")
            print(f"SQS attributes: {sqs_record.get('attributes', {})}")
            # SQS消息体包含S3事件
            s3_event = json.loads(sqs_record['body'])
            
            # 处理S3事件中的每个记录
            print(f"S3 event contains {len(s3_event['Records'])} records")
            for s3_record in s3_event['Records']:
                bucket_name = s3_record['s3']['bucket']['name']
                object_key = s3_record['s3']['object']['key']
                s3_uri = f"s3://{bucket_name}/{object_key}"
                
                print(f"Processing file from SQS: {s3_uri}")
                print(f"S3 event type: {s3_record.get('eventName', 'unknown')}")
                print(f"S3 event time: {s3_record.get('eventTime', 'unknown')}")
            
                # 跳过Bedrock输出文件
                if 'bedrock-outputs/' in object_key or 'temp/' in object_key:
                    print(f"SKIPPING Bedrock output or temp file: {object_key}")
                    continue
                
                print(f"File will be processed: {object_key}")
                
                # 更新状态为处理中
                update_embedding_status(s3_uri, 'processing', retry_count=int(sqs_record.get('attributes', {}).get('ApproximateReceiveCount', '1')))
                
                # 判断文件类型
                file_ext = object_key.split('.')[-1].lower()
                print(f"Detected file extension: {file_ext}")
                
                try:
                    if file_ext in ['png', 'jpeg', 'jpg', 'webp']:
                        # 图片文件 - 使用Marengo模型
                        print(f"Processing IMAGE file: {s3_uri}")
                        embedding = get_embedding_from_marengo('image', s3_uri, bucket_name)
                        store_embedding(opensearch_client, 'image', s3_uri, embedding, file_ext)
                    elif file_ext in ['mp4', 'mov']:
                        # 视频文件 - 使用Marengo模型
                        print(f"Processing VIDEO file: {s3_uri}")
                        embedding = get_embedding_from_marengo('video', s3_uri, bucket_name)
                        store_embedding(opensearch_client, 'video', s3_uri, embedding, file_ext)
                    elif file_ext in ['wav', 'mp3', 'm4a']:
                        # 音频文件 - 使用Marengo模型的audio功能
                        print(f"Processing AUDIO file: {s3_uri}")
                        embedding = get_embedding_from_marengo('audio', s3_uri, bucket_name)
                        store_embedding(opensearch_client, 'audio', s3_uri, embedding, file_ext)
                    else:
                        print(f"UNSUPPORTED file type: {file_ext} for {s3_uri}")
                        continue
                        
                    print(f"SUCCESS: Completed processing {s3_uri}")
                    # 更新状态为已完成
                    update_embedding_status(s3_uri, 'completed', clear_error=True)
                    
                except Exception as file_error:
                    error_msg = str(file_error)
                    retry_count = int(sqs_record.get('attributes', {}).get('ApproximateReceiveCount', '1'))
                    print(f"Error processing file {s3_uri}: {error_msg}")
                    print(f"SQS message attributes: {sqs_record.get('attributes', {})}")
                    print(f"Current retry count: {retry_count}")
                    
                    # 更新错误状态
                    update_embedding_status(s3_uri, 'retrying', retry_count=retry_count, error_msg=error_msg)
                    
                    # 检查是否是Quota限制错误
                    if any(keyword in error_msg.lower() for keyword in ['throttl', 'quota', 'limit', 'rate']):
                        print(f"QUOTA/RATE LIMIT detected for {s3_uri}, retry #{retry_count}. Will retry via SQS redrive policy.")
                        print(f"Error type: ThrottlingException - Will retry after delay")
                        # 对于quota错误，让SQS自动重试
                        raise file_error
                    else:
                        print(f"NON-QUOTA error for {s3_uri}, retry #{retry_count}: {error_msg}")
                        # 对于非quota错误，也让SQS重试，但记录更多信息
                        print(f"Error details: {type(file_error).__name__}: {error_msg}")
                        import traceback
                        print(f"Traceback: {traceback.format_exc()}")
                        raise file_error
            
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Embedding processing completed'})
        }
        
    except Exception as e:
        print(f"FATAL ERROR in embedding handler: {str(e)}")
        import traceback
        traceback.print_exc()
        print(f"Event that caused error: {json.dumps(event, default=str)}")
        # 对于handler级别的错误，也要抛出异常让SQS重试
        raise e

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

def update_embedding_status(s3_uri, status, retry_count=0, error_msg=None, clear_error=False):
    """
    更新embedding状态到DynamoDB
    """
    try:
        table = dynamodb.Table(STATUS_TABLE_NAME)
        
        # 使用s3_uri作为主键
        item = {
            's3_uri': s3_uri,
            'status': status,
            'retry_count': retry_count,
            'last_updated': datetime.now().isoformat()
        }
        
        if clear_error:
            item['last_error'] = None
            item['last_error_time'] = None
        elif error_msg:
            item['last_error'] = error_msg[:1000]  # 限制错误消息长度
            item['last_error_time'] = datetime.now().isoformat()
        
        table.put_item(Item=item)
        print(f"Updated status for {s3_uri}: {status} (retry: {retry_count})")
        
    except Exception as e:
        print(f"Failed to update status for {s3_uri}: {str(e)}")
        # 不抛出异常，避免影响主流程