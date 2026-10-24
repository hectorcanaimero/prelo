variable "region" {
  description = "Región de AWS."
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "Tipo de EC2. Langfuse v3 (ClickHouse + Redis + MinIO) pide al menos 8 GiB; ver README."
  type        = string
  default     = "t3.large"
}

variable "ssh_cidr" {
  description = "CIDR único con acceso SSH (22), p. ej. 203.0.113.7/32. Nunca 0.0.0.0/0."
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_cidr, 0)) && var.ssh_cidr != "0.0.0.0/0"
    error_message = "ssh_cidr debe ser un CIDR válido y distinto de 0.0.0.0/0."
  }
}

variable "key_name" {
  description = "Nombre de un key pair EC2 ya existente para SSH."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR de la VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR de la subred pública."
  type        = string
  default     = "10.20.1.0/24"
}

variable "data_volume_size" {
  description = "Tamaño en GiB del volumen EBS de Postgres."
  type        = number
  default     = 20
}

variable "snapshot_retention" {
  description = "Cuántos snapshots diarios de DLM se conservan."
  type        = number
  default     = 14
}

variable "ssm_prefix" {
  description = "Prefijo en SSM Parameter Store con los secretos (SecureString, creados fuera de Terraform)."
  type        = string
  default     = "/prelo"
}
