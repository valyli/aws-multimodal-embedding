#!/usr/bin/env python3
"""
测试OpenSearch Serverless功能
"""
import boto3
import json
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

OPENSEARCH_ENDPOINT = 'https://p3ipsonhfnl95wed00cj.us-east-1.aoss.amazonaws.com'
OPENSEARCH_INDEX = 'embeddings'

def get_opensearch_client():
    """初始化OpenSearch客户端"""
    host = OPENSEARCH_ENDPOINT.replace("https://", "")
    region = 'us-east-1'
    
    # 创建AWS签名认证
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, region, 'aoss')
    
    # 创建OpenSearch客户端
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )
    return client

def test_connection():
    """测试连接"""
    try:
        client = get_opensearch_client()
        info = client.info()
        print("✅ OpenSearch连接成功:")
        print(json.dumps(info, indent=2))
        return client
    except Exception as e:
        print(f"❌ OpenSearch连接失败: {e}")
        return None

def check_indices(client):
    """检查索引"""
    try:
        indices = client.indices.get_alias("*")
        print("📋 现有索引:")
        for index in indices:
            print(f"  - {index}")
        
        if OPENSEARCH_INDEX in indices:
            print(f"✅ 索引 '{OPENSEARCH_INDEX}' 存在")
            
            # 获取索引映射
            mapping = client.indices.get_mapping(index=OPENSEARCH_INDEX)
            print("🗺️ 索引映射:")
            print(json.dumps(mapping, indent=2))
            
            return True
        else:
            print(f"❌ 索引 '{OPENSEARCH_INDEX}' 不存在")
            return False
    except Exception as e:
        print(f"❌ 检查索引失败: {e}")
        return False

def check_documents(client):
    """检查文档数量"""
    try:
        count = client.count(index=OPENSEARCH_INDEX)
        doc_count = count['count']
        print(f"📊 索引中的文档数量: {doc_count}")
        
        if doc_count > 0:
            # 获取一些示例文档
            search_result = client.search(
                index=OPENSEARCH_INDEX,
                body={"query": {"match_all": {}}, "size": 3}
            )
            
            print("📄 示例文档:")
            for hit in search_result['hits']['hits']:
                doc = hit['_source']
                print(f"  - S3 URI: {doc.get('s3_uri', 'N/A')}")
                print(f"    文件类型: {doc.get('file_type', 'N/A')}")
                print(f"    时间戳: {doc.get('timestamp', 'N/A')}")
                print(f"    向量维度: {len(doc.get('embedding_vector', []))}")
                print()
        
        return doc_count
    except Exception as e:
        print(f"❌ 检查文档失败: {e}")
        return 0

def test_vector_search(client):
    """测试向量搜索"""
    try:
        # 创建一个测试向量
        test_vector = [0.1] * 1024
        
        query = {
            "size": 3,
            "query": {
                "knn": {
                    "embedding_vector": {
                        "vector": test_vector,
                        "k": 3
                    }
                }
            }
        }
        
        result = client.search(index=OPENSEARCH_INDEX, body=query)
        
        print("🔍 向量搜索测试结果:")
        for hit in result['hits']['hits']:
            print(f"  - 分数: {hit['_score']:.4f}")
            print(f"    S3 URI: {hit['_source']['s3_uri']}")
            print(f"    文件类型: {hit['_source']['file_type']}")
            print()
            
        return True
    except Exception as e:
        print(f"❌ 向量搜索测试失败: {e}")
        return False

def main():
    print("🧪 OpenSearch Serverless 测试开始")
    print("=" * 50)
    
    # 测试连接
    client = test_connection()
    if not client:
        return
    
    print("\n" + "=" * 50)
    
    # 检查索引
    index_exists = check_indices(client)
    
    print("\n" + "=" * 50)
    
    # 检查文档
    doc_count = check_documents(client)
    
    if doc_count > 0:
        print("\n" + "=" * 50)
        # 测试向量搜索
        test_vector_search(client)
    
    print("\n" + "=" * 50)
    print("🏁 测试完成")

if __name__ == "__main__":
    main()