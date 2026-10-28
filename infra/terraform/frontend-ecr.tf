resource "aws_ecr_repository" "frontend" {
  name                 = "fairrent-frontend"
  image_tag_mutability = "IMMUTABLE"

  encryption_configuration {
    encryption_type = "AES256"
  }

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "fairrent-frontend"
    env  = "S5"
  }
}

output "frontend_repository_url" {
  value = aws_ecr_repository.frontend.repository_url
}