variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "ca_cert_path" {
  description = "Path to CA certificate file"
  type        = string
}

variable "server_cert_path" {
  description = "Path to server certificate file"
  type        = string
}

variable "server_key_path" {
  description = "Path to server private key file"
  type        = string
}

variable "registry_replicas" {
  description = "Number of registry service replicas"
  type        = number
  default     = 2
}

variable "enable_monitoring" {
  description = "Enable Prometheus monitoring"
  type        = bool
  default     = true
}

variable "token_rotation_hours" {
  description = "Interval in hours for token rotation"
  type        = number
  default     = 24
}

variable "message_retention_days" {
  description = "Number of days to retain messages in pub/sub system"
  type        = number
  default     = 7
}

variable "max_retry_attempts" {
  description = "Maximum number of retry attempts for failed messages"
  type        = number
  default     = 3
} 