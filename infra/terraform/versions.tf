terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Estado remoto (D12). Bucket y región se pasan con `terraform init -backend-config=...`
  # para no fijar nombres de cuenta en el repo.
  backend "s3" {
    key     = "prelo/terraform.tfstate"
    encrypt = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project = "prelo"
    }
  }
}
