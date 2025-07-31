#!/bin/bash

# AWS 多模态嵌入搜索系统 - 一键部署脚本
# 使用方法: ./deploy.sh

set -e

echo "🚀 开始部署 AWS 多模态嵌入搜索系统..."

# 检查必要工具
echo "📋 检查环境依赖..."
command -v aws >/dev/null 2>&1 || { echo "❌ AWS CLI 未安装"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ Node.js 未安装"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python3 未安装"; exit 1; }
command -v cdk >/dev/null 2>&1 || { echo "❌ AWS CDK 未安装"; exit 1; }

# 检查AWS凭证
echo "🔐 检查AWS凭证..."
aws sts get-caller-identity >/dev/null 2>&1 || { echo "❌ AWS凭证未配置"; exit 1; }

# 读取配置
SERVICE_PREFIX=$(python3 -c "import sys; sys.path.append('config'); from settings import SERVICE_PREFIX; print(SERVICE_PREFIX)")
AWS_REGION=$(aws configure get region || echo "us-east-1")

echo "📝 配置信息:"
echo "   服务前缀: $SERVICE_PREFIX"
echo "   AWS区域: $AWS_REGION"

# 构建OpenSearch Layer
echo "🔧 构建OpenSearch Layer..."
cd backend/layers/opensearch_layer
if [ ! -d "python" ]; then
    mkdir -p python
    pip3 install opensearch-py==2.8.0 -t python/
    echo "✅ OpenSearch Layer构建完成"
else
    echo "✅ OpenSearch Layer已存在"
fi
cd ../../../

# 安装CDK依赖
echo "📦 安装CDK依赖..."
cd infrastructure
npm install
pip3 install -r requirements.txt

# CDK Bootstrap (如果需要)
echo "🏗️ 初始化CDK..."
AWS_REGION=$AWS_REGION cdk bootstrap --region $AWS_REGION

# 部署基础设施
echo "🚀 部署基础设施..."
AWS_REGION=$AWS_REGION cdk deploy --require-approval never

# 获取输出信息
echo "📊 获取部署信息..."
STACK_NAME="${SERVICE_PREFIX}-stack"
CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDomainName`].OutputValue' \
    --output text)

SEARCH_API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`SearchApiEndpoint`].OutputValue' \
    --output text)

FRONTEND_BUCKET="${SERVICE_PREFIX}-frontend"

# 更新搜索页面API端点
echo "🔄 更新搜索页面配置..."
cd ../frontend
sed -i.bak "s|{{SEARCH_API_ENDPOINT}}|$SEARCH_API_ENDPOINT|g" search.html

# 上传前端文件
echo "📤 上传前端文件..."
aws s3 cp . s3://$FRONTEND_BUCKET/ --recursive --exclude "*.bak"

cd ..

echo ""
echo "🎉 部署完成！"
echo ""
echo "📱 访问地址:"
echo "   上传页面: https://$CLOUDFRONT_DOMAIN/upload.html"
echo "   搜索页面: https://$CLOUDFRONT_DOMAIN/search.html"
echo ""
echo "🔗 API端点:"
echo "   搜索API: $SEARCH_API_ENDPOINT"
echo ""
echo "📝 后续步骤:"
echo "   1. 访问上传页面测试文件上传"
echo "   2. 访问搜索页面测试相似搜索"
echo "   3. 查看CloudWatch日志监控系统状态"
echo ""
echo "🗑️ 清理资源: cd infrastructure && cdk destroy"