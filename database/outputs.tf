output "instance_name" {
  value = google_sql_database_instance.campaigns.name
}

output "instance_connection_name" {
  value = google_sql_database_instance.campaigns.connection_name
}

output "database_name" {
  value = google_sql_database.campaigns.name
}

output "private_ip_address" {
  value     = google_sql_database_instance.campaigns.private_ip_address
  sensitive = true
}

output "database_network_id" {
  value = google_compute_network.database.id
}
