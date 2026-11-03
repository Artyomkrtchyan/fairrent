resource "aws_security_group" "alb" {
  name_prefix = "fairrent-alb-"
  description = "Public HTTP and HTTPS access"
  vpc_id      = var.vpc_id

  tags = {
    Name = "fairrent-alb"
    env  = "S5"
  }
}

resource "aws_security_group" "backend" {
  name_prefix = "fairrent-backend-"
  description = "Backend access from ALB and administrator SSH"
  vpc_id      = var.vpc_id

  tags = {
    Name = "fairrent-backend"
    env  = "S5"
  }
}

resource "aws_security_group" "database" {
  name_prefix = "fairrent-database-"
  description = "PostgreSQL access from backend"
  vpc_id      = var.vpc_id

  tags = {
    Name = "fairrent-database"
    env  = "S5"
  }
}

# Internet -> HTTP
resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  description       = "Public HTTP"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

# Internet -> HTTPS
resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  description       = "Public HTTPS"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

# ALB -> Backend
resource "aws_vpc_security_group_egress_rule" "alb_backend" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.backend.id
  description                  = "Forward requests and health checks to backend"
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_ingress_rule" "backend_http" {
  security_group_id            = aws_security_group.backend.id
  referenced_security_group_id = aws_security_group.alb.id
  description                  = "Backend requests from ALB"
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

# PC -> Backend
resource "aws_vpc_security_group_ingress_rule" "backend_ssh" {
  security_group_id = aws_security_group.backend.id
  description       = "SSH"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}

resource "aws_vpc_security_group_egress_rule" "backend_outbound" {
  security_group_id = aws_security_group.backend.id
  description       = "Outbound access for backend and provisioning"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# Backend -> PostgreSQL
resource "aws_vpc_security_group_ingress_rule" "database_postgres" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.backend.id
  description                  = "PostgreSQL from backend"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_egress_rule" "alb_nginx" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.backend.id
  description                  = "ALB to Nginx"
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

resource "aws_vpc_security_group_ingress_rule" "backend_nginx" {
  security_group_id            = aws_security_group.backend.id
  referenced_security_group_id = aws_security_group.alb.id
  description                  = "Nginx requests from ALB"
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}