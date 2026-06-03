terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.3.0"
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# ─────────────────────────────────────────────
# SERVICE ACCOUNT & IAM
# ─────────────────────────────────────────────
resource "google_service_account" "rapiro_sa" {
  account_id   = "rapiro-sa"
  display_name = "RAPIRO Service Account"
  description  = "Service account usado por el robot y Cloud Functions"
}

resource "google_project_iam_member" "sa_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.editor"
  member  = "serviceAccount:${google_service_account.rapiro_sa.email}"
}

resource "google_project_iam_member" "sa_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.rapiro_sa.email}"
}

resource "google_project_iam_member" "sa_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.rapiro_sa.email}"
}

resource "google_project_iam_member" "sa_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.rapiro_sa.email}"
}

resource "google_project_iam_member" "sa_functions" {
  project = var.project_id
  role    = "roles/cloudfunctions.invoker"
  member  = "serviceAccount:${google_service_account.rapiro_sa.email}"
}

# ¡LA SOLUCIÓN DEFINITIVA PARA GRAFANA!
# Le damos permiso de LECTURA de métricas a tu cuenta personalizada rapiro_sa
resource "google_project_iam_member" "sa_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.rapiro_sa.email}"
}

resource "google_project_iam_member" "compute_sa_storage_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "compute_sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "cloudbuild_sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${data.google_project.project.number}@cloudbuild.gserviceaccount.com"
}

resource "google_project_iam_member" "cloudbuild_sa_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${data.google_project.project.number}@cloudbuild.gserviceaccount.com"
}

resource "google_project_iam_member" "cloudbuild_sa_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${data.google_project.project.number}@cloudbuild.gserviceaccount.com"
}

resource "google_project_iam_member" "compute_sa_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "compute_sa_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

data "google_project" "project" {}

# ─────────────────────────────────────────────
# PUB/SUB
# ─────────────────────────────────────────────
resource "google_pubsub_topic" "robot_events" {
  name = "rapiro-robot-events"
}

resource "google_pubsub_subscription" "robot_events_sub" {
  name  = "rapiro-robot-events-sub"
  topic = google_pubsub_topic.robot_events.name

  ack_deadline_seconds       = 20
  message_retention_duration = "86400s"

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

# ─────────────────────────────────────────────
# CLOUD STORAGE
# ─────────────────────────────────────────────
resource "google_storage_bucket" "captures" {
  name                        = "${var.project_id}-captures"
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket" "models" {
  name                        = "${var.project_id}-models"
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "functions_source" {
  name                        = "${var.project_id}-functions-source"
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true
}

# ─────────────────────────────────────────────
# FIRESTORE
# ─────────────────────────────────────────────
resource "google_firestore_database" "default" {
  name        = "(default)"
  location_id = "nam5"
  type        = "FIRESTORE_NATIVE"
}

# ─────────────────────────────────────────────
# CLOUD FUNCTION — notificaciones
# ─────────────────────────────────────────────
data "archive_file" "notify_function" {
  type        = "zip"
  source_dir  = "${path.module}/functions/notify"
  output_path = "${path.module}/functions/notify.zip"
}

resource "google_storage_bucket_object" "notify_function_zip" {
  name   = "notify-function-${data.archive_file.notify_function.output_md5}.zip"
  bucket = google_storage_bucket.functions_source.name
  source = data.archive_file.notify_function.output_path
}

resource "google_cloudfunctions_function" "notify" {
  name        = "rapiro-notify"
  description = "Recibe eventos de Pub/Sub y persiste en Firestore"
  runtime     = "python311"
  region      = var.region

  available_memory_mb   = 256
  source_archive_bucket = google_storage_bucket.functions_source.name
  source_archive_object = google_storage_bucket_object.notify_function_zip.name
  entry_point           = "notify_handler"

  event_trigger {
    event_type = "google.pubsub.topic.publish"
    resource   = google_pubsub_topic.robot_events.name
  }

  service_account_email = google_service_account.rapiro_sa.email

  environment_variables = {
    FIRESTORE_COLLECTION = "recognition_events"
    CAPTURES_BUCKET      = google_storage_bucket.captures.name
  }
}

# ─────────────────────────────────────────────
# VM — Grafana self-hosted
# ─────────────────────────────────────────────
resource "google_compute_instance" "grafana_vm" {
  name         = "rapiro-grafana"
  machine_type = "e2-micro"
  zone         = var.zone

  tags = ["grafana", "http-server"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  metadata_startup_script = <<-EOT
    #!/bin/bash
    apt-get update -y
    apt-get install -y apt-transport-https software-properties-common wget

    wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key
    echo "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main" \
      | tee /etc/apt/sources.list.d/grafana.list
    apt-get update -y
    apt-get install -y grafana

    systemctl daemon-reload
    systemctl enable grafana-server
    systemctl start grafana-server
  EOT

  service_account {
    email  = google_service_account.rapiro_sa.email
    scopes = ["cloud-platform"]
  }
}

resource "google_compute_firewall" "grafana" {
  name    = "allow-grafana"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["3000"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["grafana"]
}

# ─────────────────────────────────────────────
# MONITORING
# ─────────────────────────────────────────────
resource "google_monitoring_notification_channel" "email" {
  display_name = "RAPIRO Email Alert"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }
}