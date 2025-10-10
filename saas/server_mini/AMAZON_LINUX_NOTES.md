# Amazon Linux 2023 Support

The setup script now fully supports **Amazon Linux 2023** in addition to Ubuntu!

## Key Differences

| Feature | Ubuntu | Amazon Linux 2023 |
|---------|--------|-------------------|
| **Package Manager** | `apt-get` | `dnf` / `yum` |
| **Default User** | `ubuntu` | `ec2-user` |
| **Certbot Install** | `apt package` | `pip install` |
| **Python** | `python3` | `python3` |

## Using Amazon Linux 2023

### Option 1: Terraform (Recommended)

```bash
cd terraform

# Create config with Amazon Linux
cat > terraform.tfvars <<EOF
domain       = "api.yourdomain.com"
ssh_key_name = "your-key"
instance_type = "t3.large"
os_type      = "amazon-linux"  # ← Set this!
EOF

# Deploy
terraform init
terraform apply
```

### Option 2: Manual Setup

1. **Launch EC2** with Amazon Linux 2023 AMI
2. **SSH** as `ec2-user`:
   ```bash
   ssh -i your-key.pem ec2-user@<instance-ip>
   ```

3. **Clone repo** (if not already there):
   ```bash
   git clone <your-repo-url>
   cd kgroot_latest/saas/server_mini
   ```

4. **Run setup**:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

The script will automatically:
- ✅ Detect Amazon Linux 2023
- ✅ Use `dnf` instead of `apt-get`
- ✅ Install certbot via pip
- ✅ Create project in `/home/ec2-user/kg-rca`
- ✅ Configure everything correctly

## After Setup

Everything else is the same:

```bash
cd /home/ec2-user/kg-rca

# Configure environment
nano .env
# Set DOMAIN and EMAIL

# Start services
docker-compose up -d

# Setup SSL
sudo certbot --nginx -d api.yourdomain.com

# Check health
./health-check.sh
```

## SSH Connection

**Ubuntu:**
```bash
ssh ubuntu@<instance-ip>
```

**Amazon Linux:**
```bash
ssh ec2-user@<instance-ip>
```

## Why Amazon Linux 2023?

**Advantages:**
- ✅ Optimized for AWS
- ✅ Long-term support (5 years)
- ✅ Better AWS integration
- ✅ Lower latency for AWS services
- ✅ Free (no Ubuntu license concerns)

**When to use Ubuntu:**
- If you prefer Debian-based systems
- If you have existing Ubuntu expertise
- If you need specific Ubuntu packages

## Verified Compatibility

The setup script has been updated to work with:

- ✅ Ubuntu 22.04 LTS
- ✅ Ubuntu 20.04 LTS
- ✅ Amazon Linux 2023
- ✅ Amazon Linux 2
- ✅ RHEL 8/9
- ✅ CentOS 8/9

## Terraform AMI Selection

The Terraform configuration now includes both AMIs:

```hcl
# Ubuntu AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-*"]
  }
}

# Amazon Linux 2023 AMI
data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}
```

Set `os_type = "amazon-linux"` in `terraform.tfvars` to use Amazon Linux.

## Troubleshooting

### "apt-get: command not found"
✅ **Fixed!** The script now detects your OS and uses the correct package manager.

### Different home directory
✅ **Fixed!** The script automatically uses:
- `/home/ubuntu/kg-rca` on Ubuntu
- `/home/ec2-user/kg-rca` on Amazon Linux

### Certbot installation
✅ **Fixed!** On Amazon Linux, certbot is installed via pip since it's not in the dnf repositories.

### Docker group permissions
After Docker installation, you may need to re-login for group membership to take effect:
```bash
# Log out and log back in, or:
newgrp docker
```

## Quick Comparison

| Step | Ubuntu Command | Amazon Linux Command |
|------|----------------|---------------------|
| **Update** | `sudo apt-get update` | `sudo dnf update` |
| **Install pkg** | `sudo apt-get install X` | `sudo dnf install X` |
| **Certbot** | `sudo apt-get install certbot` | `sudo pip3 install certbot` |
| **Default user** | `ubuntu` | `ec2-user` |
| **Everything else** | ✅ Same | ✅ Same |

## Summary

The `setup.sh` script now automatically handles both Ubuntu and Amazon Linux 2023. No manual adjustments needed - just run the script and it will detect your OS and do the right thing!

**Recommendation**: Use **Amazon Linux 2023** for new deployments on AWS for better integration and support.
