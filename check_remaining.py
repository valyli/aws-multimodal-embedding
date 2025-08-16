#!/usr/bin/env python3
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
import json

# 配置
OPENSEARCH_ENDPOINT = "https://r3u774iquxn9roqtkrpl.us-east-1.aoss.amazonaws.com"
OPENSEARCH_INDEX = "embeddings"

def get_opensearch_client():
    """初始化OpenSearch客户端"""
    host = OPENSEARCH_ENDPOINT.replace("https://", "")
    region = "us-east-1"
    
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

def main():
    try:
        client = get_opensearch_client()
        
        # 获取所有剩余文档
        print("=== 检查剩余文档 ===")
        search_result = client.search(
            index=OPENSEARCH_INDEX,
            body={
                'query': {'match_all': {}},
                'size': 20
            }
        )
        
        total_docs = search_result['hits']['total']['value']
        print(f"剩余文档数量: {total_docs}")
        
        print("\n=== 剩余文档详情 ===")
        for i, hit in enumerate(search_result['hits']['hits']):
            print(f"\n文档 {i+1} (ID: {hit['_id']}):")
            source = hit['_source']
            
            # 检查所有字段
            for key, value in source.items():
                if key.endswith('_embedding'):
                    print(f"  {key}: [向量数据, 长度={len(value) if isinstance(value, list) else 'N/A'}]")
                else:
                    print(f"  {key}: {value}")
        
        # 测试删除一个文档
        if search_result['hits']['hits']:
            test_doc_id = search_result['hits']['hits'][0]['_id']
            print(f"\n=== 测试删除文档 {test_doc_id} ===")
            try:
                delete_result = client.delete(
                    index=OPENSEARCH_INDEX,
                    id=test_doc_id
                )
                print(f"删除结果: {delete_result}")
            except Exception as e:
                print(f"删除失败: {e}")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()