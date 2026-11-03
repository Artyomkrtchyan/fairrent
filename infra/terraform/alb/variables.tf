variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "alb_sg_id" {
  type = string
}

variable "backend_instance_id" {
  description = "i-0b3a3d5463157ad65"
  type        = string
}

output "dns_name" {
  value = aws_lb.backend.dns_name
}

variable "certificate_arn" {
  type = string
}