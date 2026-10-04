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
  description = "Fargate CPU units for the combined api+worker task."
  type        = number
  default     = 2048
}

variable "api_memory" {
  description = "Fargate memory (MiB) for the combined api+worker task."
  type        = number
  default     = 8192
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
  description = "Desired number of api(+worker) tasks. Must stay 1: each task has its own SQLite database."
  type        = number
  default     = 1

  validation {
    condition     = var.api_desired_count == 1
    error_message = "api_desired_count must be 1; extra tasks would each get an independent /data."
  }
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
