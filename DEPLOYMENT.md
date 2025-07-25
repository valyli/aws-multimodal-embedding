# AWS 多模态嵌入搜索系统 - 部署指南

## 📋 系统概述

基于AWS无服务器架构的多模态嵌入搜索系统，支持图片上传、自动向量化处理和相似度搜索。

### 🏗️ 架构组件
- **前端**: HTML/JS静态页面 (CloudFront + S3)
- **API**: API Gateway + Lambda (Python)
- **存储**: S3 + OpenSearch Serverless
- **AI**: Amazon Bedrock Titan Multimodal Embeddings
- **基础设施**: AWS CDK (Python)

## 🔧 前置要求

### 1. 环境准备
```bash
# AWS CLI (版本 2.x)
aws --version

# Node.js (版本 18.x+)
node --version
npm --version

# Python (版本 3.11+)
python3 --version
pip3 --version

# AWS CDK
npm install -g aws-cdk
cdk --version
```

### 2. AWS 权限要求
确保AWS账户具有以下服务权限：
- **Lambda**: 创建函数、层、权限
- **API Gateway**: 创建REST API
- **S3**: 创建存储桶、对象操作
- **CloudFront**: 创建分发
- **OpenSearch Serverless**: 创建集合、策略
- **Bedrock**: 调用模型 (需要在控制台启用Titan模型)
- **IAM**: 创建角色、策略

### 3. Bedrock 模型启用
1. 登录AWS控制台
2. 进入Amazon Bedrock服务
3. 选择"Model access"
4. 启用 `Amazon Titan Multimodal Embeddings G1`

## 🚀 部署步骤

### 步骤 1: 克隆代码
```bash
git clone <repository-url>
cd aws-multimodal-embedding
```

### 步骤 2: 配置项目
编辑 `config/settings.py`，修改服务前缀：
```python
SERVICE_PREFIX = "your-project-name"  # 替换为你的项目名称
```

### 步骤 3: 安装依赖
```bash
# 安装CDK依赖
cd infrastructure
npm install

# 安装Python依赖
pip3 install -r requirements.txt

# 构建OpenSearch Layer
cd ../backend/layers/opensearch_layer
mkdir -p python
pip3 install opensearch-py==2.8.0 -t python/
cd ../../../
```

### 步骤 4: 配置AWS凭证
```bash
# 方式1: 使用AWS CLI配置
aws configure

# 方式2: 使用环境变量
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_DEFAULT_REGION=us-east-1
```

### 步骤 5: 部署基础设施
```bash
cd infrastructure

# 初始化CDK (首次部署)
cdk bootstrap

# 部署堆栈
cdk deploy --require-approval never
```

部署完成后，记录输出的重要信息：
- `CloudFrontDomainName`: 前端访问域名
- `ApiGatewayEndpoint`: API网关端点
- `SearchApiEndpoint`: 搜索API端点
- `OpenSearchEndpoint`: OpenSearch端点

### 步骤 6: 上传前端文件
```bash
# 获取前端存储桶名称
FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name your-project-name-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`FrontendBucketName`].OutputValue' \
  --output text)

# 上传前端文件
aws s3 cp frontend/ s3://$FRONTEND_BUCKET/ --recursive
```

### 步骤 7: 更新搜索页面API端点
编辑 `frontend/search.html`，更新搜索API端点：
```javascript
// 替换为实际的搜索API端点
const response = await fetch('https://your-search-api-id.execute-api.us-east-1.amazonaws.com/prod/', {
```

重新上传搜索页面：
```bash
aws s3 cp frontend/search.html s3://$FRONTEND_BUCKET/search.html
```

## 🧪 验证部署

### 1. 访问前端
打开浏览器访问CloudFront域名：
- 上传页面: `https://your-cloudfront-domain.cloudfront.net/upload.html`
- 搜索页面: `https://your-cloudfront-domain.cloudfront.net/search.html`

### 2. 测试上传功能
1. 访问上传页面
2. 选择一张图片文件
3. 点击上传，确认成功

### 3. 测试搜索功能
1. 访问搜索页面
2. 选择一张图片文件
3. 点击搜索，查看相似图片结果

### 4. 检查日志
```bash
# 检查embedding处理日志
aws logs tail /aws/lambda/your-project-name-embedding --follow

# 检查搜索日志
aws logs tail /aws/lambda/your-project-name-search --follow
```

## 🔧 故障排除

### 常见问题

#### 1. Bedrock权限错误
```
ValidationException: Could not access bedrock service
```
**解决方案**: 确保在Bedrock控制台启用了Titan模型访问权限

#### 2. OpenSearch连接失败
```
ConnectionError: Connection refused
```
**解决方案**: 检查OpenSearch集合状态，确保为ACTIVE状态

#### 3. Lambda超时
```
Task timed out after X seconds
```
**解决方案**: 增加Lambda超时时间或优化代码

#### 4. S3权限错误
```
AccessDenied: Access Denied
```
**解决方案**: 检查IAM角色权限配置

### 调试命令
```bash
# 查看堆栈状态
cdk diff
cdk ls

# 查看CloudFormation事件
aws cloudformation describe-stack-events --stack-name your-project-name-stack

# 查看Lambda函数
aws lambda list-functions --query 'Functions[?contains(FunctionName, `your-project-name`)]'

# 查看OpenSearch集合
aws opensearchserverless list-collections
```

## 🗑️ 清理资源

删除所有AWS资源：
```bash
cd infrastructure
cdk destroy --force
```

**注意**: 这将删除所有数据，包括上传的文件和向量数据。

## 📊 成本估算

基于中等使用量的月度成本估算：
- **Lambda**: $5-20 (基于调用次数)
- **API Gateway**: $3-10 (基于请求数)
- **S3**: $1-5 (基于存储量)
- **CloudFront**: $1-3 (基于流量)
- **OpenSearch Serverless**: $50-100 (基于索引大小)
- **Bedrock**: $0.1-1 (基于embedding调用)

**总计**: 约 $60-140/月

## 🔒 安全建议

1. **启用CloudTrail**: 记录API调用
2. **配置VPC**: 将Lambda放入私有子网
3. **使用WAF**: 保护API Gateway
4. **启用加密**: S3和OpenSearch数据加密
5. **最小权限**: 精确配置IAM权限

## 📈 扩展建议

1. **添加认证**: 集成Cognito用户池
2. **批量处理**: 使用SQS队列处理大量文件
3. **监控告警**: 配置CloudWatch告警
4. **多区域**: 部署到多个AWS区域
5. **缓存优化**: 使用ElastiCache缓存搜索结果

## 📞 支持

如遇到问题，请检查：
1. AWS服务限制和配额
2. 区域服务可用性
3. IAM权限配置
4. 网络连接状态

---

**版本**: 1.0  
**更新时间**: 2025年1月  
**兼容性**: AWS CDK v2, Python 3.11+