#!/usr/bin/env bash
# 외부 배포: 이미지(AMI)에서 인스턴스 한 대 기동 (AWS CLI 예시)
# 사용: ./deploy/run-instance.sh
# 환경변수: AMI_ID (필수), INSTANCE_TYPE, KEY_NAME, SUBNET_ID, SECURITY_GROUP_IDS
set -euo pipefail

AMI_ID="${AMI_ID:?AMI_ID를 설정하세요 (photo-api Ubuntu 이미지 ID)}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.small}"
KEY_NAME="${KEY_NAME:-}"
SUBNET_ID="${SUBNET_ID:-}"
SECURITY_GROUP_IDS="${SECURITY_GROUP_IDS:-}"
NAME="${NAME:-photo-api-$(date +%Y%m%d-%H%M)}"

TAGS="ResourceType=instance,Tags=[{Key=Name,Value=$NAME},{Key=Role,Value=photo-api}]"
# 이미지 빌드 시 systemctl enable 되어 있어 부팅 시 photo-api, promtail, telegraf 자동 기동

ARGS=(
  --image-id "$AMI_ID"
  --instance-type "$INSTANCE_TYPE"
  --tag-specifications "$TAGS"
)
[[ -n "$KEY_NAME" ]]        && ARGS+=(--key-name "$KEY_NAME")
[[ -n "$SUBNET_ID" ]]       && ARGS+=(--subnet-id "$SUBNET_ID")
[[ -n "$SECURITY_GROUP_IDS" ]] && ARGS+=(--security-group-ids $SECURITY_GROUP_IDS)

INSTANCE_ID=$(aws ec2 run-instances "${ARGS[@]}" --query 'Instances[0].InstanceId' --output text)
echo "InstanceId=$INSTANCE_ID"
echo "대기 중..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

PRIVATE_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)
PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "PrivateIp=$PRIVATE_IP"
echo "PublicIp=$PUBLIC_IP"
echo "API URL: http://${PUBLIC_IP:-$PRIVATE_IP}:8000"
