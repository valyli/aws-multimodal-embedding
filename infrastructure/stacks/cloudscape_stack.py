from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_apigateway as apigateway,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3_notifications as s3n,
    aws_opensearchserverless as opensearch,
    aws_iam as iam,
    Duration,
    RemovalPolicy
)
from constructs import Construct
import sys
import os
import json

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
            timeout=Duration.seconds(129),
            memory_size=512
        )

        # API Gateway使用5分钟超时
        api = apigateway.RestApi(
            self, "ApiGateway",
            rest_api_name=API_GATEWAY_NAME,
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["*"],
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["*"],
                allow_credentials=True
            )
        )
        
        api_integration = apigateway.LambdaIntegration(
            lambda_function,
            proxy=True,
            timeout=Duration.seconds(129)  # 129秒超时
        )
        
        api_resource = api.root.add_resource("{proxy+}")
        api_resource.add_method("ANY", api_integration)

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
        
        # 创建OpenSearch Layer
        opensearch_layer = _lambda.LayerVersion(
            self, "OpenSearchLayer",
            code=_lambda.Code.from_asset("../backend/layers/opensearch_layer"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
            layer_version_name=f"{SERVICE_PREFIX}-opensearch"
        )
        
        # Embedding处理Lambda
        embedding_function = _lambda.Function(
            self, "EmbeddingFunction",
            function_name=f"{SERVICE_PREFIX}-embedding",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="main.handler",
            code=_lambda.Code.from_asset("../backend/embedding"),
            timeout=Duration.minutes(5),
            memory_size=1024,
            layers=[opensearch_layer]
        )
        
        # 搜索Lambda
        search_function = _lambda.Function(
            self, "SearchFunction",
            function_name=f"{SERVICE_PREFIX}-search",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="main.handler",
            code=_lambda.Code.from_asset("../backend/search"),
            timeout=Duration.seconds(129),
            memory_size=1024,
            layers=[opensearch_layer]
        )
        
        # OpenSearch Serverless安全策略
        encryption_policy = opensearch.CfnSecurityPolicy(
            self, "EncryptionPolicy",
            name="mm-embed-vector-encrypt",
            type="encryption",
            policy=json.dumps({
                "Rules": [{
                    "ResourceType": "collection",
                    "Resource": ["collection/mm-embed-vector"]
                }],
                "AWSOwnedKey": True
            })
        )
        
        network_policy = opensearch.CfnSecurityPolicy(
            self, "NetworkPolicy",
            name="mm-embed-vector-network",
            type="network",
            policy=json.dumps([{
                "Rules": [{
                    "ResourceType": "collection",
                    "Resource": ["collection/mm-embed-vector"]
                }],
                "AllowFromPublic": True
            }])
        )
        
        # OpenSearch Serverless集合
        opensearch_collection = opensearch.CfnCollection(
            self, "OpenSearchCollection",
            name="mm-embed-vector",
            type="VECTORSEARCH"
        )
        
        opensearch_collection.add_dependency(encryption_policy)
        opensearch_collection.add_dependency(network_policy)
        
        # 数据访问策略
        data_policy = opensearch.CfnAccessPolicy(
            self, "DataAccessPolicy",
            name="mm-embed-vector-access",
            type="data",
            policy=json.dumps([{
                "Rules": [{
                    "ResourceType": "index",
                    "Resource": ["index/mm-embed-vector/*"],
                    "Permission": ["aoss:*"]
                }, {
                    "ResourceType": "collection",
                    "Resource": ["collection/mm-embed-vector"],
                    "Permission": ["aoss:*"]
                }],
                "Principal": [f"arn:aws:iam::{self.account}:root"]
            }])
        )
        
        data_policy.add_dependency(opensearch_collection)
        
        # 为Lambda添加环境变量
        embedding_function.add_environment("OPENSEARCH_ENDPOINT", opensearch_collection.attr_collection_endpoint)
        embedding_function.add_environment("OPENSEARCH_INDEX", "embeddings")
        
        search_function.add_environment("OPENSEARCH_ENDPOINT", opensearch_collection.attr_collection_endpoint)
        search_function.add_environment("OPENSEARCH_INDEX", "embeddings")
        
        # 给Embedding Lambda授权
        # 给Lambda授权
        for func in [embedding_function, search_function]:
            func.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "bedrock:InvokeModel",
                        "bedrock:StartAsyncInvoke",
                        "bedrock:GetAsyncInvoke"
                    ],
                    resources=["*"]
                )
            )
            
            # 给Lambda角色添加S3完整访问权限
            func.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:ListBucket",
                        "s3:GetBucketLocation"
                    ],
                    resources=[
                        upload_bucket.bucket_arn,
                        f"{upload_bucket.bucket_arn}/*"
                    ]
                )
            )
            
            func.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["aoss:*"],
                    resources=["*"]
                )
            )
            
            func.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["sts:GetCallerIdentity"],
                    resources=["*"]
                )
            )
            
            func.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "iam:PassRole"
                    ],
                    resources=["*"]
                )
            )
        
        upload_bucket.grant_read(embedding_function)
        upload_bucket.grant_write(search_function)
        upload_bucket.grant_read(search_function)
        
        # 为Bedrock创建服务角色
        bedrock_service_role = iam.Role(
            self, "BedrockServiceRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            inline_policies={
                "S3Access": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:GetObject",
                                "s3:PutObject",
                                "s3:DeleteObject",
                                "s3:ListBucket"
                            ],
                            resources=[
                                upload_bucket.bucket_arn,
                                f"{upload_bucket.bucket_arn}/*"
                            ]
                        )
                    ]
                )
            }
        )
        
        # 为Lambda添加Bedrock服务角色ARN环境变量
        for func in [embedding_function, search_function]:
            func.add_environment("BEDROCK_SERVICE_ROLE_ARN", bedrock_service_role.role_arn)
        
        # S3触发器
        upload_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(embedding_function)
        )
        
        # 搜索API使用129秒超时
        search_api = apigateway.RestApi(
            self, "SearchApi",
            rest_api_name=f"{API_GATEWAY_NAME}-search",
            cloud_watch_role=True,
            deploy_options=apigateway.StageOptions(
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
                metrics_enabled=True
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["*"],
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["*"],
                allow_credentials=True
            )
        )
        
        search_integration = apigateway.LambdaIntegration(
            search_function,
            proxy=True,
            timeout=Duration.seconds(129)
        )
        
        # 在根路径添加方法
        search_api.root.add_method("ANY", search_integration)
        
        # 在proxy路径添加方法
        search_resource = search_api.root.add_resource("{proxy+}")
        search_resource.add_method("ANY", search_integration)
        


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
                ),
                "/search/*": cloudfront.BehaviorOptions(
                    origin=origins.RestApiOrigin(search_api),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED
                )
            }
        )
        
        # 输出信息
        from aws_cdk import CfnOutput
        CfnOutput(
            self, "CloudFrontDomainName",
            value=distribution.distribution_domain_name,
            description="CloudFront Distribution Domain Name"
        )
        
        CfnOutput(
            self, "OpenSearchEndpoint",
            value=opensearch_collection.attr_collection_endpoint,
            description="OpenSearch Serverless Collection Endpoint"
        )
        
        CfnOutput(
            self, "SearchApiEndpoint",
            value=search_api.url,
            description="Search API Gateway Endpoint"
        )