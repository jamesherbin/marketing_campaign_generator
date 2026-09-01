locals {
  name_prefix = "campaign-${var.environment}"
  backend_sa  = trimsuffix(var.backend_service_account_email, ".gserviceaccount.com")
}

resource "google_project_service" "sqladmin" {
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "servicenetworking" {
  service            = "servicenetworking.googleapis.com"
  disable_on_destroy = false
}

resource "google_compute_network" "database" {
  name                    = "${local.name_prefix}-db-network"
  auto_create_subnetworks = false
}

resource "google_compute_global_address" "private_services" {
  name          = "${local.name_prefix}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.database.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.database.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]

  depends_on = [google_project_service.servicenetworking]
}

resource "random_id" "instance_suffix" {
  byte_length = 3
}

resource "google_sql_database_instance" "campaigns" {
  name                = "${local.name_prefix}-postgres-${random_id.instance_suffix.hex}"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = var.deletion_protection

  settings {
    tier              = var.instance_tier
    availability_type = var.availability_type
    disk_type         = "PD_SSD"
    disk_size         = 20
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 14
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.database.id
      enable_private_path_for_google_cloud_services = true
      ssl_mode                                      = "ENCRYPTED_ONLY"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    maintenance_window {
      day          = 7
      hour         = 4
      update_track = "stable"
    }

    insights_config {
      query_insights_enabled  = true
      record_application_tags = true
      record_client_address   = false
      query_string_length     = 1024
    }
  }

  depends_on = [
    google_project_service.sqladmin,
    google_service_networking_connection.private_services,
  ]
}

resource "google_sql_database" "campaigns" {
  name     = var.database_name
  instance = google_sql_database_instance.campaigns.name
}

resource "google_project_iam_member" "backend_cloud_sql_client" {
  count   = var.backend_service_account_email == "" ? 0 : 1
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${var.backend_service_account_email}"
}

resource "google_sql_user" "backend" {
  count    = var.backend_service_account_email == "" ? 0 : 1
  name     = local.backend_sa
  instance = google_sql_database_instance.campaigns.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}
