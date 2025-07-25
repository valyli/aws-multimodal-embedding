import json
import boto3
import base64
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
MARENG0_MODEL_ID = 'twelvelabs.marengo-embed-2-7-v1:0'
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
        
        # 根据文件类型生成embedding
        temp_s3_uri = f"s3://{UPLOAD_BUCKET}/{temp_key}"
        media_type = 'video' if ext in ['mp4', 'mov'] else 'image'
        query_embedding = get_embedding_from_marengo(media_type, temp_s3_uri, UPLOAD_BUCKET)
        
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
        
        # 发起异步调用，带重试机制
        max_retries = 5
        retry_delay = 1
        
        for retry in range(max_retries):
            try:
                start_resp = bedrock_client.start_async_invoke(
                    modelId=MARENG0_MODEL_ID,
                    modelInput=model_input,
                    outputDataConfig=output_data_config
                )
                break
            except Exception as e:
                if "ThrottlingException" in str(e) and retry < max_retries - 1:
                    print(f"Throttling detected, retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                    continue
                else:
                    raise e
            
        invocation_arn = start_resp["invocationArn"]
        print("Invocation ARN:", invocation_arn)
        
        # 轮询结果
        max_attempts = 24  # 最多等待2分钟
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
                            if "embedding" in output_json["data"][0]:
                                return output_json["data"][0]["embedding"]
                            else:
                                raise ValueError("No embedding found in output.json")
                        except Exception as s3_error:
                            print(f"Failed to read output.json from path: {output_key}")
                            raise s3_error
                        
                elif res["status"] in ("Failed", "Cancelled"):
                    error_msg = res.get("failureMessage", "Unknown error")
                    if "Unprocessable video" in error_msg:
                        raise ValueError(f"视频格式不支持: {error_msg}. 请尝试使用标准的MP4格式，时长不超过10分钟")
                    else:
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