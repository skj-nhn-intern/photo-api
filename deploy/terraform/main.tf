# photo-api Ubuntu 인스턴스 이미지(AMI)에서 인스턴스 기동
# 사용: terraform init && terraform plan -var="ami_id=ami-xxx" && terraform apply
# 변수: ami_id (필수), instance_type, key_name, subnet_id 등

variable "ami_id" {
  description = "photo-api가 설치된 Ubuntu 인스턴스 이미지 ID (AMI)"
  type        = string
}

variable "instance_type" {
  description = "인스턴스 타입"
  type        = string
  default     = "t3.small"
}

variable "key_name" {
  description = "SSH 키 페어 이름"
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "서브넷 ID (VPC 내)"
  type        = string
  default     = ""
}

variable "security_group_ids" {
  description = "보안 그룹 ID 목록 (예: 8000 포트 허용)"
  type        = list(string)
  default     = []
}

variable "name_prefix" {
  description = "리소스 이름 접두사"
  type        = string
  default     = "photo-api"
}

variable "tags" {
  description = "추가 태그"
  type        = map(string)
  default     = {}
}

variable "aws_region" {
  description = "AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_instance" "photo_api" {
  ami                    = var.ami_id
  instance_type           = var.instance_type
  key_name                = var.key_name != "" ? var.key_name : null
  subnet_id               = var.subnet_id != "" ? var.subnet_id : null
  vpc_security_group_ids  = length(var.security_group_ids) > 0 ? var.security_group_ids : null

  # 이미지 빌드 시 systemctl enable 되어 있어 부팅 시 photo-api, promtail, telegraf 자동 기동

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-${formatdate("YYYYMMDD-hhmm", timestamp())}"
    Role = "photo-api"
  })

  lifecycle {
    ignore_changes = [tags["Name"]]
  }
}

output "instance_id" {
  description = "기동된 인스턴스 ID"
  value       = aws_instance.photo_api.id
}

output "private_ip" {
  description = "인스턴스 Private IP"
  value       = aws_instance.photo_api.private_ip
}

output "public_ip" {
  description = "인스턴스 Public IP (퍼블릭 서브넷인 경우)"
  value       = aws_instance.photo_api.public_ip
}

output "api_url" {
  description = "API 기본 URL (포트 8000)"
  value       = "http://${coalesce(aws_instance.photo_api.public_ip, aws_instance.photo_api.private_ip)}:8000"
}
