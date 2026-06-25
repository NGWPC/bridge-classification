variable "allowed_account_id" {
  description = "AWS account ID to restrict operations to — prevents accidental apply in the wrong account"
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.allowed_account_id))
    error_message = "allowed_account_id must be a 12-digit AWS account ID."
  }
}

variable "project_name" {
  description = "Project name, used as a prefix for resource names"
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

variable "data_bucket" {
  description = "S3 bucket the inference workload reads (model, input) and writes (predictions). Scopes the Batch job role."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.data_bucket))
    error_message = "data_bucket must be a valid S3 bucket name (3-63 chars, lowercase)."
  }
}

# --- IAM: create roles (default), or reference existing ones ---

variable "create_iam" {
  description = "Create IAM roles for Batch. Set false to reference existing roles via existing_* variables."
  type        = bool
  default     = true
}

variable "create_batch_service_linked_role" {
  description = "Create the AWSServiceRoleForBatch service-linked role. Set false if the account already has it."
  type        = bool
  default     = true
}

variable "existing_batch_job_role_arn" {
  description = "Existing Batch job role ARN (required when create_iam = false)"
  type        = string
  default     = ""

  validation {
    condition     = var.create_iam || can(regex("^arn:aws:iam::[0-9]{12}:role/", var.existing_batch_job_role_arn))
    error_message = "existing_batch_job_role_arn is required (and must be a role ARN) when create_iam = false."
  }
}

variable "existing_batch_instance_profile_arn" {
  description = "Existing Batch instance profile ARN (required when create_iam = false)"
  type        = string
  default     = ""

  validation {
    condition     = var.create_iam || can(regex("^arn:aws:iam::[0-9]{12}:instance-profile/", var.existing_batch_instance_profile_arn))
    error_message = "existing_batch_instance_profile_arn is required (and must be an instance-profile ARN) when create_iam = false."
  }
}

variable "existing_spot_fleet_role_arn" {
  description = "Existing Spot Fleet role ARN (required when create_iam = false)"
  type        = string
  default     = ""

  validation {
    condition     = var.create_iam || can(regex("^arn:aws:iam::[0-9]{12}:role/", var.existing_spot_fleet_role_arn))
    error_message = "existing_spot_fleet_role_arn is required (and must be a role ARN) when create_iam = false."
  }
}

variable "existing_batch_service_role_arn" {
  description = "Existing Batch service role ARN (required when create_iam = false)"
  type        = string
  default     = ""

  validation {
    condition     = var.create_iam || can(regex("^arn:aws:iam::[0-9]{12}:role/", var.existing_batch_service_role_arn))
    error_message = "existing_batch_service_role_arn is required (and must be a role ARN) when create_iam = false."
  }
}

# --- Networking: create fresh (default), or reference an existing VPC ---

variable "create_networking" {
  description = "Create a VPC + public subnets + security group. Set false to reference an existing VPC."
  type        = bool
  default     = true
}

variable "vpc_cidr" {
  description = "CIDR for the created VPC (used only when create_networking = true)"
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be valid CIDR notation, e.g. 10.0.0.0/16."
  }
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs, one per AZ (used only when create_networking = true)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]

  validation {
    condition     = length(var.public_subnet_cidrs) >= 1
    error_message = "public_subnet_cidrs must have at least one CIDR."
  }

  validation {
    condition     = alltrue([for c in var.public_subnet_cidrs : can(cidrhost(c, 0))])
    error_message = "every entry in public_subnet_cidrs must be valid CIDR notation."
  }
}

variable "existing_vpc_id" {
  description = "Existing VPC ID (used only when create_networking = false; informational)"
  type        = string
  default     = ""
}

variable "existing_subnet_ids" {
  description = "Existing subnet IDs for Batch (required when create_networking = false)"
  type        = list(string)
  default     = []

  validation {
    condition     = var.create_networking || length(var.existing_subnet_ids) > 0
    error_message = "existing_subnet_ids is required when create_networking = false."
  }

  validation {
    condition     = alltrue([for s in var.existing_subnet_ids : can(regex("^subnet-", s))])
    error_message = "every existing_subnet_ids entry must start with 'subnet-'."
  }
}

variable "existing_security_group_id" {
  description = "Existing security group ID for Batch (required when create_networking = false)"
  type        = string
  default     = ""

  validation {
    condition     = var.create_networking || can(regex("^sg-", var.existing_security_group_id))
    error_message = "existing_security_group_id is required (and must start with 'sg-') when create_networking = false."
  }
}
