output "public_ip" {
  description = "Elastic IP: apunta aquí el DNS y la URL del webhook de GitHub."
  value       = aws_eip.prelo.public_ip
}

output "instance_id" {
  description = "ID de la EC2 (destino de SSM Run Command en el deploy)."
  value       = aws_instance.prelo.id
}

output "data_volume_id" {
  description = "ID del volumen EBS de Postgres."
  value       = aws_ebs_volume.data.id
}

output "ssm_prefix" {
  description = "Prefijo de SSM donde deben existir los secretos."
  value       = var.ssm_prefix
}
