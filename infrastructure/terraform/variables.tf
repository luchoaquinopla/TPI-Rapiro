variable "project_id" {
  description = "ID del proyecto GCP"
  type        = string
  default     = "project-ac5c4157-56cb-4920-98f"
}

variable "region" {
  description = "Region principal de GCP"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Zona para la VM de Grafana"
  type        = string
  default     = "us-central1-a"
}

variable "alert_email" {
  description = "Email para alertas de Cloud Monitoring"
  type        = string
  default     = "luchoaquinopla@gmail.com"
}