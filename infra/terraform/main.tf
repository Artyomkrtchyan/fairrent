module "network" {
  source = "./network"
}

module "security" {
  source = "./security"
  vpc_id = module.network.vpc_id
}

module "roles" {
  source = "./roles"
}

module "rds" {
  source = "./rds"

  private_subnet_ids = [
    module.network.private_subnet1_id,
    module.network.private_subnet2_id,
  ]

  database_sg_id = module.security.database_sg_id
}

module "alb" {
  source = "./alb"

  vpc_id          = module.network.vpc_id
  certificate_arn = var.certificate_arn
  public_subnet_ids = [
    module.network.public_subnet1_id,
    module.network.public_subnet2_id,
  ]

  alb_sg_id           = module.security.alb_sg_id
  backend_instance_id = var.backend_instance_id
}

module "asg" {
  source = "./asg"

  frontend_image = var.frontend_image

  backend_sg_id         = module.security.backend_sg_id
  instance_profile_name = module.roles.instance_profile_name
  key_name              = "artyom-wsl-import"
  frontend_target_group_arn = module.alb.frontend_target_group_arn
  public_subnet_ids = [
    module.network.public_subnet1_id,
    module.network.public_subnet2_id,
  ]


  target_group_arn = module.alb.target_group_arn
}
