# AWS 多模态搜索系统部署文档

## 系统概述

基于 AWS 无服务器架构的多模态搜索系统，支持图片、视频和文本的智能搜索。使用 TwelveLabs Marengo 模型进行多模态 embedding 生成，OpenSearch 进行向量搜索。

## 架构组件

- **前端**: React 静态网站 (CloudFront + S3)
- **API**: API Gateway + Lambda (FastAPI)
- **存储**: S3 (文件存储)
- **搜索**: OpenSearch Serverless (向量搜索)
- **队列**: SQS (异步任务处理)
- **数据库**: DynamoDB (搜索状态管理)
- **AI模型**: Amazon Bedrock (TwelveLabs Marengo)

## 前置要求

### 1. 环境准备
```bash
# Node.js 18+
node --version

# AWS CLI v2
aws --version

# Python 3.11+
python3 --version

# AWS CDK v2
npm install -g aws-cdk
cdk --version
```

### 2. AWS 权限配置
```bash
# 配置 AWS 凭证
aws configure

# 验证权限
aws sts get-caller-identity
```

### 3. 必需的 AWS 服务权限
- Amazon Bedrock (TwelveLabs Marengo 模型访问)
- OpenSearch Serverless
- Lambda
- API Gateway
- S3
- CloudFront
- DynamoDB
- SQS

## 部署步骤

### 1. 克隆项目
```bash
git clone <repository-url>
cd aws-multimodal-embedding
```

### 2. 配置服务前缀
编辑 `config/settings.py`:
```python
SERVICE_PREFIX = "your-project-name"  # 修改为你的项目名
```

### 3. 安装依赖
```bash
# CDK 依赖
cd infrastructure
npm install

# Python 依赖 (如果需要本地测试)
pip install -r requirements.txt
```

### 4. 部署基础设施
```bash
# 在 infrastructure 目录下
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
cdk bootstrap  # 首次部署需要
cdk deploy --require-approval never
```

### 5. 上传前端文件
```bash
# 部署完成后，上传前端到 S3
aws s3 sync frontend/ s3://your-project-name-frontend/ --delete
```

## 配置说明

### 环境变量
系统会自动设置以下环境变量：
- `OPENSEARCH_ENDPOINT`: OpenSearch 集群端点
- `OPENSEARCH_INDEX`: 索引名称 (默认: embeddings)
- `SEARCH_TABLE_NAME`: DynamoDB 表名
- `SEARCH_QUEUE_URL`: SQS 队列 URL

### 服务配置
- **Lambda 超时**: 15分钟 (embedding 处理)
- **Lambda 内存**: 1024MB
- **SQS 可见性超时**: 900秒
- **文件大小限制**: 10MB
- **支持格式**: PNG, JPEG, JPG, WEBP, MP4, MOV

## 功能特性

### 1. 多模态 Embedding
- **图片**: 生成视觉 embedding
- **视频**: 生成视觉、文本、音频三种 embedding
- **文本**: 生成文本 embedding

### 2. 搜索模式
- **文件搜索**: 上传图片/视频搜索相似内容
- **文本搜索**: 输入文本描述搜索相关内容
- **视频搜索模式**: 视觉相似/语义相似/音频相似

### 3. 异步处理
- 避免 CloudFront 超时
- 实时状态更新
- 后台队列处理

## 使用指南

### 1. 文件上传
1. 访问 CloudFront 域名
2. 选择"文件上传"
3. 上传图片或视频文件
4. 系统自动生成 embedding

### 2. 搜索功能
1. 选择"异步搜索"
2. 选择搜索类型：
   - **文件搜索**: 上传文件查找相似内容
   - **文本搜索**: 输入描述查找相关内容
3. 对于视频文件，可选择搜索模式
4. 查看搜索结果和相似度分数

## 故障排除

### 1. 部署失败
```bash
# 检查 CDK 版本
cdk --version

# 清理并重新部署
cdk destroy
cdk deploy --require-approval never
```

### 2. Embedding 处理失败
- 检查文件格式和大小限制
- 验证 Bedrock 模型访问权限
- 查看 Lambda 日志：
```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/your-project-name"
```

### 3. 搜索无结果
- 确认文件已成功处理 (检查 OpenSearch 索引)
- 验证搜索参数
- 检查 OpenSearch 集群状态

### 4. 前端访问问题
- 确认 CloudFront 分发状态
- 检查 S3 存储桶策略
- 验证 API Gateway 端点

## 监控和日志

### 1. CloudWatch 日志组
- `/aws/lambda/your-project-name-embedding`
- `/aws/lambda/your-project-name-search-api`
- `/aws/lambda/your-project-name-search-worker`

### 2. 关键指标
- Lambda 执行时间和错误率
- SQS 队列��度
- OpenSearch 查询性能
- S3 存储使用量

## 成本优化

### 1. 资源配置
- Lambda 内存根据实际需求调整
- OpenSearch 实例类型优化
- S3 生命周期策略

### 2. 使用建议
- 合理控制文件大小
- 定期清理临时文件
- 监控 Bedrock 调用量

## 安全考虑

### 1. 访问控制
- IAM 角色最小权限原则
- API Gateway 访问控制
- S3 存储桶策略

### 2. 数据保护
- 传输加密 (HTTPS)
- 存储加密 (S3, OpenSearch)
- 临时文件自动清理

## 扩展和定制

### 1. 添加新的文件格式
修改 `backend/embedding/main.py` 中的文件类型检查

### 2. 调整搜索算法
修改 `backend/search_worker/main.py` 中的搜索逻辑

### 3. 自定义前端界面
修改 `frontend/` 目录下的 HTML/CSS/JS 文件

## 技术支持

如遇到问题，请检查：
1. AWS 服务状态
2. CloudWatch 日志
3. 系统配置
4. 网络连接

## 版本信息

- **当前版本**: 1.0.0
- **最后更新**: 2025-01-25
- **兼容性**: AWS CDK v2, Node.js 18+, Python 3.11+