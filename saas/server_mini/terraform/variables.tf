variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type (t3.large for MVP, t3.xlarge for 10+ clients)"
  type        = string
  default     = "t3.large"

  validation {
    condition     = contains(["t3.large", "t3.xlarge", "t3.2xlarge"], var.instance_type)
    error_message = "Instance type must be t3.large, t3.xlarge, or t3.2xlarge"
  }
}

variable "os_type" {
  description = "Operating system type: ubuntu or amazon-linux"
  type        = string
  default     = "ubuntu"

  validation {
    condition     = contains(["ubuntu", "amazon-linux"], var.os_type)
    error_message = "OS type must be either ubuntu or amazon-linux"
  }
}

variable "domain" {
  description = "Domain name for the API (e.g., api.yourdomain.com)"
  type        = string
}

variable "ssh_key_name" {
  description = "Name of the SSH key pair to use"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR blocks allowed to SSH to the instance"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default = {
    Project     = "KG-RCA"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}
