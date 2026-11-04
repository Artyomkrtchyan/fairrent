output "instance_profile_name" {
  value = aws_iam_instance_profile.backend.name
}
output "role_name" { value = aws_iam_role.fairrent-backend-ec2.name }
