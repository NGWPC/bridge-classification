# Bridge Classification - Infrastructure (Terraform)

Layered Terraform that provisions **all** AWS resources for the bridge-classification batch inference pipeline.

## Layout

Three layers, applied in order.\
Each has its own remote state; each layer's outputs feed the next layer's `terraform.tfvars`:

```
bootstrap ──(state bucket)──▶ foundation ──(subnet IDs, role ARNs)──▶ app
```

| Layer | Creates | Cadence |
|-------|---------|---------|
| `bootstrap/` | S3 bucket for Terraform remote state (versioned, encrypted, locked, `prevent_destroy`) | Once per account |
| `foundation/` | IAM roles + networking (VPC/subnets/SG); networking optional - create fresh or reference an existing VPC | Rarely |
| `app/` | Workload: ECR repo, CloudWatch log group, Batch compute env / job queue / job definition | Often |

Bootstrap is optional.\
If you have an existing S3 bucket, skip it and point `backend.hcl` directly at that bucket (see [Using an existing bucket](#using-an-existing-bucket-skip-bootstrap)).

## Prerequisites

- Terraform ≥ 1.14, AWS provider ~> 6.0 (pinned per layer).
- AWS CLI with an SSO profile for the target account.
- Permissions to create S3 / IAM / VPC / Batch resources.

## State & safety

- Remote state in S3, one key per layer; S3-native locking (`use_lockfile`, TF ≥ 1.10).
- `allowed_account_ids` guard in both `backend.hcl` and `providers.tf` - a wrong account fails fast.
- `backend.hcl` and `terraform.tfvars` are git-ignored; copy from the `*.example` files.
  `.terraform.lock.hcl` is committed.
- Select the account via `export AWS_PROFILE=<profile>`; no profile is hard-coded.

## Apply

Run layers in order; each layer's `terraform output` provides values for the next layer's tfvars.
Always run `terraform plan` and review the diff before `terraform apply`.

### 1. bootstrap (once per account, optional)

Creates a dedicated S3 bucket for Terraform remote state.\
Skip this step if using an existing bucket (see [Using an existing bucket](#using-an-existing-bucket-skip-bootstrap)).

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

#### Using an existing bucket (skip bootstrap)

If your account already has an S3 bucket you want to store state in, skip bootstrap entirely and configure `backend.hcl` in foundation and app to point at it.\
Use a key prefix to isolate state files from other data in the bucket.

**foundation/backend.hcl:**
```hcl
bucket              = "my-existing-bucket"
key                 = "some-prefix/terraform-state/foundation/terraform.tfstate"
region              = "us-east-1"
use_lockfile        = true
encrypt             = true
allowed_account_ids = ["<ACCOUNT_ID>"]
```

**app/backend.hcl:**
```hcl
bucket              = "my-existing-bucket"
key                 = "some-prefix/terraform-state/app/terraform.tfstate"
region              = "us-east-1"
use_lockfile        = true
encrypt             = true
allowed_account_ids = ["<ACCOUNT_ID>"]
```

Then proceed to step 2 (foundation).\
Bucket-level settings (versioning, policies) are managed outside Terraform in this path.

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
- `create_networking` (default `true`) creates the full VPC - one public subnet per `public_subnet_cidrs` entry, IGW, routing, an S3 gateway endpoint, and the Batch SG.
- Set it `false` to create **none** of that and instead reference an existing VPC via `existing_subnet_ids` & `existing_security_group_id`.
- Either way foundation's `subnet_ids` / `batch_security_group_id` outputs resolve to the right values, so `app` is unaffected.

**IAM toggle.**
- `create_iam` (default `true`) creates Batch IAM roles (job, instance + profile, spot-fleet, service-linked).
- Set it `false` to reference existing roles via `existing_batch_job_role_arn`, `existing_batch_instance_profile_arn`, `existing_spot_fleet_role_arn`, `existing_batch_service_role_arn`.
- Either way foundation's role ARN outputs resolve to the right values, so `app` is unaffected.

**Ownership tags.** Optional `team` and `poc` variables (empty by default). When set, `Team` and `POC` tags are added to all resources. Omitted from tags when empty - OWP deployments can skip them.

`data_bucket` scopes the Batch job role to the bucket holding the model / input / predictions.

**Example `terraform.tfvars` for enterprise/sandbox** (existing IAM and existing VPC):

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

## App variable reference

All variables defined in `app/variables.tf`.
Override in `app/terraform.tfvars`.
Set `AWS_PROFILE` in your environment (not in Terraform).

### AWS & General

| Variable             | Default             | Description                                |
| -------------------- | ------------------- | ------------------------------------------ |
| `allowed_account_id` | (required)          | 12-digit AWS account ID - safety guard     |
| `region`             | `us-east-1`         | AWS region                                 |
| `project_name`       | `bridge-classifier` | Prefix for all resource names              |
| `team`               | `""`                | Team name for cost-allocation tagging (omitted if empty) |
| `poc`                | `""`                | Point of contact for resources (omitted if empty) |

### Foundation inputs

Paste from `cd infra/terraform/foundation && terraform output`:

| Variable                     | Description                                            |
| ---------------------------- | ------------------------------------------------------ |
| `subnets`                    | Subnet IDs for the Batch compute environment           |
| `batch_security_group_id`    | Security group ID for Batch compute                    |
| `batch_job_role_arn`         | IAM role for job containers (S3 read/write scoped to data bucket) |
| `batch_instance_profile_arn` | EC2 instance profile for compute instances             |
| `spot_fleet_role_arn`        | EC2 Spot Fleet role (only used when `use_spot = true`) |
| `batch_service_role_arn`     | AWS Batch service-linked role                          |

### Compute

| Variable         | Default           | Description                                       |
| ---------------- | ----------------- | ------------------------------------------------- |
| `instance_types` | `["g4dn.xlarge"]` | GPU instance type(s)                              |
| `max_vcpus`      | `256`             | Max vCPUs across all instances                    |
| `use_spot`       | `true`            | Use Spot instances (auto-retries on interruption) |

### Job definition

| Variable              | Default | Description                                |
| --------------------- | ------- | ------------------------------------------ |
| `job_vcpus`           | `3`     | vCPUs per container                        |
| `job_memory`          | `15000` | Memory (MB) per container                  |
| `shared_memory_size`  | `4096`  | Shared memory (MB) for PyTorch/spconv      |
| `job_timeout_seconds` | `28800` | Max wall-clock seconds per child (8 hours) |
| `image_tag`           | `latest`| ECR image tag (pin to avoid breaking in-flight jobs) |

### S3 / Inference

| Variable           | Description                     |
| ------------------ | ------------------------------- |
| `s3_bucket`        | S3 bucket for all I/O           |
| `s3_input_prefix`  | Prefix for source LAS/LAZ files |
| `s3_manifest_uri`  | Full S3 URI of manifest         |
| `s3_model_uri`     | Full S3 URI of model checkpoint |
| `s3_output_prefix` | Where output files are uploaded |

### Inference runtime

| Variable         | Default  | Description                                   |
| ---------------- | -------- | --------------------------------------------- |
| `inference_mode` | `masked` | Output mode: `masked`, `raw`, or `both`       |
| `bridge_timeout` | `150`    | Per-bridge timeout in seconds before skipping |
| `retry_attempts` | `3`      | SPOT interruption auto-retries                |

## App outputs

Available after `terraform apply` via `terraform output`.
Used by `scripts/build_and_push.sh` and `scripts/submit_batch_job.py`.

| Output                     | Description                             |
| -------------------------- | --------------------------------------- |
| `ecr_repository_url`       | ECR URL for `docker push`               |
| `job_definition_name`      | Batch job definition name               |
| `job_queue_name`           | Batch job queue name                    |
| `compute_environment_name` | Batch compute environment name          |
| `log_group_name`           | CloudWatch log group for Batch job logs |
| `s3_manifest_uri`          | S3 manifest URI (passthrough)           |
| `aws_region`               | AWS region (passthrough for scripts)    |
| `s3_bucket`                | S3 data bucket (passthrough for run tracking) |
| `s3_output_prefix`         | S3 output prefix (passthrough for run tracking) |

## Per-account config

Each account keeps its own `backend.hcl` + `terraform.tfvars` per layer.
If the account already has a VPC, set `create_networking = false` and supply its subnet/SG IDs - everything downstream is identical.

**Joining an existing deployment.**\
If state file already exists, clone the repo, copy `backend.hcl.example` to `backend.hcl` in each layer, fill in the same bucket/key/account values, and run `terraform init -backend-config=backend.hcl`.\
You will connect to the existing state - no apply needed.

**Switching between accounts.**\
If you previously initialized against a different account, Terraform detects a backend change.
Use `terraform init -backend-config=backend.hcl -reconfigure` to point at the new backend with empty local state.
The previous account's state remains untouched in its own backend.

**Importing pre-existing resources.**\
If the account already has resources that Terraform expects to create (e.g. an ECR repo), `terraform apply` will fail with an "already exists" error.
Import the resource into state instead:
```bash
terraform import aws_ecr_repository.inference bridge-classifier
```
After importing, `terraform plan` should show no changes (or minor drift) for that resource.

**Cross-account data bucket.**\
If `data_bucket` in foundation is in a different AWS account than the Batch infrastructure, both sides must allow access:
1. Foundation's IAM policy (Terraform handles this) grants the Batch job role access to the bucket.
2. The bucket policy in the data account must also grant access to the Batch job role from the infra account.

Verify with `aws s3 ls s3://<data-bucket>/ --profile <infra-profile>` before submitting jobs.
