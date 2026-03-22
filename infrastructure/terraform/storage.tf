# Cloud Storage (session blobs)

resource "google_storage_bucket" "blobs" {
  name          = "sessionfs-blobs"
  location      = "US"
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age                = 90
      num_newer_versions = 1
    }
    action {
      type = "Delete"
    }
  }

  versioning {
    enabled = true
  }
}

# Artifact Registry (Docker images)

resource "google_artifact_registry_repository" "api" {
  location      = var.region
  repository_id = "sessionfs"
  format        = "DOCKER"
  description   = "SessionFS API container images"
}
