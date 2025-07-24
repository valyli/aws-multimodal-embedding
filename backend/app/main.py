import json

def handler(event, context):
    """
    简化的Lambda处理器
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