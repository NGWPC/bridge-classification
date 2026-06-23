# --- Networking (resolves to created resources, or the existing IDs passed in) ---

output "subnet_ids" {
  description = "Subnet IDs for the Batch compute environment (→ app)"
  value       = var.create_networking ? aws_subnet.public[*].id : var.existing_subnet_ids
}

output "batch_security_group_id" {
  description = "Security group ID for Batch compute (→ app)"
  value       = var.create_networking ? aws_security_group.batch[0].id : var.existing_security_group_id
}

output "vpc_id" {
  description = "VPC ID (informational)"
  value       = var.create_networking ? aws_vpc.main[0].id : var.existing_vpc_id
}

# --- IAM (→ app) ---

output "batch_job_role_arn" {
  description = "Batch job (task) role ARN — job definition jobRoleArn"
  value       = aws_iam_role.batch_job.arn
}

output "batch_instance_profile_arn" {
  description = "Batch container instance profile ARN — compute env instance_role"
  value       = aws_iam_instance_profile.batch_instance.arn
}

output "spot_fleet_role_arn" {
  description = "Spot Fleet role ARN — compute env spot_iam_fleet_role"
  value       = aws_iam_role.spot_fleet.arn
}

output "batch_service_role_arn" {
  description = "Batch service-linked role ARN — compute env service_role"
  value       = var.create_batch_service_linked_role ? aws_iam_service_linked_role.batch[0].arn : "arn:aws:iam::${local.account_id}:role/aws-service-role/batch.amazonaws.com/AWSServiceRoleForBatch"
}
