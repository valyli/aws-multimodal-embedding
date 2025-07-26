import json
import boto3
import base64
import uuid
from datetime import datetime

s3_client = boto3.client('s3')
BUCKET_NAME = 'cloudscape-demo-uploads'
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
            "message": "Hello from cloudscape-demo!", 
            "status": "running"
        }
    elif path == '/health' and method == 'GET':
        response_body = {
            "status": "healthy", 
            "service": "cloudscape-demo"
        }
    elif path == '/api/data' and method == 'GET':
        response_body = {
            "data": [
                {"id": 1, "name": "Item 1", "status": "active"},
                {"id": 2, "name": "Item 2", "status": "inactive"},
            ],
            "total": 2
        }
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