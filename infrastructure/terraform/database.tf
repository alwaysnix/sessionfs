# Cloud SQL (PostgreSQL 16)

resource "google_sql_database_instance" "main" {
  name             = "sessionfs-db"
  database_version = "POSTGRES_16"
  region           = var.region

  depends_on = [google_service_networking_connection.private_vpc]

  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_size         = 10
    disk_type         = "PD_SSD"

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.main.id
      enable_private_path_for_google_cloud_services = true
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 7
      }
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "sessionfs" {
  name     = "sessionfs"
  instance = google_sql_database_instance.main.name
}

resource "random_password" "db" {
  length  = 32
  special = true
}

resource "google_sql_user" "app" {
  name     = "sessionfs"
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}
