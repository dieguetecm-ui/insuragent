# ---------------------------------------------------------------------------
# InsurAgent — infraestructura de la PoC en GCP (PRD §8).
#
# Equivalencias respecto del despliegue local:
#
#   Streamlit local          → Cloud Run (escala a cero: sin tráfico, sin costo)
#   SQLite                   → Cloud SQL for PostgreSQL
#   data/uploads/            → Cloud Storage (evidencia de siniestros)
#   .env con ANTHROPIC_API_KEY → Secret Manager
#   data/index/ (FAISS)      → se hornea en la imagen; el corpus es estático y
#                              pequeño, así que un Vertex AI Vector Search
#                              gestionado costaría más que todo lo demás junto.
# ---------------------------------------------------------------------------

locals {
  name = "insuragent-${var.environment}"
  labels = {
    app         = "insuragent"
    environment = var.environment
    managed_by  = "terraform"
    owner       = "diego-carrillo-mondragon"
  }
}

resource "google_project_service" "required" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "storage.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}

# -- Identidad del servicio: privilegio mínimo, nunca la cuenta por defecto ---

resource "google_service_account" "app" {
  account_id   = local.name
  display_name = "Identidad del servicio InsurAgent (${var.environment})"
}

# -- Secretos ----------------------------------------------------------------

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "${local.name}-anthropic-api-key"
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "anthropic_api_key" {
  secret      = google_secret_manager_secret.anthropic_api_key.id
  secret_data = var.anthropic_api_key
}

resource "google_secret_manager_secret_iam_member" "app_reads_api_key" {
  secret_id = google_secret_manager_secret.anthropic_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app.email}"
}

# -- Base transaccional: el PostgreSQL que hoy emula SQLite ------------------

resource "random_password" "db" {
  length  = 32
  special = true
}

resource "google_sql_database_instance" "main" {
  name             = "${local.name}-pg"
  database_version = "POSTGRES_16"
  region           = var.region

  # La PoC es descartable; en prod esto debe ser `true`.
  deletion_protection = false

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
    disk_size         = 10
    disk_autoresize   = true
    user_labels       = local.labels

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = false
      start_time                     = "07:00"
    }

    ip_configuration {
      # Sin IP pública: Cloud Run entra por el socket de Cloud SQL.
      ipv4_enabled = false
      # Requiere una VPC con Private Service Access ya configurada.
      private_network = google_compute_network.main.id
    }
  }

  depends_on = [
    google_project_service.required,
    google_service_networking_connection.private_vpc,
  ]
}

resource "google_sql_database" "app" {
  name     = "insuragent"
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "app" {
  name     = "insuragent_app"
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "${local.name}-db-password"
  labels    = local.labels

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db.result
}

resource "google_secret_manager_secret_iam_member" "app_reads_db_password" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app.email}"
}

resource "google_project_iam_member" "app_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# -- Red privada para Cloud SQL ---------------------------------------------

resource "google_compute_network" "main" {
  name                    = "${local.name}-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.required]
}

resource "google_compute_global_address" "private_ip" {
  name          = "${local.name}-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip.name]
}

# -- Evidencia de siniestros: reemplaza data/uploads/ ------------------------

resource "google_storage_bucket" "evidence" {
  name     = "${local.name}-evidence-${var.project_id}"
  location = var.region
  labels   = local.labels

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  # La evidencia fotográfica de un siniestro no necesita vivir para siempre en
  # almacenamiento caliente.
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket_iam_member" "app_writes_evidence" {
  bucket = google_storage_bucket.evidence.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.app.email}"
}

# -- Registro de imágenes ----------------------------------------------------

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = local.name
  format        = "DOCKER"
  labels        = local.labels

  depends_on = [google_project_service.required]
}

# -- El servicio -------------------------------------------------------------

resource "google_cloud_run_v2_service" "app" {
  name     = local.name
  location = var.region
  labels   = local.labels

  # Sin ingress público directo: se entra por el balanceador/IAP.
  ingress = var.allow_public_access ? "INGRESS_TRAFFIC_ALL" : "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.app.email

    scaling {
      # Escala a cero: sin tráfico, el costo de cómputo es cero (PRD §5).
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
      }

      ports {
        container_port = 8080
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name  = "INSURAGENT_LLM_PROVIDER"
        value = "anthropic"
      }

      env {
        name  = "INSURAGENT_ANTHROPIC_MODEL"
        value = "claude-opus-5"
      }

      env {
        name  = "INSURAGENT_EVIDENCE_BUCKET"
        value = google_storage_bucket.evidence.name
      }

      env {
        name  = "INSURAGENT_DB_HOST"
        value = "/cloudsql/${google_sql_database_instance.main.connection_name}"
      }

      env {
        name  = "INSURAGENT_DB_NAME"
        value = google_sql_database.app.name
      }

      env {
        name  = "INSURAGENT_DB_USER"
        value = google_sql_user.app.name
      }

      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.anthropic_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "INSURAGENT_DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        tcp_socket {
          port = 8080
        }
        initial_delay_seconds = 10
        timeout_seconds       = 5
        failure_threshold     = 6
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_version.anthropic_api_key,
    google_secret_manager_secret_version.db_password,
  ]
}

# Acceso abierto sólo si se pide explícitamente: por omisión, el servicio exige IAM.
resource "google_cloud_run_v2_service_iam_member" "public" {
  count = var.allow_public_access ? 1 : 0

  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
