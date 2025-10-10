terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Variables
variable "aws_region" {
  description = "AWS region"
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  default     = "t3.large"
}

variable "domain" {
  description = "Domain name for the API"
  type        = string
}

variable "ssh_key_name" {
  description = "SSH key pair name"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR blocks allowed to SSH"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# Data sources
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Security Group
resource "aws_security_group" "kg_rca_server" {
  name_prefix = "kg-rca-server-"
  description = "Security group for KG RCA server"

  # SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ssh_cidr
    description = "SSH access"
  }

  # HTTP
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP access"
  }

  # HTTPS
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS access"
  }

  # Outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound"
  }

  tags = {
    Name = "kg-rca-server"
  }
}

# EBS Volume for data
resource "aws_ebs_volume" "kg_data" {
  availability_zone = data.aws_availability_zones.available.names[0]
  size              = 100
  type              = "gp3"
  iops              = 3000
  throughput        = 125

  tags = {
    Name = "kg-rca-data"
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

# EC2 Instance
resource "aws_instance" "kg_rca_server" {
  ami           = var.os_type == "ubuntu" ? data.aws_ami.ubuntu.id : data.aws_ami.amazon_linux_2023.id
  instance_type = var.instance_type
  key_name      = var.ssh_key_name

  vpc_security_group_ids = [aws_security_group.kg_rca_server.id]

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/user-data.sh", {
    domain = var.domain
  })

  tags = {
    Name = "kg-rca-server"
  }
}

# Attach data volume
resource "aws_volume_attachment" "kg_data_attach" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.kg_data.id
  instance_id = aws_instance.kg_rca_server.id
}

# Elastic IP (optional but recommended)
resource "aws_eip" "kg_rca_server" {
  instance = aws_instance.kg_rca_server.id
  domain   = "vpc"

  tags = {
    Name = "kg-rca-server"
  }
}

# Outputs
output "instance_id" {
  value = aws_instance.kg_rca_server.id
}

output "public_ip" {
  value = aws_eip.kg_rca_server.public_ip
}

output "ssh_command" {
  value = var.os_type == "ubuntu" ? "ssh ubuntu@${aws_eip.kg_rca_server.public_ip}" : "ssh ec2-user@${aws_eip.kg_rca_server.public_ip}"
}

output "ssh_user" {
  description = "SSH username for the instance"
  value       = var.os_type == "ubuntu" ? "ubuntu" : "ec2-user"
}

output "next_steps" {
  value = <<-EOT

    ✅ Instance created successfully!

    OS Type: ${var.os_type == "ubuntu" ? "Ubuntu 22.04" : "Amazon Linux 2023"}

    Next steps:
    1. Update DNS: Point ${var.domain} to ${aws_eip.kg_rca_server.public_ip}
    2. SSH to server: ${var.os_type == "ubuntu" ? "ssh ubuntu@" : "ssh ec2-user@"}${aws_eip.kg_rca_server.public_ip}
    3. Clone repo and run setup script
    4. Configure .env file
    5. Start services with docker-compose up -d

  EOT
}
