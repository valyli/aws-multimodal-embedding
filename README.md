# TwelveLabs Marengo Embed 2.7 Multimodal Search System on Amazon Bedrock

A multimodal search application based on AWS serverless architecture, using Amazon Bedrock + TwelveLabs Marengo Embed 2.7 + OpenSearch + Lambda + S3 + CloudFront. This project was implemented entirely through AI-assisted development, demonstrating the powerful capabilities of cross-modal AI search.

## Quick Start

### 1. Configure Service Prefix
Edit `config/settings.py` to modify the `SERVICE_PREFIX` variable:
```python
SERVICE_PREFIX = "your-project-name"
```

### 2. Deploy
```bash
./deploy.sh
```

### 3. Upload Frontend
After deployment, upload the contents of the `frontend/build/` directory to the created S3 bucket.

## Project Structure
```
├── config/settings.py          # Configuration file
├── backend/                    # FastAPI backend
├── frontend/                   # React frontend
├── infrastructure/             # CDK infrastructure
└── deploy.sh                   # Deployment script
```

## Custom Configuration
- Modify `SERVICE_PREFIX` to deploy new instances
- Supports environment variables `SERVICE_PREFIX` and `AWS_REGION`
- All AWS resources automatically prefixed with naming

## Architecture Features
- ✅ Fully serverless, no EC2 exposure
- ✅ Infrastructure managed with Python CDK
- ✅ Multi-environment deployment support
- ✅ Highly reusable code
- ✅ Unified 1024-dimensional vector space supporting cross-modal search
- ✅ Completely AI-assisted development with zero manual coding

## Related Documentation
- [Detailed Deployment Guide](DEPLOYMENT.md)
- [English Technical Blog](BLOG_POST_PROFESSIONAL.md)

## Test Material Resources

To fully test multimodal search functionality, you can obtain high-quality test materials from the following AWS official resources:

### Image Materials
- **Amazon Nova Canvas Examples**: https://www.amazon.science/blog/amazon-nova-canvas-examples
- **Nova Creative Materials**: https://aws.amazon.com/ai/generative-ai/nova/creative/
- **Nova Canvas Visual Guide**: https://aws.amazon.com/blogs/machine-learning/exploring-creative-possibilities-a-visual-guide-to-amazon-nova-canvas/

### Video Materials
- **Luma AI Ray 2 Video Model Examples**: https://aws.amazon.com/blogs/aws/luma-ai-ray-2-video-model-is-now-available-in-amazon-bedrock/

These resources provide rich multimodal content, perfect for testing the cross-modal search capabilities of TwelveLabs Marengo Embed 2.7.