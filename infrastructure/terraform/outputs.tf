output "cloud_run_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "cloud_sql_connection" {
  value = google_sql_database_instance.main.connection_name
}

output "gcs_bucket" {
  value = google_storage_bucket.blobs.name
}

output "artifact_registry" {
  value = "${google_artifact_registry_repository.api.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.repository_id}"
}

output "wif_provider" {
  value = google_iam_workload_identity_pool_provider.github_actions.name
}

output "terraform_sa" {
  value = google_service_account.terraform.email
}

output "deployer_sa" {
  value = google_service_account.deployer.email
}

output "domain_mapping_records" {
  value       = google_cloud_run_domain_mapping.api.status
  description = "DNS records needed for api.sessionfs.dev"
}
