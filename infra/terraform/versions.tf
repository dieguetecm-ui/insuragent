# Versiones fijadas: un `terraform apply` dentro de seis meses debe producir la
# misma infraestructura que hoy.

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.10"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Descomentar al provisionar la cuenta: el estado nunca debe vivir en el
  # equipo de un desarrollador.
  # backend "gcs" {
  #   bucket = "insuragent-tfstate"
  #   prefix = "poc/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
