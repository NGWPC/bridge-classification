# Bridge Classification — Infrastructure (Terraform)

Layered Terraform that provisions **all** AWS resources for the bridge-classification batch
inference pipeline.

## Layout

Three layers, applied in order. Each has its own remote state; each layer's outputs feed the
next layer's `terraform.tfvars`:

```
bootstrap ──(state bucket)──▶ foundation ──(subnet IDs, role ARNs)──▶ app
```

| Layer | Creates | Cadence |
|-------|---------|---------|
| `bootstrap/` | S3 bucket for Terraform remote state (versioned, encrypted, locked, `prevent_destroy`) | Once per account |
| `foundation/` | IAM roles + networking (VPC/subnets/SG); networking optional — create fresh or reference an existing VPC | Rarely |
| `app/` | Workload: ECR repo, CloudWatch log group, Batch compute env / job queue / job definition | Often |

## Prerequisites

- Terraform ≥ 1.14, AWS provider ~> 6.0 (pinned per layer).
- AWS CLI with an SSO profile for the target account.
- Permissions to create S3 / IAM / VPC / Batch resources.

## State & safety

- Remote state in S3, one key per layer; S3-native locking (`use_lockfile`, TF ≥ 1.10).
- `allowed_account_ids` guard in both `backend.hcl` and `providers.tf` — a wrong account fails fast.
- `backend.hcl` and `terraform.tfvars` are git-ignored; copy from the `*.example` files.
  `.terraform.lock.hcl` is committed.
- Select the account via `export AWS_PROFILE=<profile>`; no profile is hard-coded.

## Apply

Run layers in order; each layer's `terraform output` provides values for the next layer's tfvars.

### 1. bootstrap (once per account)

The state bucket can't hold its own state until it exists, so bootstrap locally then migrate:

```bash
cd infra/terraform/bootstrap
export AWS_PROFILE=<profile>                    # account id: aws sts get-caller-identity --query Account
cp backend.hcl.example backend.hcl              # set bucket + account id
cp terraform.tfvars.example terraform.tfvars    # set account id

# comment out `backend "s3" {}` in terraform.tf
terraform init && terraform apply               # creates the bucket with local state

# uncomment `backend "s3" {}`
terraform init -backend-config=backend.hcl -migrate-state
rm terraform.tfstate terraform.tfstate.backup

terraform output                                # bucket_name → foundation/app backend.hcl
```

### 2. foundation

_Added next._ Creates IAM + networking; outputs subnet IDs / role ARNs for `app`. Networking is
controlled by `create_networking` (true = create a VPC; false = pass `existing_subnet_ids` /
`existing_security_group_id`).

### 3. app

_Added next._ The workload; consumes foundation's outputs and re-exposes `ecr_repository_url`,
`job_queue_name`, `job_definition_name`, etc. used by `scripts/`.

## Per-account config

Each account keeps its own `backend.hcl` + `terraform.tfvars` per layer. If the account already
has a VPC, set `create_networking = false` and supply its subnet/SG IDs — everything downstream
is identical.
