data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: pulls images, writes logs, reads the optional secret.
resource "aws_iam_role" "execution" {
  name               = "${var.project}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  count = local.use_secret ? 1 : 0
  name  = "read-anthropic-secret"
  role  = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.anthropic[0].arn]
    }]
  })
}

# Task role: what the application code itself may do (EFS access via access points).
resource "aws_iam_role" "task" {
  name               = "${var.project}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "task_efs" {
  name = "efs-client"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "elasticfilesystem:ClientMount",
        "elasticfilesystem:ClientWrite",
      ]
      Resource = aws_efs_file_system.this.arn
    }]
  })
}

locals {
  use_secret = nonsensitive(var.anthropic_api_key != "")
}

resource "aws_secretsmanager_secret" "anthropic" {
  count                   = local.use_secret ? 1 : 0
  name                    = "${var.project}/anthropic-api-key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "anthropic" {
  count         = local.use_secret ? 1 : 0
  secret_id     = aws_secretsmanager_secret.anthropic[0].id
  secret_string = var.anthropic_api_key
}
