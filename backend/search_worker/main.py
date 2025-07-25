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
    file_name = message['file_name']
    file_type = message['file_type']
    s3_key = message['s3_key']
    
    print(f"Processing search for file: {file_name}")
    
    # 判断媒体类型
    file_ext = file_name.split('.')[-1].lower()
    if file_ext in ['png', 'jpeg', 'jpg', 'webp']:
        media_type = 'image'
    elif file_ext in ['mp4', 'mov']:
        media_type = 'video'
    else:
        raise ValueError(f"Unsupported file type: {file_ext}")
    
    s3_uri = f"s3://{UPLOAD_BUCKET}/{s3_key}"
    
    # 获取查询embedding
    query_embedding = get_embedding_from_marengo(media_type, s3_uri, UPLOAD_BUCKET)
    
    # 在OpenSearch中搜索相似内容
    opensearch_client = get_opensearch_client()
    search_results = search_similar_embeddings(opensearch_client, query_embedding)
    
    # 清理临时文件
    try:
        s3_client.delete_object(Bucket=UPLOAD_BUCKET, Key=s3_key)
    except:
        pass
    
    return search_results

def get_embedding_from_marengo(media_type, s3_uri, bucket_name):
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
                        
                        if "embedding" in output_json["data"][0]:
                            return output_json["data"][0]["embedding"]
                        else:
                            raise ValueError("No embedding found in output.json")
                        
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

def search_similar_embeddings(client, query_embedding, top_k=10):
    """在OpenSearch中搜索相似embedding"""
    search_body = {
        "size": top_k,
        "query": {
            "knn": {
                "embedding_vector": {
                    "vector": query_embedding,
                    "k": top_k
                }
            }
        },
        "_source": ["s3_uri", "file_type", "timestamp"]
    }
    
    response = client.search(
        index=OPENSEARCH_INDEX,
        body=search_body
    )
    
    results = []
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