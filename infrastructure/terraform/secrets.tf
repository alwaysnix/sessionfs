# Secret Manager
#
# resend_key and verification_secret were seeded via gcloud before Terraform.
# Import them with:
#   terraform import google_secret_manager_secret.resend_key projects/sessionfs-prod/secrets/sessionfs-resend-key
#   terraform import google_secret_manager_secret.verification_secret projects/sessionfs-prod/secrets/sessionfs-verification-secret

resource "google_secret_manager_secret" "resend_key" {
  secret_id = "sessionfs-resend-key"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "verification_secret" {
  secret_id = "sessionfs-verification-secret"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "db_url" {
  secret_id = "sessionfs-db-url"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_url" {
  secret      = google_secret_manager_secret.db_url.id
  secret_data = "postgresql+asyncpg://sessionfs:${random_password.db.result}@/${google_sql_database.sessionfs.name}?host=/cloudsql/${google_sql_database_instance.main.connection_name}"
}
