output "service_url" {
  description = "URL del servicio de Cloud Run (entregable 1 del PRD §2)."
  value       = google_cloud_run_v2_service.app.uri
}

output "database_connection_name" {
  description = "Nombre de conexión de Cloud SQL, para el proxy local."
  value       = google_sql_database_instance.main.connection_name
}

output "evidence_bucket" {
  description = "Bucket donde se almacena la evidencia de siniestros."
  value       = google_storage_bucket.evidence.name
}

output "artifact_registry_repository" {
  description = "Destino de `docker push` para la imagen del servicio."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "service_account_email" {
  description = "Identidad con la que corre el servicio."
  value       = google_service_account.app.email
}
