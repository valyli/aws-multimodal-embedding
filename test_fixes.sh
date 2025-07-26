#!/bin/bash

echo "🧪 测试修复结果..."
echo

# 测试API端点
echo "1. 测试API端点："
echo "   根路径 (/):"
curl -s https://phs8fhnzi4.execute-api.us-east-1.amazonaws.com/prod/ | jq .
echo
echo "   健康检查 (/health):"
curl -s https://phs8fhnzi4.execute-api.us-east-1.amazonaws.com/prod/health | jq .
echo
echo "   数据API (/api/data):"
curl -s https://phs8fhnzi4.execute-api.us-east-1.amazonaws.com/prod/api/data | jq .
echo

# 测试前端页面
echo "2. 测试前端页面内容："
echo "   标题和描述："
curl -s https://d7senjgtq9ilu.cloudfront.net/public/index.html | grep -E "<title>|<h1>|<p.*center.*color.*666" | head -3
echo

echo "✅ 修复完成！"
echo
echo "📱 访问地址："
echo "   主页: https://d7senjgtq9ilu.cloudfront.net/public/index.html"
echo "   上传页面: https://d7senjgtq9ilu.cloudfront.net/public/upload.html"
echo "   搜索页面: https://d7senjgtq9ilu.cloudfront.net/search.html"