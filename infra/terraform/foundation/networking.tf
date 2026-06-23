# All resources here are gated by var.create_networking:
#   true  → create a VPC + public subnets + IGW + routing + S3 endpoint + Batch SG
#   false → create nothing; the app layer uses var.existing_subnet_ids / existing_security_group_id
# Subnet count follows length(var.public_subnet_cidrs) — one per AZ.

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, length(var.public_subnet_cidrs))
}

# ----- VPC -----
resource "aws_vpc" "main" {
  count = var.create_networking ? 1 : 0

  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${var.project_name}-vpc" }
}

# ----- Internet gateway -----
resource "aws_internet_gateway" "main" {
  count = var.create_networking ? 1 : 0

  vpc_id = aws_vpc.main[0].id
  tags   = { Name = "${var.project_name}-igw" }
}

# ----- Public subnets (one per AZ) -----
resource "aws_subnet" "public" {
  count = var.create_networking ? length(var.public_subnet_cidrs) : 0

  vpc_id                  = aws_vpc.main[0].id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "${var.project_name}-public-${local.azs[count.index]}" }
}

# ----- Routing (public route table → IGW) -----
resource "aws_route_table" "public" {
  count = var.create_networking ? 1 : 0

  vpc_id = aws_vpc.main[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main[0].id
  }

  tags = { Name = "${var.project_name}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count = var.create_networking ? length(var.public_subnet_cidrs) : 0

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}

# ----- S3 gateway endpoint (free; keeps S3-heavy traffic on the AWS backbone) -----
resource "aws_vpc_endpoint" "s3" {
  count = var.create_networking ? 1 : 0

  vpc_id          = aws_vpc.main[0].id
  service_name    = "com.amazonaws.${var.region}.s3"
  route_table_ids = [aws_route_table.public[0].id]

  tags = { Name = "${var.project_name}-s3-endpoint" }
}

# ----- Batch security group (all egress for S3, ECR, CloudWatch) -----
resource "aws_security_group" "batch" {
  count = var.create_networking ? 1 : 0

  name_prefix = "${var.project_name}-batch-"
  description = "Batch compute instances: all egress for S3, ECR, CloudWatch"
  vpc_id      = aws_vpc.main[0].id

  tags = { Name = "${var.project_name}-batch-sg" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_egress_rule" "batch_all" {
  count = var.create_networking ? 1 : 0

  security_group_id = aws_security_group.batch[0].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
