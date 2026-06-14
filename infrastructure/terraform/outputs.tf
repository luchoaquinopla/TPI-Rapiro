output "grafana_url" {
  description = "URL de acceso a Grafana (puerto 3000)"
  value       = "http://${google_compute_instance.grafana_vm.network_interface[0].access_config[0].nat_ip}:3000"
}

output "grafana_ip" {
  description = "IP externa de la VM Grafana"
  value       = google_compute_instance.grafana_vm.network_interface[0].access_config[0].nat_ip
}

output "pubsub_topic" {
  description = "Nombre completo del topic Pub/Sub"
  value       = google_pubsub_topic.robot_events.id
}

output "captures_bucket" {
  description = "Nombre del bucket de capturas"
  value       = google_storage_bucket.captures.name
}

output "models_bucket" {
  description = "Nombre del bucket de modelos"
  value       = google_storage_bucket.models.name
}

output "service_account_email" {
  description = "Email del service account del robot"
  value       = google_service_account.rapiro_sa.email
}