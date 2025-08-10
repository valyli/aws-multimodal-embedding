# 基于Amazon Bedrock的TwelveLabs Marengo Embed 2.7多模态搜索系统

基于AWS无服务器架构的多模态搜索应用，使用Amazon Bedrock + TwelveLabs Marengo Embed 2.7 + OpenSearch + Lambda + S3 + CloudFront。本项目完全通过AI辅助开发实现，展示了跨模态AI搜索的强大能力。

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
- ✅ 统一1024维向量空间，支持跨模态搜索
- ✅ 完全AI辅助开发，零手工编码

## 相关文档
- [详细部署指南](DEPLOYMENT_CN.md)
- [中文技术博客](BLOG_POST_PROFESSIONAL_CN.md)


## 测试素材资源

为了充分测试多模态搜索功能，可以从以下AWS官方资源获取高质量的测试素材：

### 图片素材
- **Amazon Nova Canvas示例**: https://www.amazon.science/blog/amazon-nova-canvas-examples
- **Nova Creative创意素材**: https://aws.amazon.com/ai/generative-ai/nova/creative/
- **Nova Canvas视觉指南**: https://aws.amazon.com/blogs/machine-learning/exploring-creative-possibilities-a-visual-guide-to-amazon-nova-canvas/

### 视频素材
- **Luma AI Ray 2视频模型示例**: https://aws.amazon.com/blogs/aws/luma-ai-ray-2-video-model-is-now-available-in-amazon-bedrock/

这些资源提供了丰富的多模态内容，非常适合测试TwelveLabs Marengo Embed 2.7的跨模态搜索能力。