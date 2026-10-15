# Building a CI/CD Pipeline to Deploy Lambda Functions with GitHub Actions and AWS SAM

Modern software teams ship code multiple times a day. Manual deployments slow teams down, introduce human error, and make rollbacks painful. In this post, we'll build a fully automated CI/CD pipeline using GitHub Actions for orchestration and AWS SAM + CloudFormation for deployment — going from a GitHub push to Lambda functions running in production.

## The Problem with Manual Deployments

Without a CI/CD pipeline, teams typically face:

1. **Inconsistent Environments**: "It works on my machine" becomes a recurring nightmare.
2. **Slow Release Cycles**: Manual steps bottleneck delivery and delay feedback.
3. **Error-Prone Processes**: Copy-paste deployment steps lead to missed commands and broken releases.
4. **No Audit Trail**: Hard to know who deployed what, when, and why.
5. **Fear of Deploying**: Teams avoid frequent releases because each one is risky.

A CI/CD pipeline solves all of these by automating the path from code commit to production.

## Why a Hybrid Approach: GitHub Actions + AWS

The initial design used AWS CodePipeline + CodeBuild as the full orchestration layer. In practice, new AWS accounts have a **concurrent build quota of 0** for CodeBuild — meaning the pipeline fails immediately at the build stage until AWS manually approves a quota increase, which can take weeks and may be denied on accounts without usage history.

The solution: use **GitHub Actions** as the CI/CD orchestrator (free concurrent runners, no quota issues) while keeping all deployment targets on AWS — SAM, CloudFormation, Lambda, S3, and SSM Parameter Store.

This hybrid approach gives you the best of both worlds: GitHub Actions' flexibility and zero-friction runner availability, plus AWS-native deployment with full IAM control.

## Services Used

- **GitHub Actions**: Pipeline orchestration — triggers, jobs, approvals
- **AWS SAM**: Packages and transforms Lambda functions for deployment
- **AWS CloudFormation**: Deploys and manages Lambda stacks per environment
- **AWS Lambda**: Runs the three CLI tools as serverless functions
- **Amazon S3**: Stores SAM-packaged Lambda artifacts between jobs
- **AWS SSM Parameter Store**: Stores secrets (API keys, credentials) as SecureString
- **AWS IAM**: Least-privilege roles for CloudFormation and Lambda execution

## Pipeline Architecture

```
GitHub Push to main
    │
    ▼
[build-and-test job]     ← GitHub Actions runner
  - checkout
  - install deps
  - run pytest
  - sam build
  - sam package → uploads zips to S3, outputs packaged.yaml
  - upload packaged.yaml as artifact
    │
    ▼
[deploy-staging job]     ← GitHub Actions runner
  - download packaged.yaml
  - resolve SSM secrets
  - aws cloudformation deploy → clt-lambdas-staging stack
    │
    ▼
[deploy-production job]  ← GitHub Actions runner (environment gate)
  - download packaged.yaml
  - resolve SSM secrets
  - aws cloudformation deploy → clt-lambdas-production stack
```

The `production` GitHub environment can be configured with a required reviewer, acting as a manual approval gate before production deployment.

## The Application: Three Lambda Functions

The pipeline deploys three Python CLI tools as Lambda functions:

- `clt-espn-results` — fetches football match results from ESPN
- `clt-deepl-translator` — translates text via the DeepL API
- `clt-spotify` — interacts with the Spotify API (top tracks, search)

Each tool has a thin `lambda_handler.py` wrapper that adapts the CLI logic to the Lambda event/response model:

```python
# espn/lambda_handler.py
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from espn_results import fetch_html, extract_state, get_scoreboard, normalize_date

def lambda_handler(event, context):
    date = normalize_date(event.get("date"))
    html = fetch_html(date)
    state = extract_state(html)
    scoreboard = get_scoreboard(state)
    return {"statusCode": 200, "body": json.dumps(scoreboard, ensure_ascii=False)}
```

## The SAM Template

All three functions are defined in a single `template.yaml`. Function names are suffixed with the environment to allow staging and production to coexist in the same account without name conflicts:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Parameters:
  DeeplApiKey:
    Type: String
    NoEcho: true
  SpotifyClientId:
    Type: String
    NoEcho: true
  SpotifyClientSecret:
    Type: String
    NoEcho: true
  SpotifyRedirectUri:
    Type: String
  Environment:
    Type: String
    Default: staging

Globals:
  Function:
    Runtime: python3.11
    Timeout: 30

Resources:
  EspnFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub "clt-espn-results-${Environment}"
      CodeUri: espn/
      Handler: lambda_handler.lambda_handler

  DeeplFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub "clt-deepl-translator-${Environment}"
      CodeUri: deepl/
      Handler: lambda_handler.lambda_handler
      Environment:
        Variables:
          DEEPL_API_KEY: !Ref DeeplApiKey

  SpotifyFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub "clt-spotify-${Environment}"
      CodeUri: spotify/
      Handler: lambda_handler.lambda_handler
      Environment:
        Variables:
          CLIENT_ID: !Ref SpotifyClientId
          CLIENT_SECRET: !Ref SpotifyClientSecret
          REDIRECT_URI: !Ref SpotifyRedirectUri
```

## The GitHub Actions Workflow

The workflow lives at `.github/workflows/pipeline.yml` and has three jobs:

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r code/deepl/requirements.txt
          pip install -r code/spotify/requirements.txt
          pip install aws-sam-cli pytest
      - name: Run tests
        run: python -m pytest code/tests/ -v
      - name: SAM build
        run: sam build --template code/template.yaml --build-dir .aws-sam/build
      - name: SAM package
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          AWS_DEFAULT_REGION: us-east-1
        run: |
          sam package \
            --template-file .aws-sam/build/template.yaml \
            --output-template-file packaged.yaml \
            --s3-bucket my-artifact-bucket \
            --s3-prefix sam-packages
      - uses: actions/upload-artifact@v4
        with:
          name: packaged-template
          path: packaged.yaml

  deploy-staging:
    needs: build-and-test
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: packaged-template
      - name: Resolve SSM secrets
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          AWS_DEFAULT_REGION: us-east-1
        run: |
          DEEPL=$(aws ssm get-parameter --name /clt/deepl/api_key --with-decryption --query Parameter.Value --output text)
          S_ID=$(aws ssm get-parameter --name /clt/spotify/client_id --with-decryption --query Parameter.Value --output text)
          S_SECRET=$(aws ssm get-parameter --name /clt/spotify/client_secret --with-decryption --query Parameter.Value --output text)
          S_URI=$(aws ssm get-parameter --name /clt/spotify/redirect_uri --with-decryption --query Parameter.Value --output text)
          echo "::add-mask::$DEEPL"
          echo "::add-mask::$S_ID"
          echo "::add-mask::$S_SECRET"
          echo "DEEPL_API_KEY=$DEEPL" >> $GITHUB_ENV
          echo "SPOTIFY_CLIENT_ID=$S_ID" >> $GITHUB_ENV
          echo "SPOTIFY_CLIENT_SECRET=$S_SECRET" >> $GITHUB_ENV
          echo "SPOTIFY_REDIRECT_URI=$S_URI" >> $GITHUB_ENV
      - name: Deploy to staging
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          AWS_DEFAULT_REGION: us-east-1
        run: |
          aws cloudformation deploy \
            --template-file packaged.yaml \
            --stack-name clt-lambdas-staging \
            --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
            --no-fail-on-empty-changeset \
            --parameter-overrides \
              DeeplApiKey="$DEEPL_API_KEY" \
              SpotifyClientId="$SPOTIFY_CLIENT_ID" \
              SpotifyClientSecret="$SPOTIFY_CLIENT_SECRET" \
              SpotifyRedirectUri="$SPOTIFY_REDIRECT_URI" \
              Environment=staging

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production  # configure required reviewers here for manual approval
    steps:
      # same as deploy-staging with Environment=production and stack-name clt-lambdas-production
```

## Secret Management with SSM Parameter Store

Secrets are stored as `SecureString` in AWS SSM Parameter Store and resolved at deploy time in the workflow — never hardcoded in the template or committed to the repo:

```bash
aws ssm put-parameter --name /clt/deepl/api_key --value "<key>" --type SecureString
aws ssm put-parameter --name /clt/spotify/client_id --value "<id>" --type SecureString
aws ssm put-parameter --name /clt/spotify/client_secret --value "<secret>" --type SecureString
aws ssm put-parameter --name /clt/spotify/redirect_uri --value "<uri>" --type SecureString
```

In the workflow, `echo "::add-mask::$VALUE"` ensures the resolved values are redacted in all GitHub Actions log output.

AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) are stored as GitHub repository secrets and injected as environment variables per job.

## IAM — Least Privilege

The AWS IAM user used by GitHub Actions needs only:

- `cloudformation:*` on the stacks
- `lambda:*` on the functions
- `s3:PutObject` / `s3:GetObject` on the artifact bucket
- `ssm:GetParameter` on `/clt/*`
- `iam:PassRole` for the Lambda execution role

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

For teams already on AWS deploying to AWS services, CodePipeline is the natural fit. For open-source projects, new AWS accounts, or teams that want simpler setup, GitHub Actions with AWS CLI/SAM is a pragmatic and equally powerful alternative.

## Estimated Monthly Cost

For a small team running ~500 deployments/month:

| Service | Cost |
|---|---|
| GitHub Actions | Free (2,000 min/month on free tier) |
| AWS Lambda | Free (1M requests/month on free tier) |
| S3 (artifacts) | ~$1 |
| SSM Parameter Store | Free (standard parameters) |
| CloudFormation | Free |
| **Total** | **~$1/month** |

Significantly cheaper than the pure CodePipeline + CodeBuild setup (~$9/month).

## Getting Started

1. Clone this repo and push to your own GitHub account
2. Add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as GitHub repository secrets
3. Store your app secrets in SSM Parameter Store under `/clt/`
4. Push to `main` — the pipeline triggers automatically
5. Configure the `production` GitHub environment with a required reviewer for a manual approval gate

## Conclusion

A hybrid GitHub Actions + AWS SAM pipeline gives you production-grade CI/CD without the operational overhead of managing CodePipeline infrastructure. GitHub Actions handles orchestration for free; AWS handles deployment with full IAM control and native Lambda integration.

The days of manual deployments, SSH sessions, and "hope it works" releases are over. Ship with confidence.

What does your current deployment process look like? Drop a comment below — I'd love to hear how teams are solving this.
