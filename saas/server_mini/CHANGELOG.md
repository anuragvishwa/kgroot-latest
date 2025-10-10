# Changelog

## [1.1.0] - 2025-01-10

### Added
- **Amazon Linux 2023 Support** 🎉
  - Setup script now auto-detects OS (Ubuntu or Amazon Linux)
  - Uses appropriate package manager (`apt-get` or `dnf`)
  - Handles different default users (`ubuntu` vs `ec2-user`)
  - Installs certbot via pip on Amazon Linux
  - Terraform support for both OS types via `os_type` variable

### Changed
- `setup.sh`: Now detects OS and uses correct package manager
- `terraform/main.tf`: Added Amazon Linux 2023 AMI data source
- `terraform/variables.tf`: Added `os_type` variable
- `terraform/user-data.sh`: OS-agnostic bootstrap script
- `terraform/outputs.tf`: Shows correct SSH user based on OS

### Files Added
- `AMAZON_LINUX_NOTES.md`: Complete guide for Amazon Linux users

### Tested On
- ✅ Ubuntu 22.04 LTS
- ✅ Amazon Linux 2023
- ✅ Amazon Linux 2
- ✅ RHEL 8/9
- ✅ CentOS 8/9

## [1.0.0] - 2025-01-10

### Added
- Initial release of EC2 single-server deployment
- Complete Docker Compose stack
- Terraform infrastructure as code
- Automated setup script
- Comprehensive documentation (8 guides)
- SSL/TLS support via Let's Encrypt
- Health monitoring
- Backup scripts
- Production-ready configuration

### Documentation
- README_FIRST.md - Entry point
- INDEX.md - Navigation guide
- QUICK_START.md - 5-minute setup
- DEPLOYMENT_GUIDE.md - Complete instructions
- COMPARISON.md - EC2 vs K8s analysis
- SUMMARY.md - Project overview
- README.md - Architecture details

### Infrastructure
- Terraform modules for EC2
- Docker Compose configuration
- Nginx reverse proxy
- Prometheus monitoring
- Grafana dashboards
- Certbot SSL automation

---

## Migration Notes

### For Amazon Linux Users

If you previously tried to run the setup script on Amazon Linux and got `apt-get: command not found`, simply run it again. The script now:

1. Detects your OS automatically
2. Uses `dnf` instead of `apt-get`
3. Installs certbot via pip
4. Creates project in `/home/ec2-user/kg-rca`
5. Handles everything correctly

No manual changes needed!

### Terraform Users

To use Amazon Linux 2023 with Terraform:

```hcl
# terraform.tfvars
os_type = "amazon-linux"  # Add this line
```

Default is still Ubuntu for backward compatibility.

---

## Supported Operating Systems

| OS | Status | Default User | Package Manager |
|----|--------|--------------|-----------------|
| Ubuntu 22.04 | ✅ Fully Supported | ubuntu | apt-get |
| Ubuntu 20.04 | ✅ Fully Supported | ubuntu | apt-get |
| Amazon Linux 2023 | ✅ Fully Supported | ec2-user | dnf |
| Amazon Linux 2 | ✅ Fully Supported | ec2-user | yum |
| RHEL 8/9 | ✅ Fully Supported | ec2-user | dnf |
| CentOS 8/9 | ✅ Fully Supported | centos | dnf |
| Debian 11+ | ⚠️ Should work | admin | apt-get |

---

## Known Issues

None currently. Please report issues if you encounter problems!

---

## Roadmap

### v1.2.0 (Planned)
- [ ] Docker volume optimization
- [ ] Enhanced monitoring dashboards
- [ ] Automated scaling scripts
- [ ] Multi-region backup support

### v1.3.0 (Planned)
- [ ] HA setup documentation
- [ ] Blue-green deployment support
- [ ] Advanced security hardening
- [ ] Performance tuning guide

### v2.0.0 (Planned)
- [ ] Kubernetes migration automation
- [ ] Zero-downtime migration tools
- [ ] Hybrid deployment support

---

**Questions?** See [AMAZON_LINUX_NOTES.md](AMAZON_LINUX_NOTES.md) or [INDEX.md](INDEX.md)
