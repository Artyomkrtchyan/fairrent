output "launch_template_arn" {
  value = aws_launch_template.backend.arn
}

output "autoscaling_group_arn" {
  value = aws_autoscaling_group.backend.arn
}
