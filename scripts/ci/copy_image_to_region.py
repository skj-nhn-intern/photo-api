#!/usr/bin/env python3
"""
KR1에서 생성한 이미지를 다른 리전(KR2 등) Image API로 복사.
인스턴스는 생성하지 않고, Image API만 사용 (GET image file from source → POST+PUT to target).

참고: 
- shared visibility는 테넌트 간 공유를 위한 것이지, 리전 간 복제를 위한 것이 아님
- 리전 간에는 별도의 이미지 저장소가 있어 복제가 필요함
- shared visibility로 설정하면 파일 다운로드 권한 문제는 해결될 수 있음 (같은 테넌트 내에서)
"""

필수 환경 변수:
  TOKEN: NHN Cloud 인증 토큰 (X-Auth-Token)
  SOURCE_IMAGE_ID: KR1에서 생성한 이미지 ID (예: create_image.py의 출력)
  SOURCE_IMAGE_NAME: KR1에서 생성한 이미지 이름 (예: create_image.py의 출력)
  
선택 환경 변수:
  SOURCE_IMAGE_BASE_URL: 소스 리전 Image API URL (예: https://kr1-api-image-infrastructure.nhncloudservice.com)
  COMPUTE_URL: 소스 리전 Compute API URL (있으면 Image API URL로 자동 추론)
  TARGET_REGION: 타겟 리전 코드 (기본값: KR2)
  TARGET_IMAGE_BASE_URL: 타겟 리전 Image API URL (없으면 TARGET_REGION으로 추론)

사용 예시 (로컬 테스트):
  export TOKEN="your-token"
  export SOURCE_IMAGE_BASE_URL="https://kr1-api-image-infrastructure.nhncloudservice.com"
  export SOURCE_IMAGE_ID="0e83ed24-7d97-483d-b36a-bcc154543bae"
  export SOURCE_IMAGE_NAME="photo-api-20250101-120000"
  export TARGET_REGION="KR2"
  python3 scripts/ci/copy_image_to_region.py
"""
import os
import sys
import time

import requests


def _image_base_from_compute_url(compute_url: str) -> str:
    """Compute URL에서 Image API 베이스 URL 추론 (NHN: kr1-api-instance → kr1-api-image)."""
    base = compute_url.split("/v2/")[0]
    return base.replace("-instance-", "-image-")


def _image_base_for_region(region: str) -> str:
    """리전 코드로 NHN Image API 베이스 URL 반환."""
    r = (region or "kr1").strip().lower()
    return f"https://{r}-api-image-infrastructure.nhncloudservice.com"


def main() -> None:
    token = os.environ.get("TOKEN", "").strip()
    source_base = os.environ.get("SOURCE_IMAGE_BASE_URL", "").strip()
    if not source_base:
        compute_url = os.environ.get("COMPUTE_URL", "").strip()
        if compute_url:
            source_base = _image_base_from_compute_url(compute_url)
    source_id = os.environ.get("SOURCE_IMAGE_ID", "").strip()
    source_name = os.environ.get("SOURCE_IMAGE_NAME", "").strip()
    target_region = os.environ.get("TARGET_REGION", "KR2").strip()

    # 환경 변수 검증 및 디버깅 정보 출력
    missing = []
    if not token:
        missing.append("TOKEN")
    if not source_base:
        missing.append("SOURCE_IMAGE_BASE_URL 또는 COMPUTE_URL")
    if not source_id:
        missing.append("SOURCE_IMAGE_ID")
    if not source_name:
        missing.append("SOURCE_IMAGE_NAME")
    
    if missing:
        print("❌ 필수 환경 변수가 설정되지 않았습니다.", file=sys.stderr)
        print("", file=sys.stderr)
        print("누락된 환경 변수:", file=sys.stderr)
        for var in missing:
            print(f"  - {var}", file=sys.stderr)
        print("", file=sys.stderr)
        print("현재 설정된 값 (디버깅용):", file=sys.stderr)
        print(f"  TOKEN: {'설정됨' if token else '❌ 없음'} ({'***' if token else 'N/A'})", file=sys.stderr)
        print(f"  SOURCE_IMAGE_BASE_URL: {os.environ.get('SOURCE_IMAGE_BASE_URL', '❌ 없음')}", file=sys.stderr)
        print(f"  COMPUTE_URL: {os.environ.get('COMPUTE_URL', '❌ 없음')}", file=sys.stderr)
        print(f"  SOURCE_IMAGE_ID: {os.environ.get('SOURCE_IMAGE_ID', '❌ 없음')}", file=sys.stderr)
        print(f"  SOURCE_IMAGE_NAME: {os.environ.get('SOURCE_IMAGE_NAME', '❌ 없음')}", file=sys.stderr)
        print(f"  추론된 source_base: {source_base if source_base else '❌ 없음'}", file=sys.stderr)
        print("", file=sys.stderr)
        print("GitHub Actions에서 실행하는 경우:", file=sys.stderr)
        print("  - TOKEN: steps.create_instance.outputs.token에서 자동 전달", file=sys.stderr)
        print("  - SOURCE_IMAGE_ID: steps.create_image.outputs.image_id에서 자동 전달", file=sys.stderr)
        print("  - SOURCE_IMAGE_NAME: steps.create_image.outputs.image_name에서 자동 전달", file=sys.stderr)
        print("  - SOURCE_IMAGE_BASE_URL: secrets.NHN_IMAGE_BASE_URL_KR1 또는 COMPUTE_URL 사용", file=sys.stderr)
        sys.exit(1)

    target_base = os.environ.get("TARGET_IMAGE_BASE_URL", "").strip()
    if not target_base:
        target_base = _image_base_for_region(target_region)
    headers = {"X-Auth-Token": token}
    headers_json = {**headers, "Content-Type": "application/json"}

    # 0) 타겟 리전에서 이미지가 이미 존재하는지 확인
    # 참고: 리전 간에는 별도의 이미지 저장소가 있어, 같은 이미지 ID라도 각 리전에 별도로 존재해야 함
    print(f"🔍 타겟 리전({target_region})에서 이미지 존재 여부 확인 중...")
    target_check = requests.get(f"{target_base}/v2/images/{source_id}", headers=headers_json)
    if target_check.status_code == 200:
        target_image = target_check.json().get("image") or target_check.json()
        target_status = target_image.get("status", "")
        if target_status == "active":
            print(f"✅ 타겟 리전({target_region})에 이미지가 이미 존재함 (복제 불필요)")
            print(f"   이미지 ID: {source_id}, 상태: {target_status}")
            out = os.environ.get("GITHUB_OUTPUT")
            if out:
                with open(out, "a") as f:
                    f.write(f"target_image_id={source_id}\n")
                    f.write(f"target_region={target_region}\n")
            return  # 복제 불필요, 이미 존재
        else:
            print(f"ℹ️  타겟 리전에 이미지가 있지만 상태가 {target_status}입니다. 복제 진행...")
    elif target_check.status_code == 404:
        print(f"ℹ️  타겟 리전({target_region})에 이미지가 없습니다. 복제 진행...")
    else:
        print(f"⚠️  타겟 리전 이미지 확인 실패: {target_check.status_code}. 복제 진행...")

    # 0-1) 토큰 권한 검증 (Image API 접근 가능 여부 확인)
    print("🔍 토큰 권한 검증 중...")
    test_list = requests.get(f"{source_base}/v2/images", headers=headers_json, params={"limit": 1})
    if test_list.status_code == 401:
        print("❌ 토큰이 유효하지 않거나 만료됨 (401 Unauthorized)", file=sys.stderr)
        sys.exit(1)
    if test_list.status_code == 403:
        print("❌ 토큰에 Image API 접근 권한이 없음 (403 Forbidden)", file=sys.stderr)
        print("   NHN Cloud 콘솔에서 사용자에게 Image 서비스에 대한 'member' 또는 'admin' 역할을 부여하세요.", file=sys.stderr)
        sys.exit(1)
    if not test_list.ok:
        print(f"⚠️  Image API 접근 테스트 실패: {test_list.status_code}", file=sys.stderr)
    else:
        print("✅ 토큰 권한 검증 완료")

    # 1) 소스 이미지 상세 조회 (disk_format, container_format 등)
    r = requests.get(f"{source_base}/v2/images/{source_id}", headers=headers_json)
    if r.status_code == 404:
        print(f"❌ 소스 이미지를 찾을 수 없음: {source_id}", file=sys.stderr)
        sys.exit(1)
    if r.status_code == 403:
        print(f"❌ 소스 이미지 메타데이터 접근 권한 없음: {source_id}", file=sys.stderr)
        print(f"   토큰이 Image API에 대한 읽기 권한이 있는지 확인하세요.", file=sys.stderr)
        sys.exit(1)
    r.raise_for_status()
    image_meta = r.json().get("image") or r.json()
    container_format = image_meta.get("container_format") or "bare"
    disk_format = image_meta.get("disk_format") or "raw"
    
    # 이미지 소유자 및 권한 확인 (디버깅용)
    owner = image_meta.get("owner")
    visibility = image_meta.get("visibility", "unknown")
    status = image_meta.get("status", "")
    locations = image_meta.get("locations", [])
    file_url = image_meta.get("file")  # 일부 OpenStack 구현에서 제공
    print(f"ℹ️  이미지 정보: owner={owner}, visibility={visibility}, status={status}")
    if locations:
        print(f"ℹ️  이미지 locations: {locations}")
    if file_url:
        print(f"ℹ️  이미지 file URL: {file_url}")
    
    # 참고: NHN Cloud 콘솔의 "다른 리전으로 복제" 기능은 API로 제공되지 않음
    # 따라서 파일 다운로드/업로드 방식이 유일한 API 기반 솔루션

    # 1-1) 이미지가 active 상태가 될 때까지 대기 (파일 다운로드 전 필수)
    if status != "active":
        print(f"⏳ 이미지가 active 상태가 될 때까지 대기 중... (현재: {status})")
        max_wait = 600
        start = time.time()
        while time.time() - start < max_wait:
            r = requests.get(f"{source_base}/v2/images/{source_id}", headers=headers_json)
            r.raise_for_status()
            img = r.json().get("image") or r.json()
            status = img.get("status", "")
            if status == "active":
                print(f"✅ 이미지 active 상태 확인")
                break
            if status in ("killed", "deleted", "error"):
                print(f"❌ 이미지 상태가 {status}입니다. 복제할 수 없습니다.", file=sys.stderr)
                sys.exit(1)
            print(f"  이미지 상태: {status}, 대기 중...")
            time.sleep(10)
        else:
            print(f"❌ 이미지 active 대기 타임아웃 (현재 상태: {status})", file=sys.stderr)
            sys.exit(1)

    # 2) 소스 이미지 파일 스트림
    print(f"📥 소스 리전에서 이미지 다운로드 중: {source_id}")
    get_file = requests.get(
        f"{source_base}/v2/images/{source_id}/file",
        headers=headers,
        stream=True,
    )
    if get_file.status_code == 403:
        print(f"❌ 이미지 파일 다운로드 권한 없음 (403 Forbidden)", file=sys.stderr)
        print(f"   요청 URL: {get_file.url}", file=sys.stderr)
        print(f"   응답 헤더: {dict(get_file.headers)}", file=sys.stderr)
        print(f"   응답 본문: {get_file.text[:500] if get_file.text else '(empty)'}", file=sys.stderr)
        print(f"   원인 가능성:", file=sys.stderr)
        print(f"   1. 토큰에 Image API 파일 다운로드 권한이 없음", file=sys.stderr)
        print(f"   2. 이미지 소유자({owner})와 토큰 테넌트가 다름", file=sys.stderr)
        print(f"   3. 이미지가 private이고 공유되지 않음", file=sys.stderr)
        print(f"   4. NHN Cloud에서 이미지 파일 다운로드가 제한됨 (콘솔에서만 복제 가능)", file=sys.stderr)
        print(f"   해결 방법:", file=sys.stderr)
        print(f"   - NHN Cloud 콘솔에서 수동으로 리전 간 복제 수행", file=sys.stderr)
        print(f"   - 또는 NHN Cloud 기술 지원에 API 기반 복제 기능 요청", file=sys.stderr)
        print(f"   - 또는 Compute API를 통해 이미지 내보내기 사용 (Nova export)", file=sys.stderr)
        sys.exit(1)
    get_file.raise_for_status()

    # 3) 타겟 리전에 이미지 생성 (메타데이터만)
    # visibility를 shared로 설정하여 파일 다운로드 권한 문제 해결
    create_body = {
        "name": source_name,
        "container_format": container_format,
        "disk_format": disk_format,
        "visibility": "shared",
    }
    create = requests.post(
        f"{target_base}/v2/images",
        headers=headers_json,
        json=create_body,
    )
    if not create.ok:
        print(f"❌ 타겟 리전 이미지 생성 실패: {create.status_code}", file=sys.stderr)
        print(create.text[:500], file=sys.stderr)
        sys.exit(1)
    target_image = create.json().get("image") or create.json()
    target_id = target_image.get("id")
    if not target_id:
        print("❌ 타겟 이미지 ID를 찾을 수 없음", file=sys.stderr)
        sys.exit(1)
    print(f"📤 타겟 리전({target_region}) 이미지 생성됨: {target_id}, 업로드 중...")

    # 4) 타겟에 이미지 데이터 업로드 (PUT /file)
    # 스트리밍 업로드: iter_content를 사용하여 메모리 효율적으로 전송
    put_headers = {"X-Auth-Token": token, "Content-Type": "application/octet-stream"}
    content_length = get_file.headers.get("Content-Length")
    if content_length:
        put_headers["Content-Length"] = content_length
    
    print(f"📤 타겟 리전({target_region})에 이미지 데이터 업로드 중...")
    # iter_content로 청크 단위로 스트리밍 업로드
    def generate_chunks():
        for chunk in get_file.iter_content(chunk_size=8192 * 1024):  # 8MB 청크
            if chunk:
                yield chunk
    
    upload = requests.put(
        f"{target_base}/v2/images/{target_id}/file",
        headers=put_headers,
        data=generate_chunks(),
        timeout=3600,
    )
    if not upload.ok:
        print(f"❌ 타겟 리전 이미지 업로드 실패: {upload.status_code}", file=sys.stderr)
        print(upload.text[:500], file=sys.stderr)
        sys.exit(1)

    # 5) active 될 때까지 대기
    max_wait = 900
    start = time.time()
    while time.time() - start < max_wait:
        r = requests.get(f"{target_base}/v2/images/{target_id}", headers=headers_json)
        r.raise_for_status()
        img = r.json().get("image") or r.json()
        status = img.get("status", "")
        if status == "active":
            print(f"✅ 이미지 복사 완료: {target_region} image_id={target_id}")
            out = os.environ.get("GITHUB_OUTPUT")
            if out:
                with open(out, "a") as f:
                    f.write(f"target_image_id={target_id}\n")
                    f.write(f"target_region={target_region}\n")
            return
        if status == "killed" or status == "deleted":
            print(f"❌ 이미지 상태: {status}", file=sys.stderr)
            sys.exit(1)
        print(f"  타겟 이미지 상태: {status}, 대기 중...")
        time.sleep(15)

    print("❌ 타겟 이미지 active 대기 타임아웃", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
