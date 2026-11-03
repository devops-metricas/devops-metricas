output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "vm_name" {
  value = azurerm_linux_virtual_machine.k3s.name
}

output "public_ip" {
  value = azurerm_public_ip.main.ip_address
}

output "fqdn" {
  value       = local.fqdn
  description = "Nombre DNS público (origen: etiqueta DNS de la IP pública de Azure)."
}
