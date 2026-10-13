#!/bin/bash
set -e

APP_NAME="cicd-pipeline"
ENVIRONMENT="dev"
REGION="us-east-1"
CLEANUP=false

for arg in "$@"; do
  case $arg in
    --environment=*) ENVIRONMENT="${arg#*=}" ;;
    --region=*) REGION="${arg#*=}" ;;
    --cleanup) CLEANUP=true ;;
  esac
done

STACK_NAME="${APP_NAME}-${ENVIRONMENT}"

if [ "$CLEANUP" = true ]; then
  echo "Deleting stack $STACK_NAME..."
  aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$REGION"
  echo "Stack deletion initiated."
  exit 0
fi

echo "Deploying $STACK_NAME to $REGION..."

aws cloudformation deploy \
  --template-file infrastructure/pipeline.yaml \
  --stack-name "$STACK_NAME" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION" \
  --parameter-overrides \
    AppName="$APP_NAME" \
    Environment="$ENVIRONMENT"

echo "Deployment complete."
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs"
