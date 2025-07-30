# 跨区域部署指南

本文档提供在不同 AWS 区域部署多模态搜索系统的详细步骤。

## 🌍 支持的区域

系统支持部署到任何支持以下服务的 AWS 区域：
- Amazon Bedrock (TwelveLabs Marengo Embed 2.7)
- OpenSearch Serverless
- Lambda
- API Gateway
- S3
- CloudFront

## 🚀 快速部署步骤

### 1. 设置目标区域

选择以下任一方式设置新的部署区域：

#### 方法 A: 环境变量（推荐）
```bash
export AWS_REGION=us-west-2
```

#### 方法 B: AWS CLI 配置
```bash
aws configure set region us-west-2
```

#### 方法 C: 临时设置
```bash
AWS_REGION=us-west-2 ./deploy.sh
```

### 2. 修改服务前缀（避免资源冲突）

编辑 `config/settings.py`：
```python
SERVICE_PREFIX = "multimodal-usw2"  # 建议包含区域标识
```

### 3. 执行部署

```bash
./deploy.sh
```

## 📋 详细部署流程

### 前置检查

部署脚本会自动检查：
- ✅ AWS CLI 安装和配置
- ✅ Node.js 18+ 环境
- ✅ Python 3.11+ 环境
- ✅ AWS CDK v2 安装
- ✅ AWS 凭证有效性

### 自动化步骤

1. **读取配置**: 自动获取 SERVICE_PREFIX 和 AWS_REGION
2. **构建依赖**: 创建 OpenSearch Layer
3. **CDK Bootstrap**: 初始化 CDK 环境（首次部署）
4. **基础设施部署**: 创建所有 AWS 资源
5. **前端上传**: 部署静态网站到 S3
6. **配置更新**: 自动更新 API 端点

### 部署输出

部署完成后会显示：
```
🎉 部署完成！

📱 访问地址:
   上传页面: https://d1234567890.cloudfront.net/upload.html
   搜索页面: https://d1234567890.cloudfront.net/search.html

🔗 API端点:
   搜索API: https://abcdef123.execute-api.us-west-2.amazonaws.com/prod/
```

## 🔧 区域特定配置

### TwelveLabs Marengo 模型可用性

确认目标区域支持 TwelveLabs Marengo Embed 2.7 模型：

```bash
aws bedrock list-foundation-models \
  --region us-west-2 \
  --query 'modelSummaries[?contains(modelId, `twelvelabs.marengo`)]'
```

### OpenSearch Serverless 支持

验证区域支持 OpenSearch Serverless：

```bash
aws opensearchserverless list-collections --region us-west-2
```

## 🌐 多区域部署策略

### 场景 1: 完全独立部署

每个区域使用不同的服务前缀：

```bash
# 美东部署
export AWS_REGION=us-east-1
export SERVICE_PREFIX=multimodal-use1
./deploy.sh

# 美西部署
export AWS_REGION=us-west-2
export SERVICE_PREFIX=multimodal-usw2
./deploy.sh
```

### 场景 2: 灾备部署

主区域和备份区域使用相同配置：

```bash
# 主区域
export AWS_REGION=us-east-1
export SERVICE_PREFIX=multimodal-prod
./deploy.sh

# 备份区域
export AWS_REGION=us-west-2
export SERVICE_PREFIX=multimodal-prod-backup
./deploy.sh
```

## 🔍 部署验证

### 1. 检查基础设施

```bash
# 验证 CloudFormation 栈
aws cloudformation describe-stacks \
  --stack-name ${SERVICE_PREFIX}-stack \
  --region ${AWS_REGION}

# 检查 Lambda 函数
aws lambda list-functions \
  --region ${AWS_REGION} \
  --query 'Functions[?contains(FunctionName, `'${SERVICE_PREFIX}'`)]'
```

### 2. 测试 OpenSearch 连接

```bash
python scripts/test_opensearch.py
```

### 3. 验证前端访问

访问部署输出中的 CloudFront 域名，测试：
- 文件上传功能
- 搜索功能
- API 响应

## ⚠️ 注意事项

### 区域限制

1. **Bedrock 模型可用性**: 确认目标区域支持 TwelveLabs 模型
2. **服务配额**: 检查区域内的服务限制
3. **数据驻留**: 考虑数据本地化要求

### 成本考虑

1. **跨区域传输**: 避免不必要的跨区域数据传输
2. **资源定价**: 不同区域的服务定价可能不同
3. **CloudFront**: 全球分发网络的成本影响

### 安全配置

1. **IAM 权限**: 确保在目标区域有足够权限
2. **VPC 配置**: 如需要，配置区域特定的网络设置
3. **加密密钥**: 使用区域特定的 KMS 密钥

## 🛠️ 故障排除

### 常见问题

#### 1. CDK Bootstrap 失败
```bash
# 手动 bootstrap
cdk bootstrap aws://ACCOUNT-ID/REGION-NAME
```

#### 2. Bedrock 模型访问被拒绝
```bash
# 检查模型访问权限
aws bedrock get-model-invocation-logging-configuration --region ${AWS_REGION}
```

#### 3. OpenSearch 集合创建失败
```bash
# 检查服务配额
aws service-quotas get-service-quota \
  --service-code aoss \
  --quota-code L-8A6B6B1D \
  --region ${AWS_REGION}
```

### 日志查看

```bash
# Lambda 日志
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/${SERVICE_PREFIX}" \
  --region ${AWS_REGION}

# CloudFormation 事件
aws cloudformation describe-stack-events \
  --stack-name ${SERVICE_PREFIX}-stack \
  --region ${AWS_REGION}
```

## 🗑️ 清理资源

### 单区域清理

```bash
cd infrastructure
cdk destroy --region ${AWS_REGION}
```

### 多区域清理

```bash
# 清理所有区域的资源
for region in us-east-1 us-west-2 eu-west-1; do
  echo "清理区域: $region"
  AWS_REGION=$region cdk destroy --require-approval never
done
```

## 📚 相关文档

- [主部署文档](DEPLOYMENT.md)
- [系统架构说明](README.md)
- [AWS CDK 文档](https://docs.aws.amazon.com/cdk/)
- [Amazon Bedrock 区域支持](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html#bedrock-regions)

## 🆘 技术支持

如遇到跨区域部署问题：

1. 检查 AWS 服务状态页面
2. 验证区域服务可用性
3. 查看 CloudWatch 日志
4. 确认 IAM 权限配置

---

*最后更新: 2025-01-25*