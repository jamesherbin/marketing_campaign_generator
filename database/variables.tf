variable "project_id" {
  description = "Google Cloud project that will own the Cloud SQL instance."
  type        = string
}

variable "region" {
  description = "Google Cloud region for Cloud SQL."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment suffix used in resource names."
  type        = string
  default     = "production"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.environment))
    error_message = "environment must be 2-21 lowercase letters, digits, or hyphens and start with a letter."
  }
}

variable "database_name" {
  description = "PostgreSQL database name."
  type        = string
  default     = "campaigns"
}

variable "instance_tier" {
  description = "Cloud SQL machine tier. Adjust after measuring production load."
  type        = string
  default     = "db-custom-1-3840"
}

variable "availability_type" {
  description = "Use REGIONAL for production HA or ZONAL for lower-cost development."
  type        = string
  default     = "REGIONAL"

  validation {
    condition     = contains(["REGIONAL", "ZONAL"], var.availability_type)
    error_message = "availability_type must be REGIONAL or ZONAL."
  }
}

variable "deletion_protection" {
  description = "Protect the instance from accidental Terraform deletion."
  type        = bool
  default     = true
}

variable "backend_service_account_email" {
  description = "Optional Cloud Run backend service account email. Grants Cloud SQL Client and creates an IAM database user."
  type        = string
  default     = ""
}
