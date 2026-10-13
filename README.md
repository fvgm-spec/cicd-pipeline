# CI/CD Pipeline to Deploy Applications on AWS

A complete CI/CD pipeline using AWS CodePipeline, CodeBuild, and CodeDeploy to automate the build, test, and deployment of applications on AWS.

## Architecture Overview

This project implements a fully automated CI/CD pipeline:

- **CodePipeline**: Orchestrates the end-to-end pipeline stages
- **CodeBuild**: Builds and tests the application
- **CodeDeploy**: Deploys the application to EC2 / ECS / Lambda
- **S3**: Stores pipeline artifacts
- **IAM**: Manages permissions across pipeline stages
- **CloudWatch**: Monitors pipeline executions and application health

## Pipeline Stages

1. **Source**: Triggered by a push to the GitHub/CodeCommit repository
2. **Build**: CodeBuild compiles code, runs tests, and packages artifacts
3. **Deploy (Staging)**: Deploys to staging environment for validation
4. **Approval**: Manual approval gate before production
5. **Deploy (Production)**: Deploys to production environment

## Prerequisites

- AWS CLI configured with appropriate permissions
- An existing application repository (GitHub or CodeCommit)
- Python 3.9 or later

## Quick Start

```bash
# Clone the repository
git clone <repository-url>
cd cicd_pipeline

# Deploy the pipeline infrastructure
./deploy.sh
```

## Configuration

### Environment Variables

- `APP_NAME`: Application name
- `ENVIRONMENT`: Target environment (staging, prod)
- `GITHUB_REPO`: Source repository URL
- `GITHUB_BRANCH`: Branch to trigger the pipeline

### Deployment Options

```bash
# Deploy to staging
./deploy.sh --environment staging

# Deploy to production
./deploy.sh --environment prod

# Tear down
./deploy.sh --cleanup
```

## Monitoring

- **CodePipeline Console**: Track pipeline execution status
- **CloudWatch Logs**: View CodeBuild build logs
- **CloudWatch Alarms**: Get notified on pipeline failures

## Security Best Practices

- Least privilege IAM roles per pipeline stage
- Secrets stored in AWS Secrets Manager / Parameter Store
- Artifacts encrypted at rest in S3

## Related Resources

- [AWS CodePipeline Documentation](https://docs.aws.amazon.com/codepipeline/)
- [AWS CodeBuild Documentation](https://docs.aws.amazon.com/codebuild/)
- [AWS CodeDeploy Documentation](https://docs.aws.amazon.com/codedeploy/)
