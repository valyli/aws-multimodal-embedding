import json
import boto3
import base64
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
UPLOAD_BUCKET = 'cloudscape-demo-uploads'

def handler(event, context):
    """
    相似图片搜索API
    """
    try:
        # 解析请求体
        body = json.loads(event.get('body', '{}'))
        file_data = body.get('file')
        file_name = body.get('fileName')
        file_type = body.get('fileType')
        
        if not file_data or not file_name:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type'
                },
                'body': json.dumps({'error': 'Missing file data or filename'})
            }
        
        print(f"Processing search request for file: {file_name}")
        
        # 生成临时文件名
        ext = file_name.split('.')[-1].lower()
        temp_key = f"temp/{uuid.uuid4()}.{ext}"
        
        # 解码base64文件数据并上传到S3
        file_content = base64.b64decode(file_data)
        s3_client.put_object(
            Bucket=UPLOAD_BUCKET,
            Key=temp_key,
            Body=file_content,
            ContentType=file_type
        )
        
        print(f"Temporarily stored file: s3://{UPLOAD_BUCKET}/{temp_key}")
        
        # 生成查询图片的embedding
        query_embedding = generate_image_embedding(UPLOAD_BUCKET, temp_key)
        
        # 删除临时文件
        s3_client.delete_object(Bucket=UPLOAD_BUCKET, Key=temp_key)
        
        # 初始化OpenSearch客户端并搜索
        opensearch_client = get_opensearch_client()
        similar_images = search_similar_images(opensearch_client, query_embedding)
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            },
            'body': json.dumps({
                'message': 'Search completed successfully',
                'results': similar_images
            })
        }
        
    except Exception as e:
        print(f"Error in search: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            },
            'body': json.dumps({'error': str(e)})
        }

def get_opensearch_client():
    """初始化OpenSearch客户端"""
    if not OPENSEARCH_ENDPOINT:
        raise ValueError("OPENSEARCH_ENDPOINT environment variable not set")
    
    host = OPENSEARCH_ENDPOINT.replace("https://", "").replace("https://", "")
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

def search_similar_images(client, query_vector, top_k=5):
    """
    在OpenSearch中搜索相似图像
    """
    query = {
        "size": top_k,
        "query": {
            "knn": {
                "embedding_vector": {
                    "vector": query_vector,
                    "k": top_k
                }
            }
        }
    }
    
    response = client.search(
        body=query,
        index=OPENSEARCH_INDEX
    )
    
    results = []
    for hit in response['hits']['hits']:
        s3_uri = hit['_source']['s3_uri']
        # 解析S3 URI获取bucket和key
        bucket_name = s3_uri.split('/')[2]
        object_key = '/'.join(s3_uri.split('/')[3:])
        
        # 生成pre-signed URL，有效期60分钟
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': object_key},
            ExpiresIn=3600  # 60分钟
        )
        
        results.append({
            'score': hit['_score'],
            's3_uri': s3_uri,
            'file_type': hit['_source']['file_type'],
            'timestamp': hit['_source']['timestamp'],
            'image_url': presigned_url
        })
    
    return results