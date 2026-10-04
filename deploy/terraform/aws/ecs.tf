resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.project}"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "this" {
  name = "${var.project}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# Cloud Map namespace used by ECS Service Connect.
resource "aws_service_discovery_http_namespace" "this" {
  name        = "docagent.local"
  description = "Service Connect namespace for ${var.project}"
}

locals {
  redis_url = "redis://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"

  app_environment = [
    { name = "DOCAGENT_REDIS_URL", value = local.redis_url },
    { name = "DOCAGENT_PROVIDER", value = var.provider_mode },
    { name = "HF_HOME", value = "/models" },
    { name = "DOCAGENT_DATA_DIR", value = "/data" },
  ]

  app_secrets = local.use_secret ? [
    { name = "ANTHROPIC_API_KEY", valueFrom = aws_secretsmanager_secret.anthropic[0].arn },
  ] : []

  app_mounts = [
    { sourceVolume = "data", containerPath = "/data", readOnly = false },
    { sourceVolume = "models", containerPath = "/models", readOnly = false },
  ]

  api_image = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
  ui_image  = "${aws_ecr_repository.ui.repository_url}:${var.image_tag}"

  log_config = { for name in ["api", "worker", "ui"] : name => {
    logDriver = "awslogs"
    options = {
      awslogs-group         = aws_cloudwatch_log_group.this.name
      awslogs-region        = var.region
      awslogs-stream-prefix = name
    }
  } }
}

# ------------------------------------------------- api + worker (one task)
# SQLite WAL needs a shared-memory -shm file, so api and worker must share a
# host. They run as two containers in ONE task, sharing a task-scoped
# ephemeral "data" volume (no efs config = bind mount on the task's host).
resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  ephemeral_storage {
    size_in_gib = 30
  }

  volume {
    name = "data"
  }

  volume {
    name = "models"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.this.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.models.id
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name              = "api"
      image             = local.api_image
      essential         = true
      memoryReservation = 3072
      portMappings      = [{ name = "api", containerPort = 8000, protocol = "tcp", appProtocol = "http" }]
      environment       = local.app_environment
      secrets           = local.app_secrets
      mountPoints       = local.app_mounts
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')\" || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 120
      }
      logConfiguration = local.log_config["api"]
    },
    {
      name              = "worker"
      image             = local.api_image
      essential         = true
      memoryReservation = 4096
      command           = ["arq", "docagent.worker.main.WorkerSettings"]
      environment       = local.app_environment
      secrets           = local.app_secrets
      mountPoints       = local.app_mounts
      logConfiguration  = local.log_config["worker"]
    },
  ])
}

resource "aws_ecs_service" "api" {
  name                   = "api"
  cluster                = aws_ecs_cluster.this.id
  task_definition        = aws_ecs_task_definition.api.arn
  desired_count          = var.api_desired_count
  launch_type            = "FARGATE"
  enable_execute_command = true

  # Model download on first start can be slow.
  health_check_grace_period_seconds = 180

  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.tasks.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.this.arn

    service {
      port_name      = "api"
      discovery_name = "api"
      client_alias {
        dns_name = "api"
        port     = 8000
      }
    }
  }

  depends_on = [aws_lb_listener.http, aws_efs_mount_target.this]
}

# ----------------------------------------------------------------- ui
resource "aws_ecs_task_definition" "ui" {
  family                   = "${var.project}-ui"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ui_cpu
  memory                   = var.ui_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name             = "ui"
    image            = local.ui_image
    essential        = true
    portMappings     = [{ name = "ui", containerPort = 80, protocol = "tcp" }]
    logConfiguration = local.log_config["ui"]
  }])
}

resource "aws_ecs_service" "ui" {
  name            = "ui"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.ui.arn
  desired_count   = var.ui_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.tasks.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.ui.arn
    container_name   = "ui"
    container_port   = 80
  }

  # Client-only Service Connect: lets nginx resolve http://api:8000.
  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.this.arn
  }

  depends_on = [aws_lb_listener.http, aws_ecs_service.api]
}
