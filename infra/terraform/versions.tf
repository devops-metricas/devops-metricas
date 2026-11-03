terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Estado remoto en Azure Storage. Los valores (cuenta, contenedor) se pasan con
  # `-backend-config=backend.hcl` (ver backend.hcl.example e infra/bootstrap/bootstrap.sh).
  backend "azurerm" {}
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  use_oidc        = true # en CI; localmente `az login` sirve para `plan`
}
