#!/usr/bin/env python3

import boto3
import os
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth

# OpenSearch配置
OPENSEARCH_ENDPOINT = "https://p3ipsonhfnl95wed00cj.us-east-1.aoss.amazonaws.com"
INDEX_NAME = "embeddings"

def clear_opensearch_data():
    """清空OpenSearch中的所有数据"""
    
    # 获取配置
    region = os.environ.get('AWS_REGION', boto3.Session().region_name or 'us-east-1')
    
    # 获取AWS凭证
    session = boto3.Session()
    credentials = session.get_credentials()
    
    # 创建认证
    auth = AWSRequestsAuth(
        aws_access_key=credentials.access_key,
        aws_secret_access_key=credentials.secret_key,
        aws_token=credentials.token,
        aws_host=OPENSEARCH_ENDPOINT.replace('https://', ''),
        aws_region=region,
        aws_service='aoss'
    )
    
    # 创建OpenSearch客户端
    client = OpenSearch(
        hosts=[OPENSEARCH_ENDPOINT],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )
    
    try:
        # 检查索引是否存在
        if client.indices.exists(index=INDEX_NAME):
            print(f"删除索引: {INDEX_NAME}")
            client.indices.delete(index=INDEX_NAME)
            print("✅ OpenSearch索引已删除")
        else:
            print("ℹ️ OpenSearch索引不存在，无需删除")
            
    except Exception as e:
        print(f"❌ 清理OpenSearch时出错: {e}")

if __name__ == "__main__":
    clear_opensearch_data()