# AWS Cloudscape 程序

基于AWS无服务器架构的Cloudscape应用，使用API Gateway + Lambda (FastAPI) + S3 + CloudFront。

## 快速开始

### 1. 配置服务前缀
编辑 `config/settings.py` 修改 `SERVICE_PREFIX` 变量：
```python
SERVICE_PREFIX = "your-project-name"
```

### 2. 部署
```bash
./deploy.sh
```

### 3. 上传前端
部署完成后，将 `frontend/build/` 目录内容上传到创建的S3存储桶。

## 项目结构
```
├── config/settings.py          # 配置文件
├── backend/                    # FastAPI后端
├── frontend/                   # React前端
├── infrastructure/             # CDK基础设施
└── deploy.sh                   # 部署脚本
```

## 自定义配置
- 修改 `SERVICE_PREFIX` 即可部署新实例
- 支持环境变量 `SERVICE_PREFIX` 和 `AWS_REGION`
- 所有AWS资源自动添加前缀命名

## 架构特点
- ✅ 完全无服务器，无EC2暴露
- ✅ 使用Python CDK管理基础设施
- ✅ 支持多环境部署
- ✅ 代码高度可复用