# Cloud Run v2

resource "google_cloud_run_v2_service" "api" {
  name     = "sessionfs-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    service_account = google_service_account.api.email

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.repository_id}/sessionfs-api:latest"

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      # App uses SFS_ prefix for all env vars
      env {
        name = "SFS_DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_url.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "SFS_RESEND_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.resend_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "SFS_VERIFICATION_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.verification_secret.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "SFS_BLOB_STORE_TYPE"
        value = "gcs"
      }

      env {
        name  = "SFS_GCS_BUCKET"
        value = google_storage_bucket.blobs.name
      }

      env {
        name  = "SFS_CORS_ORIGINS"
        value = "[\"https://app.sessionfs.dev\",\"https://sessionfs.dev\"]"
      }

      env {
        name  = "SFS_MAX_SYNC_BYTES"
        value = "10485760"
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }
  }

  depends_on = [
    google_project_iam_member.api_cloudsql,
    google_project_iam_member.api_gcs,
    google_project_iam_member.api_secrets,
  ]
}

# Public access (app handles auth)

resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Custom domain mapping

resource "google_cloud_run_domain_mapping" "api" {
  location = var.region
  name     = "api.sessionfs.dev"

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.api.name
  }
}
