#!/usr/bin/env python3
"""
初始化OpenSearch Serverless索引
"""
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth

def create_index():
    # AWS认证
    session = boto3.Session()
    credentials = session.get_credentials()
    awsauth = AWSRequestsAuth(
        aws_access_key=credentials.access_key,
        aws_secret_access_key=credentials.secret_key,
        aws_token=credentials.token,
        aws_host='multimodal-embeddings.us-east-1.aoss.amazonaws.com',
        aws_region='us-east-1',
        aws_service='aoss'
    )
    
    # OpenSearch客户端
    client = OpenSearch(
        hosts=[{'host': 'multimodal-embeddings.us-east-1.aoss.amazonaws.com', 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )
    
    # 索引映射
    index_mapping = {
        "mappings": {
            "properties": {
                "s3_uri": {"type": "keyword"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 1024,
                    "index": True,
                    "similarity": "cosine"
                },
                "file_type": {"type": "keyword"},
                "timestamp": {"type": "date"},
                "id": {"type": "keyword"}
            }
        }
    }
    
    try:
        # 创建索引
        response = client.indices.create(
            index='embeddings',
            body=index_mapping
        )
        print(f"索引创建成功: {response}")
    except Exception as e:
        if "resource_already_exists_exception" in str(e):
            print("索引已存在")
        else:
            print(f"创建索引失败: {e}")

if __name__ == "__main__":
    create_index()