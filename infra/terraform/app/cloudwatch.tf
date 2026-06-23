# ----- CloudWatch log group (Batch container logs) -----
# Name must match the scope of foundation's batch_instance_logs IAM policy.
resource "aws_cloudwatch_log_group" "batch" {
  name              = "/aws/batch/${var.project_name}"
  retention_in_days = 365
}
