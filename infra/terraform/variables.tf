variable "backend_instance_id" {
  type = string
}

variable "certificate_arn" {
  type = string
}

variable "frontend_image" {
  description = "Immutable frontend image for the ASG release."
  type        = string
  default     = "566663271715.dkr.ecr.eu-central-1.amazonaws.com/fairrent-frontend:demo-v2"
}
