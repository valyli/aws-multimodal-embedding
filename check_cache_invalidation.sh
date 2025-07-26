#!/bin/bash

DISTRIBUTION_ID="E1EGKUZ1A4OP4"
INVALIDATION_ID="I7TZ5ZVWDSZKLF154NAHBMBI68"
CLOUDFRONT_URL="https://d7senjgtq9ilu.cloudfront.net/public/index.html"

echo "🔄 检查CloudFront缓存失效状态..."
echo

# 检查失效状态
STATUS=$(aws cloudfront get-invalidation --distribution-id $DISTRIBUTION_ID --id $INVALIDATION_ID --query 'Invalidation.Status' --output text)
echo "缓存失效状态: $STATUS"
echo

if [ "$STATUS" = "Completed" ]; then
    echo "✅ 缓存失效已完成！"
else
    echo "⏳ 缓存失效进行中，通常需要3-5分钟..."
fi

echo
echo "🧪 测试更新后的页面内容:"
echo "标题和描述:"
curl -s $CLOUDFRONT_URL | grep -E "<title>|<h1>|<p.*center.*color.*666" | head -3
echo

echo "📱 访问地址:"
echo "   主页: https://d7senjgtq9ilu.cloudfront.net/public/index.html"
echo "   上传页面: https://d7senjgtq9ilu.cloudfront.net/public/upload.html"
echo "   搜索页面: https://d7senjgtq9ilu.cloudfront.net/search.html"
echo

if [ "$STATUS" != "Completed" ]; then
    echo "💡 提示: 如果还看不到更新，请等待几分钟后再次运行此脚本"
    echo "命令: ./check_cache_invalidation.sh"
fi