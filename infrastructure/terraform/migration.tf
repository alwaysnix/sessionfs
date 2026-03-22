# Cloud Run Job for Alembic migrations

resource "google_cloud_run_v2_job" "migrate" {
  name     = "sessionfs-migrate"
  location = var.region

  template {
    template {
      vpc_access {
        connector = google_vpc_access_connector.connector.id
        egress    = "PRIVATE_RANGES_ONLY"
      }

      service_account = google_service_account.api.email
      timeout         = "300s"
      max_retries     = 0

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.main.connection_name]
        }
      }

      containers {
        image   = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.repository_id}/sessionfs-api:latest"
        command = ["alembic"]
        args    = ["upgrade", "head"]

        env {
          name = "SFS_DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.db_url.secret_id
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.api_cloudsql,
    google_project_iam_member.api_secrets,
  ]
}
