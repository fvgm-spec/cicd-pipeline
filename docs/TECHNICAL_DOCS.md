# CI/CD Pipeline — Technical Documentation

## Pipeline Flow

```
GitHub Push → CodePipeline → CodeBuild (test + build) → Deploy Staging → Manual Approval → Deploy Production
```

## Infrastructure Components

| Resource | Purpose |
|---|---|
| CodePipeline | Orchestrates all stages |
| CodeBuild | Runs tests and builds artifact |
| S3 (ArtifactBucket) | Stores build artifacts and deployments |
| IAM Roles | Least-privilege access per service |

## buildspec.yml Stages

- `install` — installs Python deps
- `pre_build` — runs pytest
- `build` — zips app into artifact
- `post_build` — confirms completion

## Parameters (pipeline.yaml)

| Parameter | Description |
|---|---|
| AppName | Application identifier |
| Environment | dev / staging / prod |
| GitHubOwner | GitHub username/org |
| GitHubRepo | Repository name |
| GitHubBranch | Branch to watch |
| GitHubOAuthToken | GitHub personal access token (NoEcho) |

## Deployment

```bash
./deploy.sh --environment=dev
```

Pass GitHub params via `--parameter-overrides` or store in SSM Parameter Store.
