variable "backend_sg_id" {
  type = string
}

variable "instance_profile_name" {
  type = string
}

variable "key_name" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "target_group_arn" {
  type = string
}

variable "frontend_target_group_arn" {
  type = string
}

variable "frontend_image" {
  description = "Frontend ECR image deployed when ASG instances start."
  type        = string
}
