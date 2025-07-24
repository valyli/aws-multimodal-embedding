from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_apigateway as apigateway,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    Duration,
    RemovalPolicy
)
from constructs import Construct
import sys
import os

# 添加配置路径
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))
from config.settings import (
    LAMBDA_FUNCTION_NAME,
    API_GATEWAY_NAME,
    S3_BUCKET_NAME,
    CLOUDFRONT_DISTRIBUTION_NAME,
    SERVICE_PREFIX
)

class CloudscapeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Lambda函数
        lambda_function = _lambda.Function(
            self, "ApiFunction",
            function_name=LAMBDA_FUNCTION_NAME,
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="main.handler",
            code=_lambda.Code.from_asset("../backend/app"),
            timeout=Duration.seconds(30),
            memory_size=512
        )

        # API Gateway
        api = apigateway.LambdaRestApi(
            self, "ApiGateway",
            rest_api_name=API_GATEWAY_NAME,
            handler=lambda_function,
            proxy=True,
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["*"]
            )
        )

        # S3存储桶（私有）
        frontend_bucket = s3.Bucket(
            self, "FrontendBucket",
            bucket_name=S3_BUCKET_NAME,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )
        
        # 文件上传存储桶
        upload_bucket = s3.Bucket(
            self, "UploadBucket",
            bucket_name=f"{SERVICE_PREFIX}-uploads",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )
        
        # 给Lambda授权访问上传存储桶
        upload_bucket.grant_write(lambda_function)

        # CloudFront Origin Access Identity
        oai = cloudfront.OriginAccessIdentity(
            self, "OAI",
            comment=f"OAI for {S3_BUCKET_NAME}"
        )
        
        # 授权CloudFront访问S3
        frontend_bucket.grant_read(oai)
        
        # CloudFront分发
        distribution = cloudfront.Distribution(
            self, "Distribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    frontend_bucket,
                    origin_access_identity=oai
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.from_cache_policy_id(
                    self, "DevCachePolicy",
                    "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"  # CachingDisabled
                )
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=origins.RestApiOrigin(api),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED
                )
            }
        )
        
        # 输出CloudFront域名
        from aws_cdk import CfnOutput
        CfnOutput(
            self, "CloudFrontDomainName",
            value=distribution.distribution_domain_name,
            description="CloudFront Distribution Domain Name"
        )