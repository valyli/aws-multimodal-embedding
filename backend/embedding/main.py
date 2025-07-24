import json
import boto3
import base64
from datetime import datetime
import uuid
import os
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

# 初始化客户端
s3_client = boto3.client('s3')
bedrock_client = boto3.client('bedrock-runtime')

# 配置
OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT')
OPENSEARCH_INDEX = os.environ.get('OPENSEARCH_INDEX', 'embeddings')
BEDROCK_MODEL_ID = 'amazon.titan-embed-image-v1'
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
            
            # 判断文件类型
            file_ext = object_key.split('.')[-1].lower()
            
            if file_ext in ['png', 'jpeg', 'jpg', 'webp']:
                # 图片文件 - 使用Titan Multimodal Embeddings
                embedding = generate_image_embedding(bucket_name, object_key)
                store_embedding(opensearch_client, s3_uri, embedding, file_ext)
            elif file_ext in ['mp4', 'mov']:
                # 视频文件 - 生成占位符embedding
                embedding = generate_video_embedding()
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
                    'embedding_vector': {
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

def generate_image_embedding(bucket_name, object_key):
    """
    使用Bedrock Titan生成图片Embedding
    """
    # 从S3获取图片
    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    image_content = response['Body'].read()
    
    # 将图片转换为base64
    image_base64 = base64.b64encode(image_content).decode('utf-8')
    
    # 调用Bedrock API
    request_body = {
        "inputImage": image_base64,
        "embeddingConfig": {
            "outputEmbeddingLength": VECTOR_DIMENSION
        }
    }
    
    response = bedrock_client.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(request_body),
        contentType='application/json'
    )
    
    response_body = json.loads(response['body'].read())
    return response_body['embedding']

def generate_video_embedding():
    """
    视频文件处理 - 占位符embedding
    """
    import random
    return [random.random() for _ in range(VECTOR_DIMENSION)]

def store_embedding(client, s3_uri, embedding_vector, file_type):
    """
    存储向量到OpenSearch
    """
    document = {
        'embedding_vector': embedding_vector,
        's3_uri': s3_uri,
        'file_type': file_type,
        'timestamp': datetime.now().isoformat()
    }
    
    response = client.index(
        index=OPENSEARCH_INDEX,
        body=document
    )
    
    print(f"Stored embedding for {s3_uri}: {response}")
    return response