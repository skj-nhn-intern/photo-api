#!/usr/bin/env python3
"""
중지된 NHN Cloud 인스턴스로부터 이미지를 생성하고 active 될 때까지 대기.
인스턴스가 block storage volume 루트이면 createImage가 400 → 볼륨 업로드 API로 대체 시도.
환경 변수: TOKEN, COMPUTE_URL, INSTANCE_ID, GIT_SHA(선택), VOLUME_URL(선택, Block Storage API)
GITHUB_OUTPUT에 image_id, image_name 기록.
"""
import os
import sys
import time
from datetime import datetime

import requests


def _image_base_url(compute_url: str) -> str:
    """Compute URL에서 Image API 베이스 URL 추론 (NHN: kr1-api-instance → kr1-api-image)."""
    base = compute_url.split("/v2/")[0]
    return base.replace("-instance-", "-image-")


def _volume_url_from_compute(compute_url: str) -> str:
    """Compute URL에서 Block Storage(Volume) API URL 추론. NHN은 Volume v2 사용."""
    parts = compute_url.split("/v2/", 1)
    base = parts[0]
    tenant_id = (parts[1] or "").strip("/") if len(parts) > 1 else ""
    replaced = base.replace("-instance-", "-block-storage-")
    if replaced == base:
        replaced = base.replace("-instance-", "-volume-")
    if replaced != base and tenant_id:
        return f"{replaced}/v2/{tenant_id}"
    return replaced if replaced != base else ""


def main() -> None:
    token = os.environ["TOKEN"]
    compute_url = os.environ["COMPUTE_URL"]
    server_id = os.environ["INSTANCE_ID"]
    git_sha = os.environ.get("GIT_SHA", "")
    volume_url = os.environ.get("VOLUME_URL", "").strip()
    if not volume_url:
        volume_url = _volume_url_from_compute(compute_url)
    headers = {
        "X-Auth-Token": token,
        "Content-Type": "application/json",
    }

    image_name = f"photo-api-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    image_base = _image_base_url(compute_url)

    # 1) Nova createImage 시도 (volume 루트 인스턴스면 NHN에서 400)
    # visibility를 shared로 설정하여 파일 다운로드 권한 문제 해결 (테넌트 간 공유용)
    create_image_payload = {
        "createImage": {
            "name": image_name,
            "visibility": "shared",  # 파일 다운로드 권한 문제 해결을 위해 shared로 설정
            "metadata": {
                "purpose": "github-actions-build",
                "app": "photo-api",
                "git_sha": git_sha,
            },
        }
    }
    r = requests.post(
        f"{compute_url}/servers/{server_id}/action",
        headers=headers,
        json=create_image_payload,
    )

    image_id = None
    if r.ok:
        # 응답에 image_id가 있을 수 있음
        try:
            body = r.json()
            image_id = (body.get("image_id") or body.get("imageId") or "").strip()
        except Exception:
            pass
    else:
        msg = (r.text or "").lower()
        if "block storage volume" in msg and volume_url:
            # 2) 볼륨 → 이미지 업로드 (Cinder os-volume_upload_image) 시도
            print("ℹ️  인스턴스가 block storage volume 루트라 createImage 불가. 볼륨 업로드로 이미지 생성 시도...")
            att = requests.get(
                f"{compute_url}/servers/{server_id}/os-volume_attachments",
                headers=headers,
            )
            att.raise_for_status()
            attachments = att.json().get("volumeAttachments") or att.json().get("volume_attachments") or []
            if not attachments:
                print("❌ 서버에 연결된 볼륨을 찾을 수 없습니다.", file=sys.stderr)
                sys.exit(1)
            vol_id = attachments[0].get("volumeId") or attachments[0].get("id")
            upload_body = {
                "os-volume_upload_image": {
                    "image_name": image_name,
                    "container_format": "bare",
                    "disk_format": "raw",
                    "visibility": "shared",  # 파일 다운로드 권한 문제 해결을 위해 shared로 설정
                    "force": True,
                }
            }
            up = requests.post(
                f"{volume_url}/volumes/{vol_id}/action",
                headers=headers,
                json=upload_body,
            )
            if not up.ok:
                print(f"❌ 볼륨 업로드 API 응답: {up.status_code}", file=sys.stderr)
                print(up.text[:500] if up.text else "", file=sys.stderr)
                sys.exit(1)
            
            # 볼륨 업로드 응답에서 image_id 추출
            print(f"🔍 볼륨 업로드 응답 확인 중...")
            try:
                up_data = up.json()
                print(f"   응답 데이터: {up_data}")
                # 다양한 응답 형식 지원
                image_id = (
                    up_data.get("os-volume_upload_image", {}).get("image_id") or
                    up_data.get("image_id") or
                    up_data.get("imageId") or
                    (up_data.get("os-volume_upload_image") or {}).get("imageId") or
                    ""
                ).strip()
                if image_id:
                    print(f"✅ 볼륨 업로드로 이미지 생성 요청 완료: {image_id}")
                else:
                    print(f"⚠️  응답에서 image_id를 찾을 수 없음. 이름으로 조회 시도: {image_name}")
            except Exception as e:
                print(f"⚠️  볼륨 업로드 응답 파싱 실패: {e}", file=sys.stderr)
                print(f"   응답 텍스트: {up.text[:500] if up.text else '(empty)'}", file=sys.stderr)
                print(f"   이름으로 조회 시도: {image_name}")
                image_id = None
        elif "block storage volume" in msg:
            print(f"❌ 이미지 생성 불가: 인스턴스가 block storage volume 루트입니다.", file=sys.stderr)
            print(f"   볼륨 업로드 API URL을 찾을 수 없습니다 (VOLUME_URL 또는 compute URL 추론 실패).", file=sys.stderr)
            print(f"   NHN 콘솔에서 수동으로 이미지 생성하거나 Image Builder를 사용하세요.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"❌ 이미지 생성 API 응답: {r.status_code}", file=sys.stderr)
            print(r.text[:800] if r.text else "(empty)", file=sys.stderr)
            r.raise_for_status()

    max_wait = 900
    start = time.time()
    while time.time() - start < max_wait:
        if image_id:
            r = requests.get(f"{image_base}/v2/images/{image_id}", headers=headers)
            if r.status_code == 404:
                time.sleep(15)
                continue
            r.raise_for_status()
            image = r.json().get("image") or r.json()
            status = image.get("status", "")
        else:
            # image_id가 없으면 이름으로 조회
            r = requests.get(
                f"{image_base}/v2/images?name={image_name}",
                headers=headers,
            )
            r.raise_for_status()
            images = r.json().get("images", [])
            if not images:
                print(f"  이미지 '{image_name}'을 찾을 수 없음, 대기 중...")
                time.sleep(15)
                continue
            # 같은 이름의 이미지가 여러 개일 수 있으므로 최신 것 선택
            images.sort(key=lambda img: img.get("created_at") or "", reverse=True)
            image = images[0]
            image_id = image["id"]
            status = image.get("status", "")
            print(f"  이미지 발견: {image_id}, 상태: {status}")
        # 상태별 처리
        if status == "active":
            # 이미지 visibility를 shared로 설정 (파일 다운로드 권한 문제 해결을 위해)
            # 참고: shared는 테넌트 간 공유용이며, 리전 간 복제와는 무관
            print(f"🔧 이미지 visibility를 shared로 설정 중...")
            update_headers = {**headers, "X-Image-Meta-Visibility": "shared"}
            update_response = requests.patch(
                f"{image_base}/v2/images/{image_id}",
                headers=update_headers,
                json=[{"op": "replace", "path": "/visibility", "value": "shared"}],
            )
            if update_response.ok:
                print(f"✅ 이미지 visibility를 shared로 설정 완료")
            else:
                print(f"⚠️  이미지 visibility 설정 실패 (계속 진행): {update_response.status_code}")
                if update_response.text:
                    print(f"   응답: {update_response.text[:200]}")
            
            print(f"✅ 이미지 생성 완료: {image_id}")
            out = os.environ.get("GITHUB_OUTPUT")
            if out:
                with open(out, "a") as f:
                    f.write(f"image_id={image_id}\n")
                    f.write(f"image_name={image_name}\n")
            return
        # queued 상태가 너무 오래 지속되면 에러 출력
        if status == "queued":
            elapsed = int(time.time() - start)
            if elapsed > 300:  # 5분 이상 queued 상태면 경고
                print(f"⚠️  이미지가 {elapsed}초 동안 queued 상태입니다. 계속 대기 중...")
        else:
            print(f"  상태: {status}, 대기 중...")
        time.sleep(15)

    print("❌ 타임아웃: 이미지가 생성되지 않았습니다", file=sys.stderr)
    if image_id:
        print(f"   최종 이미지 ID: {image_id}", file=sys.stderr)
        print(f"   최종 상태: {status}", file=sys.stderr)
    else:
        print(f"   이미지 이름: {image_name}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
