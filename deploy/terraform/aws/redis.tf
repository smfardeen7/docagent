resource "aws_security_group" "redis" {
  name        = "${var.project}-redis"
  description = "Redis access from ECS tasks"
  vpc_id      = module.vpc.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_tasks" {
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.project}-redis"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.project}-redis"
  description          = "${var.project} redis (arq queue and cache)"
  engine               = "redis"
  node_type            = var.redis_node_type
  port                 = 6379
  num_cache_clusters   = 1

  automatic_failover_enabled = false
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.redis.id]
}
