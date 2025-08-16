import json
import boto3
import base64
import uuid
import os
from datetime import datetime

s3_client = boto3.client('s3')
BUCKET_NAME = os.environ.get('UPLOAD_BUCKET', 'multimodal-search-uploads')
ALLOWED_TYPES = ['png', 'jpeg', 'jpg', 'webp', 'mp4', 'mov', 'wav', 'mp3', 'm4a']

def handler(event, context):
    """
    Lambda处理器
    """
    path = event.get('path', '/')
    method = event.get('httpMethod', 'GET')
    
    # 路由处理
    if path == '/' and method == 'GET':
        response_body = {
            "message": "Hello from multimodal-search!", 
            "status": "running",
            "bucket": BUCKET_NAME
        }
    elif path == '/health' and method == 'GET':
        response_body = {
            "status": "healthy", 
            "service": "multimodal-search"
        }
    elif path == '/api/data' and method == 'GET':
        response_body = {
            "data": [
                {"id": 1, "name": "Item 1", "status": "active"},
                {"id": 2, "name": "Item 2", "status": "inactive"},
            ],
            "total": 2
        }
    elif path == '/api/materials' and method == 'GET':
        try:
            # 获取S3中的所有文件
            s3_objects = s3_client.list_objects_v2(Bucket=BUCKET_NAME)
            materials = []
            
            if 'Contents' in s3_objects:
                # 初始化OpenSearch客户端
                from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
                import boto3
                
                opensearch_endpoint = os.environ.get('OPENSEARCH_ENDPOINT')
                if opensearch_endpoint:
                    host = opensearch_endpoint.replace('https://', '')
                    region = os.environ.get('AWS_REGION', 'us-east-1')
                    credentials = boto3.Session().get_credentials()
                    auth = AWSV4SignerAuth(credentials, region, 'aoss')
                    
                    opensearch_client = OpenSearch(
                        hosts=[{'host': host, 'port': 443}],
                        http_auth=auth,
                        use_ssl=True,
                        verify_certs=True,
                        connection_class=RequestsHttpConnection
                    )
                
                for obj in s3_objects['Contents']:
                    key = obj['Key']
                    if key.startswith('bedrock-outputs/') or key.startswith('temp/'):
                        continue
                        
                    # 生成预签名URL
                    file_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': BUCKET_NAME, 'Key': key},
                        ExpiresIn=3600
                    )
                    
                    # 检查OpenSearch中的embedding状态
                    embeddings = []
                    segment_count = 0
                    segment_counts = {'visual': 0, 'text': 0, 'audio': 0}
                    if opensearch_endpoint:
                        try:
                            s3_uri = f"s3://{BUCKET_NAME}/{key}"
                            search_result = opensearch_client.search(
                                index='embeddings',
                                body={
                                    'query': {'term': {'s3_uri': s3_uri}},
                                    'size': 100
                                }
                            )
                            
                            total_hits = search_result['hits']['total']['value']
                            segment_count = total_hits
                            
                            if total_hits > 0:
                                # 统计各类型embedding的数量
                                for hit in search_result['hits']['hits']:
                                    doc = hit['_source']
                                    if 'visual_embedding' in doc:
                                        segment_counts['visual'] += 1
                                    if 'text_embedding' in doc:
                                        segment_counts['text'] += 1
                                    if 'audio_embedding' in doc:
                                        segment_counts['audio'] += 1
                                
                                # 设置可用的embedding类型
                                if segment_counts['visual'] > 0:
                                    embeddings.append('🖼️ 视觉')
                                if segment_counts['text'] > 0:
                                    embeddings.append('📝 文本')
                                if segment_counts['audio'] > 0:
                                    embeddings.append('🎧 音频')
                        except:
                            pass
                    
                    materials.append({
                        'key': key,
                        'name': key.split('/')[-1],
                        'size': obj['Size'],
                        'lastModified': obj['LastModified'].isoformat(),
                        'url': file_url,
                        'embeddings': embeddings,
                        'hasEmbedding': len(embeddings) > 0,
                        'segmentCount': segment_count,
                        'segmentCounts': segment_counts
                    })
            
            response_body = {
                'materials': materials,
                'total': len(materials)
            }
            
        except Exception as e:
            response_body = {'error': str(e)}
            status_code = 500
    elif path == '/api/upload' and method == 'POST':
        try:
            body = json.loads(event.get('body', '{}'))
            file_data = body.get('file')
            file_name = body.get('fileName')
            file_type = body.get('fileType')
            
            # 验证必要参数
            if not all([file_data, file_name, file_type]):
                response_body = {"error": "缺少必要参数: file, fileName, fileType"}
                status_code = 400
            else:
                # 验证文件类型
                ext = file_name.split('.')[-1].lower()
                if ext not in ALLOWED_TYPES:
                    response_body = {"error": f"不支持的文件类型。仅支持: {', '.join(ALLOWED_TYPES)}"}
                    status_code = 400
                else:
                    # 生成唯一文件名
                    unique_name = f"{uuid.uuid4()}.{ext}"
                    
                    # 解码base64文件数据
                    file_content = base64.b64decode(file_data)
                    
                    # 上传到S3
                    s3_client.put_object(
                        Bucket=BUCKET_NAME,
                        Key=unique_name,
                        Body=file_content,
                        ContentType=file_type
                    )
                    
                    s3_uri = f"s3://{BUCKET_NAME}/{unique_name}"
                    response_body = {
                        "success": True,
                        "fileName": unique_name,
                        "s3Uri": s3_uri,
                        "uploadTime": datetime.now().isoformat()
                    }
        except Exception as e:
            response_body = {"error": str(e)}
            status_code = 500
    else:
        response_body = {"error": "Not Found"}
        status_code = 404
    
    # 默认成功状态码
    if 'status_code' not in locals():
        status_code = 200
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization'
        },
        'body': json.dumps(response_body)
    }