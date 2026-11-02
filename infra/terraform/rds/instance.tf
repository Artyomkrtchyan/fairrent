resource "aws_db_instance" "fairrent" {
  allocated_storage           = 20
  db_name                     = "fairrent"
  engine                      = "postgres"
  engine_version              = "16.15"
  instance_class              = "db.t3.micro"
  manage_master_user_password = true
  vpc_security_group_ids      = [var.database_sg_id]
  publicly_accessible         = false
  identifier                  = "fairrent-dev"
  username                    = "fairrent_admin"
  storage_type                = "gp3"
  storage_encrypted           = true
  multi_az                    = false
  backup_retention_period     = 1
  auto_minor_version_upgrade  = true
  deletion_protection         = false
  skip_final_snapshot         = true
  delete_automated_backups    = true
  db_subnet_group_name        = aws_db_subnet_group.rds-subnet.name

  tags = {
    Name = "fairrent-dev"
    env  = "S5"
  }
}
