# ----- Account / general -----

variable "allowed_account_id" {
  description = "AWS account ID to restrict operations to — prevents accidental apply in the wrong account"
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.allowed_account_id))
    error_message = "allowed_account_id must be a 12-digit AWS account ID."
  }
}

variable "project_name" {
  description = "Project name; prefixes resource names and is the ECR repo name"
  type        = string
  default     = "bridge-classifier"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]*[a-z0-9]$", var.project_name))
    error_message = "project_name must be lowercase letters, digits, and hyphens only."
  }
}

variable "region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.region))
    error_message = "region must look like an AWS region, e.g. us-east-1."
  }
}

variable "team" {
  description = "Team name for cost-allocation and ownership tagging (omitted from tags if empty)"
  type        = string
  default     = ""
}

variable "poc" {
  description = "Point of contact for these resources (omitted from tags if empty)"
  type        = string
  default     = ""
}

# ----- From the foundation layer (paste from its `terraform output`) -----

variable "subnets" {
  description = "Subnet IDs for the Batch compute environment (foundation output: subnet_ids)"
  type        = list(string)

  validation {
    condition     = length(var.subnets) > 0 && alltrue([for s in var.subnets : can(regex("^subnet-", s))])
    error_message = "subnets must be a non-empty list of 'subnet-' IDs."
  }
}

variable "batch_security_group_id" {
  description = "Security group ID for Batch compute (foundation output: batch_security_group_id)"
  type        = string

  validation {
    condition     = can(regex("^sg-", var.batch_security_group_id))
    error_message = "batch_security_group_id must start with 'sg-'."
  }
}

variable "batch_job_role_arn" {
  description = "Batch job (task) role ARN (foundation output: batch_job_role_arn)"
  type        = string

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/", var.batch_job_role_arn))
    error_message = "batch_job_role_arn must be an IAM role ARN (arn:aws:iam::<account>:role/...)."
  }
}

variable "batch_instance_profile_arn" {
  description = "Batch instance profile ARN (foundation output: batch_instance_profile_arn)"
  type        = string

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:instance-profile/", var.batch_instance_profile_arn))
    error_message = "batch_instance_profile_arn must be an instance-profile ARN (not a role ARN)."
  }
}

variable "spot_fleet_role_arn" {
  description = "Spot Fleet role ARN (foundation output: spot_fleet_role_arn)"
  type        = string

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/", var.spot_fleet_role_arn))
    error_message = "spot_fleet_role_arn must be an IAM role ARN (arn:aws:iam::<account>:role/...)."
  }
}

variable "batch_service_role_arn" {
  description = "Batch service-linked role ARN (foundation output: batch_service_role_arn)"
  type        = string

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/", var.batch_service_role_arn))
    error_message = "batch_service_role_arn must be an IAM role ARN (arn:aws:iam::<account>:role/...)."
  }
}

# ----- Compute environment -----

variable "max_vcpus" {
  description = "Max vCPUs the compute environment can scale to"
  type        = number
  default     = 256

  validation {
    condition     = var.max_vcpus > 0
    error_message = "max_vcpus must be greater than 0."
  }
}

variable "instance_types" {
  description = "Instance types Batch may launch"
  type        = list(string)
  default     = ["g4dn.xlarge"]

  validation {
    condition     = length(var.instance_types) > 0
    error_message = "instance_types must be a non-empty list."
  }
}

variable "use_spot" {
  description = "Use SPOT (true) or on-demand EC2 (false)"
  type        = bool
  default     = true
}

# ----- Job definition -----

variable "job_vcpus" {
  description = "vCPUs requested per job"
  type        = number
  default     = 3

  validation {
    condition     = var.job_vcpus > 0
    error_message = "job_vcpus must be greater than 0."
  }
}

variable "job_memory" {
  description = "Memory (MB) requested per job"
  type        = number
  default     = 15000

  validation {
    condition     = var.job_memory > 0
    error_message = "job_memory must be greater than 0."
  }
}

variable "shared_memory_size" {
  description = "Shared memory (MB) for the container (/dev/shm)"
  type        = number
  default     = 4096

  validation {
    condition     = var.shared_memory_size > 0
    error_message = "shared_memory_size must be greater than 0."
  }
}

variable "job_timeout_seconds" {
  description = "Per-job attempt timeout (seconds)"
  type        = number
  default     = 28800

  validation {
    condition     = var.job_timeout_seconds >= 60
    error_message = "job_timeout_seconds must be at least 60 (AWS Batch minimum attempt duration)."
  }
}

variable "retry_attempts" {
  description = "Job retry attempts (SPOT interruption handling)"
  type        = number
  default     = 3

  validation {
    condition     = var.retry_attempts >= 1 && var.retry_attempts <= 10
    error_message = "retry_attempts must be between 1 and 10 (AWS Batch range)."
  }
}

variable "image_tag" {
  description = "ECR image tag to run (pin a tag to avoid breaking in-flight jobs)"
  type        = string
  default     = "latest"
}

# ----- Inference runtime + data (S3) -----

variable "inference_mode" {
  description = "Inference output mode: masked, raw, or both"
  type        = string
  default     = "masked"

  validation {
    condition     = contains(["masked", "raw", "both"], var.inference_mode)
    error_message = "inference_mode must be one of: masked, raw, both."
  }
}

variable "bridge_timeout" {
  description = "Per-bridge inference timeout (seconds)"
  type        = number
  default     = 150

  validation {
    condition     = var.bridge_timeout > 0
    error_message = "bridge_timeout must be greater than 0."
  }
}

variable "s3_bucket" {
  description = "S3 bucket holding model/input and receiving predictions (matches foundation data_bucket)"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.s3_bucket))
    error_message = "s3_bucket must be a valid S3 bucket name (3-63 chars, lowercase)."
  }
}

variable "s3_input_prefix" {
  description = "S3 prefix for input source LAZ"
  type        = string
}

variable "s3_manifest_uri" {
  description = "S3 URI of the manifest file (s3://...)"
  type        = string

  validation {
    condition     = can(regex("^s3://", var.s3_manifest_uri))
    error_message = "s3_manifest_uri must start with s3://."
  }
}

variable "s3_model_uri" {
  description = "S3 URI of the model checkpoint (s3://...)"
  type        = string

  validation {
    condition     = can(regex("^s3://", var.s3_model_uri))
    error_message = "s3_model_uri must start with s3://."
  }
}

variable "s3_output_prefix" {
  description = "S3 prefix for prediction outputs"
  type        = string
}
