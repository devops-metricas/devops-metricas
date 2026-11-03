locals {
  fqdn = "${var.dns_label}.${var.location}.cloudapp.azure.com"
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.prefix}"
  location = var.location
}

# --- Red -----------------------------------------------------------------------------------

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = ["10.10.0.0/16"]
}

resource "azurerm_subnet" "main" {
  name                 = "snet-k3s"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.1.0/24"]
}

resource "azurerm_public_ip" "main" {
  name                = "pip-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
  domain_name_label   = var.dns_label
}

# Exposición mínima: 80/443 para el ingreso (Traefik) y SSH solo desde admin_cidr.
# El resto del tráfico entrante cae en la regla por defecto DenyAllInbound; en particular
# la API de Kubernetes (6443) NO es alcanzable desde Internet (sección 5.3 del enunciado).
resource "azurerm_network_security_group" "main" {
  name                = "nsg-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {
    name                       = "allow-http"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-https"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-ssh-admin"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.admin_cidr
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "main" {
  name                = "nic-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.main.id
  }
}

resource "azurerm_network_interface_security_group_association" "main" {
  network_interface_id      = azurerm_network_interface.main.id
  network_security_group_id = azurerm_network_security_group.main.id
}

# --- VM con K3s ----------------------------------------------------------------------------

resource "azurerm_linux_virtual_machine" "k3s" {
  name                            = "vm-${var.prefix}"
  location                        = azurerm_resource_group.main.location
  resource_group_name             = azurerm_resource_group.main.name
  size                            = var.vm_size
  admin_username                  = var.admin_username
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.main.id]

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 64
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  # K3s se instala solo en el primer arranque: sin pasos manuales (DEV-09, 4.1 del enunciado).
  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
    k3s_version = var.k3s_version
    fqdn        = local.fqdn
  }))
}

# Red de seguridad de costos: la VM se apaga sola cada noche (y se desasigna: sin cargo de cómputo).
resource "azurerm_dev_test_global_vm_shutdown_schedule" "k3s" {
  virtual_machine_id    = azurerm_linux_virtual_machine.k3s.id
  location              = azurerm_resource_group.main.location
  enabled               = true
  daily_recurrence_time = var.shutdown_time
  timezone              = var.shutdown_timezone

  notification_settings {
    enabled = false
  }
}

# --- Presupuesto ---------------------------------------------------------------------------
# A nivel de suscripción, para cubrir también la cuenta del estado de Terraform.
# Las alertas solo notifican: no detienen recursos (sección 5.9).

resource "azurerm_consumption_budget_subscription" "main" {
  name            = "budget-${var.prefix}"
  subscription_id = "/subscriptions/${var.subscription_id}"
  amount          = var.budget_amount
  time_grain      = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      enabled        = true
      threshold      = notification.value
      operator       = "GreaterThan"
      threshold_type = "Actual"
      contact_emails = var.alert_emails
    }
  }
}
