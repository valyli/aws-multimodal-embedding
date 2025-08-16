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
        
        # 检查集合信息
        print("=== OpenSearch 集合信息 ===")
        print(f"端点: {OPENSEARCH_ENDPOINT}")
        
        # 列出所有索引
        print("\n=== 所有索引 ===")
        try:
            indices = client.cat.indices(format='json')
            print(f"找到 {len(indices)} 个索引:")
            for idx in indices:
                print(f"  - {idx['index']} (文档数: {idx['docs.count']})")
        except Exception as e:
            print(f"获取索引列表失败: {e}")
        
        # 检查目标索引是否存在
        print(f"\n=== 检查索引 '{OPENSEARCH_INDEX}' ===")
        index_exists = client.indices.exists(index=OPENSEARCH_INDEX)
        print(f"索引存在: {index_exists}")
        
        if index_exists:
            # 直接搜索获取文档信息
            try:
                sample = client.search(
                    index=OPENSEARCH_INDEX,
                    body={'query': {'match_all': {}}, 'size': 5}
                )
                doc_count = sample['hits']['total']['value']
                print(f"文档数量: {doc_count}")
                
                if doc_count > 0:
                    print(f"\n样本文档:")
                    for i, hit in enumerate(sample['hits']['hits']):
                        print(f"  文档 {i+1}:")
                        source = hit['_source']
                        print(f"    s3_uri: {source.get('s3_uri', 'N/A')}")
                        print(f"    media_type: {source.get('media_type', 'N/A')}")
                        print(f"    file_type: {source.get('file_type', 'N/A')}")
                        print(f"    segment_index: {source.get('segment_index', 'N/A')}")
                        embeddings = []
                        if 'visual_embedding' in source:
                            embeddings.append('visual')
                        if 'text_embedding' in source:
                            embeddings.append('text')
                        if 'audio_embedding' in source:
                            embeddings.append('audio')
                        print(f"    embeddings: {embeddings}")
            except Exception as e:
                print(f"搜索文档失败: {e}")
        
        # 测试删除操作
        print(f"\n=== 测试删除操作 ===")
        if index_exists:
            try:
                # 先测试一个简单的删除查询
                delete_result = client.delete_by_query(
                    index=OPENSEARCH_INDEX,
                    body={'query': {'match_all': {}}},
                    wait_for_completion=True,
                    conflicts='proceed'
                )
                print(f"删除操作完成，删除了 {delete_result.get('deleted', 0)} 个文档")
            except Exception as e:
                print(f"删除操作失败: {e}")
                import traceback
                traceback.print_exc()
        
    except Exception as e:
        print(f"连接失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()