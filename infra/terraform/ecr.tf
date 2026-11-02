module "ecr" {
  source = "terraform-aws-modules/ecr/aws"

  repository_name                 = "fairrent-backend"
  repository_image_tag_mutability = "IMMUTABLE"
  create_lifecycle_policy         = "false"
  attach_repository_policy        = "false"
  tags = {
    Terraform = "true"
    env       = "S5"
  }
}
