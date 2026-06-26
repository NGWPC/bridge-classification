# Bridge Classification — Infrastructure (Terraform)

Layered Terraform that provisions **all** AWS resources for the bridge-classification batch inference pipeline.

## Layout

Three layers, applied in order. Each has its own remote state; each layer's outputs feed the next layer's `terraform.tfvars`:

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
Always run `terraform plan` and review the diff before `terraform apply`.

### 1. bootstrap (once per account)

The state bucket can't hold its own state until it exists, so bootstrap locally then migrate:

```bash
cd infra/terraform/bootstrap
export AWS_PROFILE=<profile>                    # account id: aws sts get-caller-identity --query Account
cp backend.hcl.example backend.hcl              # set bucket + account id
cp terraform.tfvars.example terraform.tfvars    # set account id

# comment out `backend "s3" {}` in terraform.tf
terraform init
terraform plan                                  # review the diff before applying
terraform apply                                 # creates the bucket with local state

# uncomment `backend "s3" {}`
terraform init -backend-config=backend.hcl -migrate-state
rm terraform.tfstate terraform.tfstate.backup

terraform output                                # bucket_name → foundation/app backend.hcl
```

### 2. foundation

Creates IAM (Batch job / instance / spot-fleet roles + Batch service-linked role) and, by default, networking (VPC + public subnets + SG). Outputs the subnet IDs / SG / role ARNs that `app` consumes.

```bash
cd infra/terraform/foundation
cp backend.hcl.example backend.hcl            # bucket = the bootstrap state bucket
cp terraform.tfvars.example terraform.tfvars  # set account id + data_bucket
terraform init -backend-config=backend.hcl
terraform plan                                # review the diff before applying
terraform apply
terraform output                              # feed these values into app/terraform.tfvars
```

**Networking toggle.**
- `create_networking` (default `true`) creates the full VPC — one public subnet per `public_subnet_cidrs` entry, IGW, routing, an S3 gateway endpoint, and the Batch SG.
- Set it `false` to create **none** of that and instead reference an existing VPC via `existing_subnet_ids` + `existing_security_group_id`.
- Either way foundation's `subnet_ids` / `batch_security_group_id` outputs resolve to the right values, so `app` is unaffected.

**IAM toggle.**
- `create_iam` (default `true`) creates Batch IAM roles (job, instance + profile, spot-fleet, service-linked).
- Set it `false` to reference existing roles via `existing_batch_job_role_arn`, `existing_batch_instance_profile_arn`, `existing_spot_fleet_role_arn`, `existing_batch_service_role_arn`.
- Either way foundation's role ARN outputs resolve to the right values, so `app` is unaffected.

**Ownership tags.** Optional `team` and `poc` variables (empty by default). When set, `Team` and `POC` tags are added to all resources. Omitted from tags when empty — OWP deployments can skip them.

`data_bucket` scopes the Batch job role to the bucket holding the model / input / predictions.

**Example `terraform.tfvars` for enterprise/sandbox** (existing IAM + existing VPC):

```hcl
allowed_account_id = "123456789012"
data_bucket        = "my-data-bucket"
team               = "my-team"
poc                = "my-name"

# Use existing IAM roles (skip role creation)
create_iam                          = false
existing_batch_job_role_arn         = "arn:aws:iam::123456789012:role/bridge-classifier-batch-job"
existing_batch_instance_profile_arn = "arn:aws:iam::123456789012:instance-profile/bridge-classifier-batch-instance"
existing_spot_fleet_role_arn        = "arn:aws:iam::123456789012:role/bridge-classifier-spot-fleet"
existing_batch_service_role_arn     = "arn:aws:iam::123456789012:role/aws-service-role/batch.amazonaws.com/AWSServiceRoleForBatch"

# Use existing VPC (skip VPC creation)
create_networking          = false
existing_subnet_ids        = ["subnet-abc123", "subnet-def456"]
existing_security_group_id = "sg-abc123"
```

### 3. app

The workload: ECR repo, CloudWatch log group, Batch compute environment / queue / job definition. Consumes foundation's outputs (subnets, SG, role ARNs) via its tfvars, plus the S3 data config. Re-exposes outputs that `scripts/build_and_push.sh` and `scripts/submit_batch_job.py` read via `terraform output`: `ecr_repository_url`, `job_queue_name`, `job_definition_name`, `compute_environment_name`, `log_group_name`, `s3_manifest_uri`, `aws_region`, `s3_bucket`, `s3_output_prefix`.

```bash
cd infra/terraform/app
cp backend.hcl.example backend.hcl            # bucket = the bootstrap state bucket
cp terraform.tfvars.example terraform.tfvars  # paste foundation outputs + set the S3 data vars
terraform init -backend-config=backend.hcl
terraform plan                                # review the diff before applying
terraform apply
terraform output
```

## Per-account config

Each account keeps its own `backend.hcl` + `terraform.tfvars` per layer. If the account already has a VPC, set `create_networking = false` and supply its subnet/SG IDs — everything downstream is identical.
