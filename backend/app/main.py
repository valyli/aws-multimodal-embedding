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
    elif path == '/api/debug/opensearch' and method == 'GET':
        try:
            opensearch_endpoint = os.environ.get('OPENSEARCH_ENDPOINT')
            if opensearch_endpoint:
                from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
                import boto3
                
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
                
                # 直接搜索检查索引状态（OpenSearch Serverless兼容）
                try:
                    sample_docs = opensearch_client.search(
                        index='embeddings',
                        body={'query': {'match_all': {}}, 'size': 10}
                    )
                    
                    doc_count = sample_docs['hits']['total']['value']
                    sample_documents = []
                    
                    for hit in sample_docs['hits']['hits']:
                        doc = hit['_source'].copy()
                        # 移除embedding向量数据以减少响应大小
                        for key in list(doc.keys()):
                            if key.endswith('_embedding'):
                                doc[key] = f"[向量数据, 长度={len(doc[key]) if isinstance(doc[key], list) else 'N/A'}]"
                        sample_documents.append(doc)
                    
                    response_body = {
                        'index_exists': True,
                        'document_count': doc_count,
                        'sample_documents': sample_documents
                    }
                    
                except Exception as search_error:
                    if '404' in str(search_error) or 'index_not_found' in str(search_error).lower():
                        response_body = {
                            'index_exists': False,
                            'document_count': 0,
                            'sample_documents': []
                        }
                    else:
                        raise search_error
            else:
                response_body = {'error': 'OpenSearch endpoint not configured'}
                
        except Exception as e:
            response_body = {'error': str(e)}
            status_code = 500
    elif path == '/api/cleanup' and method == 'DELETE':
        try:
            # 清理S3文件（包括bedrock-outputs）
            try:
                # 使用分页获取所有对象
                paginator = s3_client.get_paginator('list_objects_v2')
                objects_to_delete = []
                
                for page in paginator.paginate(Bucket=BUCKET_NAME):
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            objects_to_delete.append({'Key': obj['Key']})
                
                if objects_to_delete:
                    print(f"Deleting {len(objects_to_delete)} S3 objects")
                    # 批量删除S3对象
                    for i in range(0, len(objects_to_delete), 1000):  # S3批量删除最多1000个
                        batch = objects_to_delete[i:i+1000]
                        s3_client.delete_objects(
                            Bucket=BUCKET_NAME,
                            Delete={'Objects': batch}
                        )
                        print(f"Deleted batch {i//1000 + 1}")
            except Exception as s3_error:
                print(f"S3 cleanup error: {str(s3_error)}")
                response_body = {'error': f'S3 cleanup failed: {str(s3_error)}'}
                status_code = 500
            
            # 清理OpenSearch
            opensearch_endpoint = os.environ.get('OPENSEARCH_ENDPOINT')
            if opensearch_endpoint:
                try:
                    from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
                    import boto3
                    
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
                    
                    # 删除所有embedding数据 - OpenSearch Serverless不支持delete_by_query
                    index_name = os.environ.get('OPENSEARCH_INDEX', 'embeddings')
                    
                    # 使用多轮删除确保所有文档都被删除
                    total_deleted = 0
                    max_rounds = 10  # 最多10轮
                    
                    for round_num in range(max_rounds):
                        # 检查是否还有文档
                        check_result = opensearch_client.search(
                            index=index_name,
                            body={
                                'query': {'match_all': {}},
                                'size': 0  # 只要总数
                            }
                        )
                        
                        remaining_docs = check_result['hits']['total']['value']
                        print(f"Round {round_num + 1}: {remaining_docs} documents remaining")
                        
                        if remaining_docs == 0:
                            break
                            
                        # 获取一批文档ID进行删除
                        search_result = opensearch_client.search(
                            index=index_name,
                            body={
                                'query': {'match_all': {}},
                                'size': min(500, remaining_docs),  # 每次最多500个
                                '_source': False
                            }
                        )
                        
                        hits = search_result['hits']['hits']
                        if not hits:
                            break
                            
                        # 批量删除
                        bulk_body = []
                        for hit in hits:
                            bulk_body.append({
                                'delete': {
                                    '_index': index_name,
                                    '_id': hit['_id']
                                }
                            })
                        
                        if bulk_body:
                            delete_result = opensearch_client.bulk(body=bulk_body)
                            batch_deleted = len(bulk_body)
                            total_deleted += batch_deleted
                            print(f"Deleted {batch_deleted} documents in round {round_num + 1}, total: {total_deleted}")
                            
                            # 检查是否有删除错误
                            if 'errors' in delete_result and delete_result['errors']:
                                print(f"Some delete errors occurred: {delete_result}")
                        
                        # 等待一下让索引更新
                        import time
                        time.sleep(1)
                    
                    print(f"Cleared {total_deleted} documents from OpenSearch index: {index_name} in {round_num + 1} rounds")
                except Exception as os_error:
                    print(f"OpenSearch cleanup error: {str(os_error)}")
                    import traceback
                    traceback.print_exc()
            
            # 清理DynamoDB搜索记录
            search_table_name = os.environ.get('SEARCH_TABLE_NAME', 'multimodal-search-search-tasks')
            if search_table_name:
                try:
                    dynamodb = boto3.resource('dynamodb')
                    table = dynamodb.Table(search_table_name)
                    
                    # 扫描并删除所有记录
                    deleted_count = 0
                    scan_response = table.scan()
                    
                    while True:
                        items = scan_response.get('Items', [])
                        if items:
                            with table.batch_writer() as batch:
                                for item in items:
                                    batch.delete_item(Key={'search_id': item['search_id']})
                                    deleted_count += 1
                        
                        # 检查是否有更多数据
                        if 'LastEvaluatedKey' not in scan_response:
                            break
                        scan_response = table.scan(ExclusiveStartKey=scan_response['LastEvaluatedKey'])
                    
                    print(f"DynamoDB deleted {deleted_count} search records")
                except Exception as db_error:
                    print(f"DynamoDB cleanup error: {str(db_error)}")
            
            if 'response_body' not in locals():
                response_body = {
                    "success": True,
                    "message": "清库操作完成，所有数据已清理干净"
                }
            status_code = 200
            
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