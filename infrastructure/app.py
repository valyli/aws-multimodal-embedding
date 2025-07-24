#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.cloudscape_stack import CloudscapeStack
import sys
import os

# 添加配置路径
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))
from config.settings import SERVICE_PREFIX, AWS_REGION

app = cdk.App()

CloudscapeStack(
    app, 
    f"{SERVICE_PREFIX}-stack",
    env=cdk.Environment(region=AWS_REGION)
)

app.synth()