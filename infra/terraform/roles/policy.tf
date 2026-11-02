resource "aws_iam_policy" "policy" {
  name        = "policy"
  path        = "/"
  description = "My ec2 policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "ecr:GetAuthorizationToken",
        ]
        Effect   = "Allow"
        Resource = "*"
      },
      {
        Action = [
          "ecr:BatchCheckLayerAvailability",
        ]
        Effect = "Allow"
        Resource = [
          "arn:aws:ecr:eu-central-1:566663271715:repository/fairrent-backend",
          "arn:aws:ecr:eu-central-1:566663271715:repository/fairrent-frontend",
        ]
      },
      {
        Action = [
          "ecr:GetDownloadUrlForLayer",
        ]
        Effect = "Allow"
        Resource = [
          "arn:aws:ecr:eu-central-1:566663271715:repository/fairrent-backend",
          "arn:aws:ecr:eu-central-1:566663271715:repository/fairrent-frontend",
        ]
      },
      {
        Action = [
          "ecr:BatchGetImage",
        ]
        Effect = "Allow"
        Resource = [
          "arn:aws:ecr:eu-central-1:566663271715:repository/fairrent-backend",
          "arn:aws:ecr:eu-central-1:566663271715:repository/fairrent-frontend",
        ]
      },
    ]
  })
}
