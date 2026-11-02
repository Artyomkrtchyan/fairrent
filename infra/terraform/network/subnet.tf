resource "aws_subnet" "public_subnet1" {
  vpc_id            = aws_vpc.main_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "eu-central-1a"

  tags = {
    Name = "public_subnet1"
    env  = "S5"
  }
}

resource "aws_subnet" "public_subnet2" {
  vpc_id            = aws_vpc.main_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "eu-central-1b"

  tags = {
    Name = "public_subnet2"
    env  = "S5"
  }
}

resource "aws_subnet" "private_subnet1" {
  vpc_id            = aws_vpc.main_vpc.id
  cidr_block        = "10.20.11.0/24"
  availability_zone = "eu-central-1a"

  tags = {
    Name = "private_subnet1"
    env  = "S5"
  }
}

resource "aws_subnet" "private_subnet2" {
  vpc_id            = aws_vpc.main_vpc.id
  cidr_block        = "10.20.12.0/24"
  availability_zone = "eu-central-1b"

  tags = {
    Name = "private_subnet2"
    env  = "S5"
  }
}