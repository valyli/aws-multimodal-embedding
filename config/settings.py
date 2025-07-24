import os

# 服务前缀配置 - 修改此处即可部署新实例
SERVICE_PREFIX = os.getenv("SERVICE_PREFIX", "cloudscape-demo")

# AWS资源命名
LAMBDA_FUNCTION_NAME = f"{SERVICE_PREFIX}-api"
API_GATEWAY_NAME = f"{SERVICE_PREFIX}-api-gateway"
S3_BUCKET_NAME = f"{SERVICE_PREFIX}-frontend"
CLOUDFRONT_DISTRIBUTION_NAME = f"{SERVICE_PREFIX}-cdn"

# 环境配置
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")