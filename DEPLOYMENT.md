# AWS Multimodal Search System Deployment Guide

## System Overview

A multimodal search system based on AWS serverless architecture that supports intelligent search across images, videos, and text. Uses TwelveLabs Marengo model for multimodal embedding generation and OpenSearch for vector search.

## Architecture Components

- **Frontend**: React static website (CloudFront + S3)
- **API**: API Gateway + Lambda (FastAPI)
- **Storage**: S3 (file storage)
- **Search**: OpenSearch Serverless (vector search)
- **Queue**: SQS (asynchronous task processing)
- **Database**: DynamoDB (search status management)
- **AI Model**: Amazon Bedrock (TwelveLabs Marengo)

## Prerequisites

### 1. Environment Setup
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

### 2. AWS Credentials Configuration
```bash
# Configure AWS credentials
aws configure

# Verify permissions
aws sts get-caller-identity
```

### 3. Required AWS Service Permissions
- Amazon Bedrock (TwelveLabs Marengo model access)
- OpenSearch Serverless
- Lambda
- API Gateway
- S3
- CloudFront
- DynamoDB
- SQS

## Deployment Steps

### 1. Clone Project
```bash
git clone <repository-url>
cd aws-multimodal-embedding
```

### 2. Configure Service Prefix
Edit `config/settings.py`:
```python
SERVICE_PREFIX = "your-project-name"  # Change to your project name
```

### 3. Install Dependencies
```bash
# CDK dependencies
cd infrastructure
npm install

# Python dependencies (if needed for local testing)
pip install -r requirements.txt
```

### 4. Deploy Infrastructure
```bash
# In infrastructure directory
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
cdk bootstrap  # Required for first deployment
cdk deploy --require-approval never
```

### 5. Upload Frontend Files
```bash
# After deployment, upload frontend to S3
aws s3 sync frontend/ s3://your-project-name-frontend/ --delete
```

## Configuration Details

### Environment Variables
The system automatically sets the following environment variables:
- `OPENSEARCH_ENDPOINT`: OpenSearch cluster endpoint
- `OPENSEARCH_INDEX`: Index name (default: embeddings)
- `SEARCH_TABLE_NAME`: DynamoDB table name
- `SEARCH_QUEUE_URL`: SQS queue URL

### Service Configuration
- **Lambda Timeout**: 15 minutes (embedding processing)
- **Lambda Memory**: 1024MB
- **SQS Visibility Timeout**: 900 seconds
- **File Size Limit**: 10MB
- **Supported Formats**: PNG, JPEG, JPG, WEBP, MP4, MOV

## Features

### 1. Multimodal Embedding
- **Images**: Generate visual embeddings
- **Videos**: Generate visual, text, and audio embeddings
- **Text**: Generate text embeddings

### 2. Search Modes
- **File Search**: Upload images/videos to search for similar content
- **Text Search**: Input text descriptions to search for related content
- **Video Search Modes**: Visual similarity/Semantic similarity/Audio similarity

### 3. Asynchronous Processing
- Avoid CloudFront timeouts
- Real-time status updates
- Background queue processing

## Usage Guide

### 1. File Upload
1. Access CloudFront domain
2. Select "File Upload"
3. Upload image or video files
4. System automatically generates embeddings

### 2. Search Functionality
1. Select "Asynchronous Search"
2. Choose search type:
   - **File Search**: Upload files to find similar content
   - **Text Search**: Input descriptions to find related content
3. For video files, select search mode
4. View search results and similarity scores

## Troubleshooting

### 1. Deployment Failures
```bash
# Check CDK version
cdk --version

# Clean and redeploy
cdk destroy
cdk deploy --require-approval never
```

### 2. Embedding Processing Failures
- Check file format and size limits
- Verify Bedrock model access permissions
- View Lambda logs:
```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/your-project-name"
```

### 3. No Search Results
- Confirm files have been successfully processed (check OpenSearch index)
- Verify search parameters
- Check OpenSearch cluster status

### 4. Frontend Access Issues
- Confirm CloudFront distribution status
- Check S3 bucket policies
- Verify API Gateway endpoints

## Monitoring and Logging

### 1. CloudWatch Log Groups
- `/aws/lambda/your-project-name-embedding`
- `/aws/lambda/your-project-name-search-api`
- `/aws/lambda/your-project-name-search-worker`

### 2. Key Metrics
- Lambda execution time and error rates
- SQS queue depth
- OpenSearch query performance
- S3 storage usage

## Cost Optimization

### 1. Resource Configuration
- Adjust Lambda memory based on actual needs
- Optimize OpenSearch instance types
- S3 lifecycle policies

### 2. Usage Recommendations
- Control file sizes reasonably
- Regular cleanup of temporary files
- Monitor Bedrock API calls

## Security Considerations

### 1. Access Control
- IAM roles with least privilege principle
- API Gateway access control
- S3 bucket policies

### 2. Data Protection
- Encryption in transit (HTTPS)
- Encryption at rest (S3, OpenSearch)
- Automatic cleanup of temporary files

## Extensions and Customization

### 1. Adding New File Formats
Modify file type checks in `backend/embedding/main.py`

### 2. Adjusting Search Algorithms
Modify search logic in `backend/search_worker/main.py`

### 3. Customizing Frontend Interface
Modify HTML/CSS/JS files in `frontend/` directory

## Technical Support

If you encounter issues, please check:
1. AWS service status
2. CloudWatch logs
3. System configuration
4. Network connectivity

## Version Information

- **Current Version**: 1.0.0
- **Last Updated**: 2025-01-25
- **Compatibility**: AWS CDK v2, Node.js 18+, Python 3.11+