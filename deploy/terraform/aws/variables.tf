variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Name prefix for all resources."
  type        = string
  default     = "docagent"
}

variable "image_tag" {
  description = "Image tag to deploy for both the api and ui images."
  type        = string
  default     = "latest"
}

variable "provider_mode" {
  description = "LLM provider mode passed as DOCAGENT_PROVIDER (hf or anthropic)."
  type        = string
  default     = "hf"

  validation {
    condition     = contains(["hf", "anthropic"], var.provider_mode)
    error_message = "provider_mode must be either \"hf\" or \"anthropic\"."
  }
}

variable "anthropic_api_key" {
  description = "Anthropic API key. Stored in Secrets Manager only when non-empty."
  type        = string
  default     = ""
  sensitive   = true
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "api_cpu" {
  description = "Fargate CPU units for the api task."
  type        = number
  default     = 1024
}

variable "api_memory" {
  description = "Fargate memory (MiB) for the api task."
  type        = number
  default     = 4096
}

variable "worker_cpu" {
  description = "Fargate CPU units for the worker task."
  type        = number
  default     = 1024
}

variable "worker_memory" {
  description = "Fargate memory (MiB) for the worker task."
  type        = number
  default     = 4096
}

variable "ui_cpu" {
  description = "Fargate CPU units for the ui task."
  type        = number
  default     = 256
}

variable "ui_memory" {
  description = "Fargate memory (MiB) for the ui task."
  type        = number
  default     = 512
}

variable "api_desired_count" {
  description = "Desired number of api tasks."
  type        = number
  default     = 1
}

variable "worker_desired_count" {
  description = "Desired number of worker tasks."
  type        = number
  default     = 1
}

variable "ui_desired_count" {
  description = "Desired number of ui tasks."
  type        = number
  default     = 1
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 14
}
