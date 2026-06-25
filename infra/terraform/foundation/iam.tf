data "aws_caller_identity" "current" {}

locals {
  account_id        = data.aws_caller_identity.current.account_id
  data_bucket_arn   = "arn:aws:s3:::${var.data_bucket}"
  batch_log_grp_arn = "arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/batch/${var.project_name}:*"
}

# ----- Batch job role -----
# Application permissions for the inference container (jobRoleArn): reads model/input,
# writes predictions. Scoped to the single data bucket.

resource "aws_iam_role" "batch_job" {
  count = var.create_iam ? 1 : 0
  name  = "${var.project_name}-batch-job"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "batch_job" {
  count = var.create_iam ? 1 : 0
  name  = "${var.project_name}-batch-job"
  role  = aws_iam_role.batch_job[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3List"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = local.data_bucket_arn
      },
      {
        Sid      = "S3ReadWrite"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${local.data_bucket_arn}/*"
      },
    ]
  })
}

# ----- Batch container instance role + instance profile -----
# The ECS agent on each EC2 instance: registers, pulls from ECR, ships awslogs.

resource "aws_iam_role" "batch_instance" {
  count = var.create_iam ? 1 : 0
  name  = "${var.project_name}-batch-instance"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_instance_profile" "batch_instance" {
  count = var.create_iam ? 1 : 0
  name  = "${var.project_name}-batch-instance"
  role  = aws_iam_role.batch_instance[0].name
}

resource "aws_iam_role_policy_attachment" "batch_instance_ecs" {
  count      = var.create_iam ? 1 : 0
  role       = aws_iam_role.batch_instance[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

# awslogs driver runs under the instance role on EC2 launch type — grant scoped logs.
resource "aws_iam_role_policy" "batch_instance_logs" {
  count = var.create_iam ? 1 : 0
  name  = "${var.project_name}-batch-instance-logs"
  role  = aws_iam_role.batch_instance[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "CloudWatchLogs"
      Effect   = "Allow"
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = local.batch_log_grp_arn
    }]
  })
}

# ----- Spot Fleet role -----

resource "aws_iam_role" "spot_fleet" {
  count = var.create_iam ? 1 : 0
  name  = "${var.project_name}-spot-fleet"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "spotfleet.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "spot_fleet" {
  count      = var.create_iam ? 1 : 0
  role       = aws_iam_role.spot_fleet[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2SpotFleetTaggingRole"
}

# ----- Batch service-linked role -----
# Account-global; AWS may have auto-created it already. Toggle off to skip and reference it.

resource "aws_iam_service_linked_role" "batch" {
  count            = var.create_iam && var.create_batch_service_linked_role ? 1 : 0
  aws_service_name = "batch.amazonaws.com"
}
