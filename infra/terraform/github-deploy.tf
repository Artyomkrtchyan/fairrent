resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "github_deploy" {
  name = "fairrent-github-deploy"
  max_session_duration = 7200
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = var.github_main_oidc_subject
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_deploy" {
  name = "fairrent-publish-and-refresh"
  role = aws_iam_role.github_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage",
          "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages",
        ]
        Resource = [
          "arn:aws:ecr:eu-central-1:566663271715:repository/fairrent-backend",
          "arn:aws:ecr:eu-central-1:566663271715:repository/fairrent-frontend",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeLaunchTemplateVersions", "ec2:DescribeLaunchTemplates",
          "ec2:DescribeImages", "ec2:DescribeInstances",
          "autoscaling:DescribeAutoScalingGroups", "autoscaling:DescribeInstanceRefreshes",
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:CreateLaunchTemplateVersion", "ec2:RunInstances"]
        Resource = module.asg.launch_template_arn
      },
      {
        Effect = "Allow"
        Action = "ec2:RunInstances"
        Resource = [
          "arn:aws:ec2:eu-central-1::image/ami-0ff772d250ad39c75",
          "arn:aws:ec2:eu-central-1:566663271715:instance/*",
          "arn:aws:ec2:eu-central-1:566663271715:volume/*",
          "arn:aws:ec2:eu-central-1:566663271715:network-interface/*",
          "arn:aws:ec2:eu-central-1:566663271715:key-pair/artyom-wsl-import",
          "arn:aws:ec2:eu-central-1:566663271715:security-group/${module.security.backend_sg_id}",
          "arn:aws:ec2:eu-central-1:566663271715:subnet/${module.network.public_subnet1_id}",
          "arn:aws:ec2:eu-central-1:566663271715:subnet/${module.network.public_subnet2_id}",
        ]
      },
      {
        Effect = "Allow"
        Action = "ec2:CreateTags"
        Resource = "arn:aws:ec2:eu-central-1:566663271715:instance/*"
        Condition = {
          StringEquals = { "ec2:CreateAction" = "RunInstances" }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "autoscaling:StartInstanceRefresh", "autoscaling:RollbackInstanceRefresh",
          "autoscaling:UpdateAutoScalingGroup",
        ]
        Resource = module.asg.autoscaling_group_arn
      },
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = "arn:aws:iam::566663271715:role/fairrent-backend-ec2"
        Condition = {
          StringEquals = { "iam:PassedToService" = "ec2.amazonaws.com" }
        }
      },
    ]
  })
}

variable "github_main_oidc_subject" {
  description = "Exact GitHub OIDC sub claim for this repository's main branch."
  type        = string
  default     = "repo:Artyomkrtchyan/fairrent:ref:refs/heads/main"
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}
