variable "subscription_id" {
  type        = string
  description = "ID de la suscripción Azure for Students."
}

variable "location" {
  type        = string
  default     = "northcentralus"
  description = "Región. La política de la suscripción solo permite: northcentralus, brazilsouth, norwayeast, westus, francecentral."
}

variable "prefix" {
  type        = string
  default     = "notifier"
  description = "Prefijo de los nombres de recursos."
}

variable "dns_label" {
  type        = string
  description = "Etiqueta DNS de la IP pública (<label>.<region>.cloudapp.azure.com). Única por región."
}

variable "vm_size" {
  type        = string
  default     = "Standard_B2as_v2" # 2 vCPU / 8 GiB (AMD): disponible en northcentralus, sin restricciones
  description = "Tamaño de la VM; se justifica con los requests reales (docs/DEV-14-costos.md)."
}

variable "admin_username" {
  type    = string
  default = "azureuser"
}

variable "ssh_public_key" {
  type        = string
  description = "Clave pública SSH para administrar la VM (la privada nunca se versiona)."
}

variable "admin_cidr" {
  type        = string
  description = "CIDR autorizado para SSH (p. ej. la IP pública del equipo, /32). Nunca 0.0.0.0/0."
  sensitive   = true # los logs de Actions son públicos: no deben mostrar la IP de nadie

  validation {
    condition     = var.admin_cidr != "0.0.0.0/0" && var.admin_cidr != "*"
    error_message = "SSH no puede abrirse a todo Internet."
  }
}

variable "k3s_version" {
  type    = string
  default = "v1.31.4+k3s1"
}

variable "alert_emails" {
  type        = list(string)
  description = "Correos que reciben las alertas de presupuesto."
  sensitive   = true
}

variable "budget_amount" {
  type        = number
  default     = 100
  description = "Tope en USD del presupuesto del proyecto."
}

variable "budget_start_date" {
  type        = string
  description = "Primer día de un mes, formato 2026-11-01T00:00:00Z."
}

variable "shutdown_time" {
  type        = string
  default     = "2300"
  description = "Hora HHMM del apagado automático diario de la VM (red de seguridad de costos)."
}

variable "shutdown_timezone" {
  type    = string
  default = "Central America Standard Time"
}
