#!/bin/bash

# 部署脚本
set -e

echo "🚀 开始部署 Cloudscape 应用..."

# 检查并安装CDK
if ! command -v cdk &> /dev/null; then
    echo "📦 安装AWS CDK..."
    npm install -g aws-cdk
fi

# 进入infrastructure目录
cd infrastructure

# 安装CDK依赖
echo "📦 安装CDK依赖..."
pip install -r requirements.txt

# 安装后端依赖
echo "📦 安装后端依赖..."
cd ../backend

# 检查并安装编译工具
if ! command -v gcc &> /dev/null; then
    echo "🔧 安装编译工具..."
    sudo yum groupinstall -y "Development Tools"
fi

pip install -r requirements.txt -t app/

# 返回infrastructure目录
cd ../infrastructure

# CDK部署
echo "🏗️  部署AWS资源..."
cdk bootstrap
cdk deploy --require-approval never

# 构建前端
echo "🎨 构建前端应用..."
cd ../frontend
npm install
npm run build

echo "✅ 部署完成！"
echo ""
echo "🎉 AWS Cloudscape 应用部署成功！"
echo ""
echo "API 端点:"
echo "  - 主页: https://phs8fhnzi4.execute-api.us-east-1.amazonaws.com/prod/"
echo "  - 健康检查: https://phs8fhnzi4.execute-api.us-east-1.amazonaws.com/prod/health"
echo "  - 数据 API: https://phs8fhnzi4.execute-api.us-east-1.amazonaws.com/prod/api/data"
echo ""
echo "📝 请手动将frontend/build/目录内容上传到S3存储桶: cloudscape-demo-frontend"
echo "🔧 要修改服务前缀，请编辑 config/settings.py 文件"