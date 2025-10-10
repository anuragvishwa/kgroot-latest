output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.kg_rca_server.id
}

output "public_ip" {
  description = "Public IP address of the instance"
  value       = aws_eip.kg_rca_server.public_ip
}

output "private_ip" {
  description = "Private IP address of the instance"
  value       = aws_instance.kg_rca_server.private_ip
}

output "data_volume_id" {
  description = "EBS volume ID for data"
  value       = aws_ebs_volume.kg_data.id
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.kg_rca_server.id
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh ubuntu@${aws_eip.kg_rca_server.public_ip}"
}

output "dns_record" {
  description = "DNS record to create"
  value       = "Create A record: ${var.domain} -> ${aws_eip.kg_rca_server.public_ip}"
}

output "setup_instructions" {
  description = "Next steps for setup"
  value       = <<-EOT

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ✅ KG RCA Server Infrastructure Created!
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    📍 Instance Details:
       - Instance ID: ${aws_instance.kg_rca_server.id}
       - Public IP:   ${aws_eip.kg_rca_server.public_ip}
       - Type:        ${var.instance_type}

    🔧 Next Steps:

    1️⃣  Update DNS
        Create an A record:
        ${var.domain} -> ${aws_eip.kg_rca_server.public_ip}

    2️⃣  SSH to Server
        ${self.ssh_command}

    3️⃣  Clone Repository
        git clone <your-repo-url>
        cd kg-rca/saas/server_mini

    4️⃣  Run Setup Script
        ./setup.sh

    5️⃣  Configure Environment
        Edit .env file:
        - Set DOMAIN=${var.domain}
        - Set EMAIL for SSL certificates
        - Review auto-generated passwords

    6️⃣  Start Services
        docker-compose up -d

    7️⃣  Setup SSL Certificate
        sudo certbot --nginx -d ${var.domain}

    8️⃣  Verify Deployment
        ./health-check.sh

    📊 Monitoring URLs (via SSH tunnel):
        - Grafana:  http://localhost:3000
        - Neo4j:    http://localhost:7474
        - Kafka UI: http://localhost:7777

    💰 Estimated Monthly Cost: $${var.instance_type == "t3.large" ? "77" : var.instance_type == "t3.xlarge" ? "137" : "250"}
       (Instance + 100GB storage + data transfer)

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  EOT
}
