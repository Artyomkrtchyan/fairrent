resource "aws_launch_template" "backend" {
  name_prefix   = "fairrent-backend-"
  image_id      = "ami-0ff772d250ad39c75"
  instance_type = "t3.small"
  key_name      = var.key_name

  user_data = base64encode(join("\n", ["#cloud-config", yamlencode({
    write_files = [{
      path        = "/etc/fairrent/frontend.json"
      owner       = "root:root"
      permissions = "0640"
      content = jsonencode({
        aws_region     = "eu-central-1"
        ecr_registry   = "566663271715.dkr.ecr.eu-central-1.amazonaws.com"
        frontend_image = var.frontend_image
      })
    }]
    runcmd = [
      ["systemctl", "restart", "fairrent-frontend.service"],
    ]
  })]))

  iam_instance_profile {
    name = var.instance_profile_name
  }

  network_interfaces {
    device_index                = 0
    associate_public_ip_address = true
    delete_on_termination       = true
    security_groups             = [var.backend_sg_id]
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  credit_specification {
    cpu_credits = "standard"
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Name = "fairrent-backend-asg"
      env  = "S5"
    }
  }

  tags = {
    Name = "fairrent-backend-template"
    env  = "S5"
  }

  lifecycle {
    # GitHub Actions owns application releases after initial provisioning.
    ignore_changes = [user_data]
  }
}

resource "aws_autoscaling_group" "backend" {
  name = "fairrent-dev-asg"

  min_size         = 1
  desired_capacity = 1
  max_size         = 2

  vpc_zone_identifier = var.public_subnet_ids
  target_group_arns = [
  var.target_group_arn,
  var.frontend_target_group_arn,
  ]

  health_check_type         = "ELB"
  health_check_grace_period = 600

  min_elb_capacity          = 1
  wait_for_capacity_timeout = "15m"

  instance_refresh {
    strategy = "Rolling"

    preferences {
      min_healthy_percentage = 100
      max_healthy_percentage = 200
      instance_warmup        = 180
      skip_matching          = true
    }
  }

  launch_template {
    id      = aws_launch_template.backend.id
    version = tostring(aws_launch_template.backend.latest_version)
  }

  lifecycle {
    # A numbered version is selected by the deployment workflow.
    ignore_changes = [desired_capacity, launch_template[0].version]
  }

  tag {
    key                 = "Name"
    value               = "fairrent-backend-asg"
    propagate_at_launch = true
  }

  tag {
    key                 = "env"
    value               = "S5"
    propagate_at_launch = true
  }
}

resource "aws_autoscaling_policy" "backend_cpu" {
  name                   = "fairrent-backend-cpu"
  autoscaling_group_name = aws_autoscaling_group.backend.name
  policy_type            = "TargetTrackingScaling"

  estimated_instance_warmup = 180

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }

    target_value = 60.0
  }
}
