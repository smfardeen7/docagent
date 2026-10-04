output "alb_dns_name" {
  description = "Public DNS name of the load balancer."
  value       = aws_lb.this.dns_name
}

output "ecr_api_url" {
  description = "ECR repository URL for the api/worker image."
  value       = aws_ecr_repository.api.repository_url
}

output "ecr_ui_url" {
  description = "ECR repository URL for the ui image."
  value       = aws_ecr_repository.ui.repository_url
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}
