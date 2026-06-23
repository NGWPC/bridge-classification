# Consumed by scripts/build_and_push.sh and scripts/submit_batch_job.py
# (via `terraform output` in this directory). Profile is selected with AWS_PROFILE.

output "ecr_repository_url" {
  description = "ECR repo URL — docker build/push target"
  value       = aws_ecr_repository.inference.repository_url
}

output "job_queue_name" {
  description = "Batch job queue name — submit target"
  value       = aws_batch_job_queue.inference.name
}

output "job_definition_name" {
  description = "Batch job definition name — submit target"
  value       = aws_batch_job_definition.inference.name
}

output "compute_environment_name" {
  description = "Batch compute environment name"
  value       = aws_batch_compute_environment.gpu.name
}

output "log_group_name" {
  description = "CloudWatch log group for Batch container logs"
  value       = aws_cloudwatch_log_group.batch.name
}

output "s3_manifest_uri" {
  description = "Manifest URI (passthrough for the submit script)"
  value       = var.s3_manifest_uri
}

output "aws_region" {
  description = "AWS region (passthrough for scripts)"
  value       = var.region
}
