#!/usr/bin/env python3
"""
多模态搜索功能测试脚本
测试不同搜索模式的功能
"""

import json
import requests
import time
import base64
import os

# 配置
SEARCH_API_ENDPOINT = "https://ghefkhoaj4.execute-api.us-east-1.amazonaws.com/prod/"

def test_text_search():
    """测试文本搜索功能"""
    print("🔍 测试文本搜索...")
    
    test_queries = [
        "一只可爱的小猫",
        "美丽的风景",
        "现代建筑",
        "音乐演奏"
    ]
    
    for query in test_queries:
        print(f"\n测试查询: {query}")
        
        # 启动搜索
        response = requests.post(SEARCH_API_ENDPOINT, json={
            "searchType": "text",
            "searchMode": "visual-text",  # 文本搜索使用text embedding
            "queryText": query
        })
        
        if response.status_code == 202:
            result = response.json()
            search_id = result['search_id']
            print(f"搜索任务已启动: {search_id}")
            
            # 轮询结果
            poll_results(search_id)
        else:
            print(f"搜索启动失败: {response.text}")

def test_file_search_modes():
    """测试不同文件搜索模式"""
    print("🔍 测试文件搜索模式...")
    
    # 测试图片搜索
    test_image_search()
    
    # 测试视频搜索的不同模式
    test_video_search_modes()
    
    # 测试音频搜索
    test_audio_search()

def test_image_search():
    """测试图片搜索"""
    print("\n📸 测试图片搜索...")
    
    # 这里需要一个测试图片文件
    test_image_path = "test_image.jpg"  # 替换为实际的测试图片路径
    
    if not os.path.exists(test_image_path):
        print(f"测试图片不存在: {test_image_path}")
        return
    
    with open(test_image_path, 'rb') as f:
        file_data = base64.b64encode(f.read()).decode('utf-8')
    
    response = requests.post(SEARCH_API_ENDPOINT, json={
        "searchType": "file",
        "searchMode": "visual-image",
        "file": file_data,
        "fileName": "test_image.jpg",
        "fileType": "image/jpeg"
    })
    
    if response.status_code == 202:
        result = response.json()
        search_id = result['search_id']
        print(f"图片搜索任务已启动: {search_id}")
        poll_results(search_id)
    else:
        print(f"图片搜索启动失败: {response.text}")

def test_video_search_modes():
    """测试视频的不同搜索模式"""
    print("\n🎥 测试视频搜索模式...")
    
    test_video_path = "test_video.mp4"  # 替换为实际的测试视频路径
    
    if not os.path.exists(test_video_path):
        print(f"测试视频不存在: {test_video_path}")
        return
    
    # 测试三种视频搜索模式
    search_modes = [
        ("visual-image", "🖼️ 视觉相似"),
        ("visual-text", "📝 语义相似"),
        ("audio", "🎧 音频相似")
    ]
    
    with open(test_video_path, 'rb') as f:
        file_data = base64.b64encode(f.read()).decode('utf-8')
    
    for mode, description in search_modes:
        print(f"\n测试 {description} 模式...")
        
        response = requests.post(SEARCH_API_ENDPOINT, json={
            "searchType": "file",
            "searchMode": mode,
            "file": file_data,
            "fileName": "test_video.mp4",
            "fileType": "video/mp4"
        })
        
        if response.status_code == 202:
            result = response.json()
            search_id = result['search_id']
            print(f"视频搜索任务已启动 ({description}): {search_id}")
            poll_results(search_id)
        else:
            print(f"视频搜索启动失败 ({description}): {response.text}")
        
        time.sleep(2)  # 避免过于频繁的请求

def test_audio_search():
    """测试音频搜索"""
    print("\n🎧 测试音频搜索...")
    
    test_audio_path = "test_audio.wav"  # 替换为实际的测试音频路径
    
    if not os.path.exists(test_audio_path):
        print(f"测试音频不存在: {test_audio_path}")
        return
    
    with open(test_audio_path, 'rb') as f:
        file_data = base64.b64encode(f.read()).decode('utf-8')
    
    response = requests.post(SEARCH_API_ENDPOINT, json={
        "searchType": "file",
        "searchMode": "audio",
        "file": file_data,
        "fileName": "test_audio.wav",
        "fileType": "audio/wav"
    })
    
    if response.status_code == 202:
        result = response.json()
        search_id = result['search_id']
        print(f"音频搜索任务已启动: {search_id}")
        poll_results(search_id)
    else:
        print(f"音频搜索启动失败: {response.text}")

def poll_results(search_id, max_attempts=30):
    """轮询搜索结果"""
    print(f"正在轮询搜索结果: {search_id}")
    
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{SEARCH_API_ENDPOINT}status/{search_id}")
            
            if response.status_code == 200:
                result = response.json()
                status = result['status']
                
                if status == 'completed':
                    results = result.get('results', [])
                    print(f"✅ 搜索完成！找到 {len(results)} 个相似内容")
                    
                    # 显示前3个结果
                    for i, item in enumerate(results[:3]):
                        print(f"  {i+1}. 相似度: {item['score']:.3f} | 文件: {item['s3_uri'].split('/')[-1]} | 类型: {item['file_type']}")
                        if 'search_info' in item:
                            info = item['search_info']
                            print(f"     搜索模式: {info.get('search_embedding_type', 'unknown')} → {info.get('target_embedding_type', 'unknown')}")
                    
                    return results
                    
                elif status == 'failed':
                    error = result.get('error', 'Unknown error')
                    print(f"❌ 搜索失败: {error}")
                    return None
                    
                elif status == 'processing':
                    print(f"⏳ 处理中... (尝试 {attempt + 1}/{max_attempts})")
                    
            else:
                print(f"获取状态失败: {response.text}")
                
        except Exception as e:
            print(f"轮询错误: {e}")
        
        time.sleep(5)  # 等待5秒
    
    print("⏰ 搜索超时")
    return None

def main():
    """主测试函数"""
    print("🚀 开始多模态搜索功能测试")
    print("=" * 50)
    
    # 检查API端点配置
    if "your-api-gateway-url" in SEARCH_API_ENDPOINT:
        print("❌ 请先配置正确的API Gateway URL")
        return
    
    try:
        # 测试文本搜索
        test_text_search()
        
        print("\n" + "=" * 50)
        
        # 测试文件搜索
        test_file_search_modes()
        
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
    
    print("\n🏁 测试完成")

if __name__ == "__main__":
    main()