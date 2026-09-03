variable "project_id" {
  description = "ID del proyecto de GCP donde se despliega InsurAgent."
  type        = string
}

variable "region" {
  description = "Región de despliegue. northamerica-south1 (México) minimiza latencia y mantiene los datos en el país."
  type        = string
  default     = "northamerica-south1"
}

variable "environment" {
  description = "Nombre del entorno; se usa como sufijo de los recursos."
  type        = string
  default     = "poc"

  validation {
    condition     = contains(["poc", "dev", "prod"], var.environment)
    error_message = "El entorno debe ser poc, dev o prod."
  }
}

variable "container_image" {
  description = "Imagen del servicio en Artifact Registry, con tag inmutable (nunca `latest`)."
  type        = string
}

variable "anthropic_api_key" {
  description = "API key de Anthropic. Se pasa vía TF_VAR_anthropic_api_key, jamás en un .tfvars versionado."
  type        = string
  sensitive   = true
}

variable "db_tier" {
  description = "Tier de Cloud SQL. db-f1-micro es el más económico y suficiente para la PoC."
  type        = string
  default     = "db-f1-micro"
}

variable "max_instances" {
  description = "Máximo de instancias de Cloud Run. El tope es el control de costo real (PRD §5)."
  type        = number
  default     = 2
}

variable "allow_public_access" {
  description = "Si true, el servicio queda accesible sin autenticación de IAM. Sólo para la demo."
  type        = bool
  default     = false
}
