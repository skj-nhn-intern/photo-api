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
    create_image_payload = {
        "createImage": {
            "name": image_name,
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
            try:
                image_id = (up.json().get("image_id") or up.json().get("imageId") or "").strip()
            except Exception:
                print("❌ 볼륨 업로드 응답에서 image_id를 찾을 수 없습니다.", file=sys.stderr)
                sys.exit(1)
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
            r = requests.get(
                f"{image_base}/v2/images?name={image_name}",
                headers=headers,
            )
            r.raise_for_status()
            images = r.json().get("images", [])
            if not images:
                time.sleep(15)
                continue
            image = images[0]
            image_id = image["id"]
            status = image.get("status", "")
        if status == "active":
            # 이미지 visibility를 shared로 설정 (리전 간 복제를 위해)
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
        print(f"  상태: {status}, 대기 중...")
        time.sleep(15)

    print("❌ 타임아웃: 이미지가 생성되지 않았습니다", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
