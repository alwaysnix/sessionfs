variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "sessionfs-prod"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "github_repo" {
  description = "GitHub repository (owner/repo)"
  type        = string
  default     = "alwaysnix/sessionfs"
}
