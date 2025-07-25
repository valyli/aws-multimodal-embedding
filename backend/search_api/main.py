import json
import boto3
import uuid
import base64
from datetime import datetime
import os

# 初始化客户端
dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')
s3_client = boto3.client('s3')

# 配置
SEARCH_TABLE_NAME = os.environ.get('SEARCH_TABLE_NAME')
SEARCH_QUEUE_URL = os.environ.get('SEARCH_QUEUE_URL')
UPLOAD_BUCKET = 'cloudscape-demo-uploads'

def handler(event, context):
    """
    异步搜索API - 快速返回搜索ID
    """
    try:
        path = event.get('path', '/')
        method = event.get('httpMethod', 'GET')
        
        if path == '/' and method == 'POST':
            return start_search(event)
        elif path.startswith('/status/') and method == 'GET':
            search_id = path.split('/')[-1]
            return get_search_status(search_id)
        else:
            return {
                'statusCode': 404,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Not found'})
            }
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }

def start_search(event):
    """启动搜索任务"""
    try:
        body = json.loads(event.get('body', '{}'))
        search_type = body.get('searchType', 'file')  # 'file' 或 'text'
        search_mode = body.get('searchMode', 'visual-image')  # 搜索模式
        
        # 生成搜索ID
        search_id = str(uuid.uuid4())
        
        if search_type == 'text':
            # 文本搜索
            query_text = body.get('queryText')
            if not query_text:
                return {
                    'statusCode': 400,
                    'headers': get_cors_headers(),
                    'body': json.dumps({'error': 'Missing query text'})
                }
            
            # 在DynamoDB中创建搜索任务记录
            table = dynamodb.Table(SEARCH_TABLE_NAME)
            table.put_item(
                Item={
                    'search_id': search_id,
                    'status': 'pending',
                    'search_type': 'text',
                    'search_mode': search_mode,
                    'query_text': query_text,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
            )
            
            # 发送消息到SQS队列
            sqs.send_message(
                QueueUrl=SEARCH_QUEUE_URL,
                MessageBody=json.dumps({
                    'search_id': search_id,
                    'search_type': 'text',
                    'search_mode': search_mode,
                    'query_text': query_text
                })
            )
            
        else:
            # 文件搜索
            file_data = body.get('file')
            file_name = body.get('fileName')
            file_type = body.get('fileType')
            
            if not all([file_data, file_name, file_type]):
                return {
                    'statusCode': 400,
                    'headers': get_cors_headers(),
                    'body': json.dumps({'error': 'Missing file data or filename'})
                }
            
            # 临时存储文件到S3
            temp_key = f"temp/{search_id}.{file_name.split('.')[-1]}"
            file_content = base64.b64decode(file_data)
            
            s3_client.put_object(
                Bucket=UPLOAD_BUCKET,
                Key=temp_key,
                Body=file_content,
                ContentType=file_type
            )
            
            # 在DynamoDB中创建搜索任务记录
            table = dynamodb.Table(SEARCH_TABLE_NAME)
            table.put_item(
                Item={
                    'search_id': search_id,
                    'status': 'pending',
                    'search_type': 'file',
                    'search_mode': search_mode,
                    'file_name': file_name,
                    'file_type': file_type,
                    's3_key': temp_key,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
            )
            
            # 发送消息到SQS队列
            sqs.send_message(
                QueueUrl=SEARCH_QUEUE_URL,
                MessageBody=json.dumps({
                    'search_id': search_id,
                    'search_type': 'file',
                    'search_mode': search_mode,
                    'file_name': file_name,
                    'file_type': file_type,
                    's3_key': temp_key
                })
            )
        
        return {
            'statusCode': 202,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'search_id': search_id,
                'status': 'pending',
                'message': 'Search started successfully'
            })
        }
        
    except Exception as e:
        print(f"Error starting search: {str(e)}")
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }

def get_search_status(search_id):
    """获取搜索状态和结果"""
    try:
        table = dynamodb.Table(SEARCH_TABLE_NAME)
        response = table.get_item(Key={'search_id': search_id})
        
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Search not found'})
            }
        
        item = response['Item']
        result = {
            'search_id': search_id,
            'status': item['status'],
            'created_at': item['created_at'],
            'updated_at': item['updated_at']
        }
        
        if item['status'] == 'completed' and 'results' in item:
            result['results'] = json.loads(item['results'])
        elif item['status'] == 'failed' and 'error' in item:
            result['error'] = item['error']
            
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps(result)
        }
        
    except Exception as e:
        print(f"Error getting search status: {str(e)}")
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }

def get_cors_headers():
    """返回CORS头部"""
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    }