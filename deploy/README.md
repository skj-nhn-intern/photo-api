# photo-api 배포

이미지 빌드가 끝난 Ubuntu 인스턴스 이미지(AMI 등)를 **외부 배포 도구**로 기동할 때 사용하는 코드입니다.

## 이미지 빌드 (선행 작업)

Ubuntu VM에서 아래를 실행해 이미지를 만듭니다.

```bash
# 저장소 클론 또는 소스 업로드 후
sudo ./scripts/build-image.sh
# 또는 단계별:
# sudo ./scripts/1-install-python.sh
# sudo ./scripts/2-setup-photo-api.sh
# sudo ./scripts/3-setup-promtail.sh
# sudo ./scripts/4-setup-telegraf.sh
```

이미지 스냅샷/AMI 생성 후, 해당 이미지 ID를 배포 시 사용합니다.

---

## 1. Terraform으로 기동

- **경로**: `deploy/terraform/`
- **용도**: `ami_id` 등 변수로 이미지 지정 후 인스턴스 기동

```bash
cd deploy/terraform
terraform init
terraform plan -var="ami_id=ami-xxxxxxxx"
terraform apply -var="ami_id=ami-xxxxxxxx"
```

출력: `instance_id`, `private_ip`, `public_ip`, `api_url`

변수 예시는 `variables.tf.example` 참고. `photo-api.auto.tfvars` 등으로 넘기면 됩니다.

---

## 2. AWS CLI 스크립트로 기동

- **파일**: `deploy/run-instance.sh`
- **필수 환경변수**: `AMI_ID`

```bash
export AMI_ID=ami-xxxxxxxx
export KEY_NAME=my-key
export SUBNET_ID=subnet-xxxxxxxx
export SECURITY_GROUP_IDS="sg-xxxxxxxx"
./deploy/run-instance.sh
```

기동 후 API URL이 출력됩니다.

---

## 배포 후 확인

- API: `http://<인스턴스 IP>:8000`
- Health: `http://<인스턴스 IP>:8000/health`
- 메트릭: `http://<인스턴스 IP>:8000/metrics` (Telegraf가 수집)

**인스턴스 이미지와 서비스 기동**  
이미지는 디스크 스냅샷이라 서비스는 **중지된 상태**로 들어갑니다. 빌드 시 `systemctl enable`만 해 두었기 때문에, 이 이미지에서 **인스턴스를 부팅하면** photo-api, promtail, telegraf가 **자동으로 기동**됩니다.  
수동 제어는 인스턴스에 SSH 접속한 뒤 **systemctl 실행 스크립트** 사용:

```bash
sudo photo-api-run start|stop|restart|status
```

Loki/InfluxDB 주소를 이미지와 다르게 쓰려면, 인스턴스 기동 후 `/opt/promtail/promtail-config.yaml`, `/opt/telegraf/telegraf.conf`를 수정하거나, 빌드 시 `LOKI_URL`, `INFLUX_URL`, `INFLUX_TOKEN` 환경변수로 설정한 뒤 이미지를 만드세요.
