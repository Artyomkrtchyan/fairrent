resource "aws_iam_role" "fairrent-backend-ec2" {
  name = "fairrent-backend-ec2"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      },
    ]
  })

  tags = {
    env = "S5"
  }
}

resource "aws_iam_role_policy_attachment" "test-attach" {
  role       = aws_iam_role.fairrent-backend-ec2.name
  policy_arn = aws_iam_policy.policy.arn
}

resource "aws_iam_instance_profile" "backend" {
  name = "fairrent-backend-ec2"
  role = aws_iam_role.fairrent-backend-ec2.name
}

resource "aws_iam_role_policy" "backend_db_secret" {
  name = "fairrent-backend-db-secret"
  role = aws_iam_role.fairrent-backend-ec2.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = "arn:aws:secretsmanager:eu-central-1:566663271715:secret:fairrent/dev/backend-db-??????"
    }]
  })
}