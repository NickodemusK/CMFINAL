# Nickodemus made this file and code
import os
import boto3

aws_region = os.getenv("AWS_REGION", "us-east-2")

# Let boto3 resolve credentials from the environment/instance role chain.
# This works on Elastic Beanstalk with the EC2 instance profile and avoids
# hard coupling to static access keys.
s3 = boto3.client("s3", region_name=aws_region)

BUCKET_NAME = os.getenv("BUCKET_NAME")
AWS_REGION = aws_region
