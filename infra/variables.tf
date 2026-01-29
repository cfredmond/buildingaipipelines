variable "aws_region" {
  type        = string
  description = "AWS region to deploy into"
}

variable "project_name" {
  type        = string
  description = "Name prefix for resources"
  default     = "building-ai-pipelines"
}

variable "google_cse_api_key" {
  type        = string
  description = "Google CSE API key (stored in Secrets Manager via Terraform)"
  sensitive   = true
}

variable "google_cse_cx" {
  type        = string
  description = "Google CSE CX identifier (stored in Secrets Manager via Terraform)"
  sensitive   = true
}

variable "openai_api_key" {
  type        = string
  description = "OpenAI API key (stored in Secrets Manager via Terraform)"
  sensitive   = true
}

variable "openai_model" {
  type        = string
  description = "Optional model override (stored in Secrets Manager via Terraform)"
  sensitive   = true
  default     = ""
}

