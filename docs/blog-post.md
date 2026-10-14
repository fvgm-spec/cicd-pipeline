# Building a CI/CD Pipeline to Deploy Applications on AWS

Modern software teams ship code multiple times a day. Manual deployments slow teams down, introduce human error, and make rollbacks painful. In this post, we'll build a fully automated CI/CD pipeline on AWS using CodePipeline, CodeBuild, and CodeDeploy — going from a GitHub push to a production deployment with zero manual steps (except an intentional approval gate).

## The Problem with Manual Deployments

Without a CI/CD pipeline, teams typically face:

1. **Inconsistent Environments**: "It works on my machine" becomes a recurring nightmare.
2. **Slow Release Cycles**: Manual steps bottleneck delivery and delay feedback.
3. **Error-Prone Processes**: Copy-paste deployment steps lead to missed commands and broken releases.
4. **No Audit Trail**: Hard to know who deployed what, when, and why.
5. **Fear of Deploying**: Teams avoid frequent releases because each one is risky.

A CI/CD pipeline solves all of these by automating the path from code commit to production.

## AWS Services Used

- **AWS CodePipeline**: Orchestrates the end-to-end pipeline stages
- **AWS CodeBuild**: Compiles code, runs tests, and packages artifacts
- **AWS CodeDeploy**: Deploys the packaged application to the target compute
- **Amazon S3**: Stores pipeline artifacts between stages
- **AWS IAM**: Manages least-privilege permissions per stage
- **Amazon CloudWatch**: Monitors pipeline executions and application health

## Pipeline Architecture

```
GitHub Push
    │
    ▼
[Source Stage]        ← CodePipeline detects push, pulls source
    │
    ▼
[Build Stage]         ← CodeBuild installs deps, runs tests, packages artifact
    │
    ▼
[Deploy Staging]      ← Artifact deployed to staging environment
    │
    ▼
[Manual Approval]     ← Human gate before production
    │
    ▼
[Deploy Production]   ← Artifact promoted to production
```

## Implementation Deep Dive

### 1. The buildspec.yml — Defining the Build

CodeBuild uses a `buildspec.yml` file to know what to do during the build stage:

```yaml
version: 0.2

phases:
  install:
    runtime-versions:
      python: 3.11
    commands:
      - pip install -r requirements.txt

  pre_build:
    commands:
      - echo "Running tests..."
      - python -m pytest code/tests/ -v

  build:
    commands:
      - echo "Packaging application..."
      - zip -r app.zip code/ --exclude "code/tests/*"

  post_build:
    commands:
      - echo "Build complete."

artifacts:
  files:
    - app.zip
    - infrastructure/**/*
```

The `pre_build` phase runs tests before packaging. If tests fail, the pipeline stops — nothing broken ever reaches staging.

### 2. The Application

For this example, we deploy a simple Lambda function:

```python
import json

def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Hello from CI/CD pipeline!",
            "event": event
        })
    }
```

The same pattern applies to any application — Flask APIs, FastAPI services, containerized workloads on ECS, etc.

### 3. CloudFormation Infrastructure

The pipeline itself is defined as Infrastructure as Code using CloudFormation. Key resources:

**Artifact Bucket** — S3 bucket with versioning to store build outputs between stages:

```yaml
ArtifactBucket:
  Type: AWS::S3::Bucket
  Properties:
    BucketName: !Sub "${AppName}-artifacts-${Environment}-${AWS::AccountId}"
    VersioningConfiguration:
      Status: Enabled
```

**CodeBuild Project** — runs the buildspec and produces the artifact:

```yaml
BuildProject:
  Type: AWS::CodeBuild::Project
  Properties:
    Name: !Sub "${AppName}-build-${Environment}"
    ServiceRole: !GetAtt CodeBuildRole.Arn
    Artifacts:
      Type: CODEPIPELINE
    Environment:
      Type: LINUX_CONTAINER
      ComputeType: BUILD_GENERAL1_SMALL
      Image: aws/codebuild/standard:7.0
    Source:
      Type: CODEPIPELINE
      BuildSpec: code/buildspec.yml
```

**CodePipeline** — wires all stages together:

```yaml
Pipeline:
  Type: AWS::CodePipeline::Pipeline
  Properties:
    Stages:
      - Name: Source
        Actions:
          - Name: Source
            ActionTypeId:
              Category: Source
              Owner: ThirdParty
              Provider: GitHub
              Version: '1'
            Configuration:
              Owner: !Ref GitHubOwner
              Repo: !Ref GitHubRepo
              Branch: !Ref GitHubBranch
              OAuthToken: !Ref GitHubOAuthToken

      - Name: Build
        Actions:
          - Name: Build
            ActionTypeId:
              Category: Build
              Owner: AWS
              Provider: CodeBuild
              Version: '1'
            Configuration:
              ProjectName: !Ref BuildProject

      - Name: ApproveProduction
        Actions:
          - Name: ManualApproval
            ActionTypeId:
              Category: Approval
              Owner: AWS
              Provider: Manual
              Version: '1'

      - Name: DeployProduction
        Actions:
          - Name: DeployProduction
            ActionTypeId:
              Category: Deploy
              Owner: AWS
              Provider: S3
              Version: '1'
```

### 4. IAM — Least Privilege Per Stage

Each service gets only the permissions it needs:

```yaml
CodeBuildRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Statement:
        - Effect: Allow
          Principal:
            Service: codebuild.amazonaws.com
          Action: sts:AssumeRole
    ManagedPolicyArns:
      - arn:aws:iam::aws:policy/AmazonS3FullAccess
      - arn:aws:iam::aws:policy/CloudWatchLogsFullAccess
```

CodeBuild only gets S3 and CloudWatch access. CodePipeline gets CodeBuild, S3, and CodeDeploy access. Neither gets more than they need.

### 5. Deploying the Pipeline

```bash
./deploy.sh --environment=dev
```

The script calls `aws cloudformation deploy` with the pipeline template, passing GitHub credentials as parameter overrides. On first run it creates the stack; subsequent runs update it.

## Real-World Use Case: Deploying a REST API

Imagine a team building a product catalog API. Without CI/CD:

- Developer finishes a feature → manually SSHs into server → runs deployment commands → hopes nothing breaks

With this pipeline:

1. Developer pushes to `main`
2. CodePipeline detects the push within seconds
3. CodeBuild installs dependencies and runs the full test suite
4. If tests pass, the artifact is deployed to staging automatically
5. QA validates on staging
6. A team lead clicks **Approve** in the CodePipeline console
7. The same artifact is promoted to production — no rebuild, no drift

The entire process is auditable, repeatable, and fast.

## Monitoring and Observability

### Pipeline Execution History

CodePipeline keeps a full history of every execution — what triggered it, which stage failed, how long each stage took.

### CloudWatch Integration

CodeBuild streams logs to CloudWatch Logs automatically. Set up a CloudWatch alarm to notify your team on pipeline failures:

```python
import boto3

cloudwatch = boto3.client('cloudwatch')

cloudwatch.put_metric_alarm(
    AlarmName='PipelineFailure',
    MetricName='FailedPipelineExecutions',
    Namespace='AWS/CodePipeline',
    Statistic='Sum',
    Period=300,
    EvaluationPeriods=1,
    Threshold=1,
    ComparisonOperator='GreaterThanOrEqualToThreshold',
    AlarmActions=['arn:aws:sns:us-east-1:123456789012:pipeline-alerts']
)
```

### SNS Notifications

Add an SNS topic as a pipeline notification target to get Slack/email alerts on stage transitions, approvals needed, and failures.

## Benefits and Considerations

### Key Benefits

1. **Speed**: Code goes from commit to production in minutes, not hours
2. **Consistency**: Every deployment follows the exact same process
3. **Safety**: Tests must pass before anything is deployed
4. **Auditability**: Full history of who approved what and when
5. **Rollback**: Re-run a previous pipeline execution to roll back

### Considerations

1. **Secret Management**: Never hardcode GitHub tokens — use AWS Secrets Manager or SSM Parameter Store
2. **Branch Strategy**: Decide which branches trigger which environments (e.g. `develop` → staging, `main` → production)
3. **Test Coverage**: The pipeline is only as safe as your test suite — invest in tests
4. **Cost**: CodePipeline charges per active pipeline per month (~$1), CodeBuild charges per build minute

## Estimated Monthly Cost

For a small team running ~500 deployments/month:

| Service | Cost |
|---|---|
| CodePipeline | ~$1/pipeline/month |
| CodeBuild | ~$5 (build minutes) |
| S3 (artifacts) | ~$1 |
| CloudWatch Logs | ~$2 |
| **Total** | **~$9/month** |

A negligible cost for the reliability and speed gains.

## Getting Started

1. **Fork this repo** and connect it to your AWS account
2. **Store your GitHub token** in AWS Secrets Manager
3. **Run `./deploy.sh`** to provision the pipeline
4. **Push a commit** and watch the pipeline execute end-to-end
5. **Extend it** — add ECS deployment, Lambda update, or Elastic Beanstalk targets as needed

The complete implementation including CloudFormation templates, buildspec, and deploy script is available in this repository.

## AWS CodePipeline vs GitHub Actions

If you've used GitHub Actions before, the concepts map directly:

| GitHub Actions | AWS CodePipeline |
|---|---|
| `.github/workflows/*.yml` | `pipeline.yaml` (CloudFormation) |
| Workflow | Pipeline |
| Job | Stage |
| Step | Action |
| `runs-on` runner | CodeBuild environment |
| `actions/checkout` | Source stage (GitHub provider) |
| `run: pytest` | CodeBuild `buildspec.yml` |
| Environment secrets | SSM Parameter Store / Secrets Manager |
| `workflow_dispatch` (manual trigger) | Manual approval stage |
| Artifacts | S3 artifact bucket |

Key differences worth knowing:

- **Config-as-code vs infrastructure**: GitHub Actions lives entirely in your repo (`.github/workflows/`). CodePipeline is AWS infrastructure defined separately in CloudFormation — the pipeline itself is not in your repo.
- **Concurrency**: GitHub Actions provides free concurrent runners within limits. CodeBuild has account-level concurrent build quotas that may need to be increased on new accounts.
- **AWS-native integration**: CodePipeline has tighter native integration with IAM, CloudFormation, Lambda, and other AWS services. GitHub Actions relies on third-party actions or the AWS CLI for the same.
- **Ecosystem**: GitHub Actions has a large marketplace of community actions. CodePipeline integrates deeply with AWS but has fewer third-party options.

For teams already on AWS deploying to AWS services, CodePipeline is the natural fit. For open-source projects or multi-cloud setups, GitHub Actions offers more flexibility.

## Conclusion

A CI/CD pipeline is one of the highest-leverage investments a software team can make. With AWS CodePipeline, CodeBuild, and CloudFormation, you can have a production-grade pipeline running in under an hour — fully automated, auditable, and extensible.

The days of manual deployments, SSH sessions, and "hope it works" releases are over. Ship with confidence.

What does your current deployment process look like? Drop a comment below — I'd love to hear how teams are solving this.
