"""로드뷰 정적 이미지 — 헤드리스 크롬으로 web/pano-shot.html 을 열어 한 장 찍는다.

브리핑을 HTML 파일로 내려받을 때 쓴다. 로드뷰 뷰어는 도메인 인증이 필요해 파일 안에서는 돌지 않으므로,
그 시점의 화면을 JPEG 로 찍어 넣는다. (개인 확인용. 네이버 로드뷰 이미지이므로 재배포하지 않는다.)

- 크롬 실행 파일은 macOS 기본 위치 또는 CHROME_PATH.
- 같은 (좌표, 방향, 크기)는 out/pano_cache/ 에 저장해 다시 찍지 않는다.
- 로드뷰가 없는 지점은 회색 화면만 찍힌다 → 파일 크기로 판정해 None.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

log = logging.getLogger("ncp.panoshot")

CHROME_CANDIDATES = [
    os.environ.get("CHROME_PATH", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "", shutil.which("chromium") or "",
]
TIMEOUT_S = 30
MIN_BYTES = 12_000    # 이보다 작으면 단색(로드뷰 없음)

_LIMIT = threading.Semaphore(3)   # 크롬 동시 실행 수


def chrome_path() -> str | None:
    return next((c for c in CHROME_CANDIDATES if c and Path(c).exists()), None)


def shoot(base_url: str, cache_dir: Path, lon: float, lat: float, pan: float,
          w: int = 640, h: int = 360, tilt: float = 2, fov: float = 90) -> bytes | None:
    key = hashlib.sha1(f"{lon:.6f},{lat:.6f},{pan:.0f},{tilt},{fov},{w}x{h}".encode()).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{key}.jpg"
    if out.exists():
        data = out.read_bytes()
        return data if len(data) >= MIN_BYTES else None
    chrome = chrome_path()
    if not chrome:
        log.warning("크롬을 찾지 못해 로드뷰를 찍을 수 없습니다 (CHROME_PATH 설정)")
        return None
    url = f"{base_url}/pano-shot.html?lon={lon}&lat={lat}&pan={pan:.1f}&tilt={tilt}&fov={fov}&w={w}&h={h}"
    with _LIMIT, tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "shot.png"
        cmd = [chrome, "--headless=new", "--hide-scrollbars", "--mute-audio", "--no-first-run",
               # 배율 1 로 고정해야 창 크기 = 그려지는 크기다. 레티나(2배)에서는 아래쪽이 회색으로 비었다(실측).
               f"--window-size={w},{h}", "--force-device-scale-factor=1", "--timeout=8000",
               f"--user-data-dir={tmp}/profile", f"--screenshot={png}", url]
        # 헤드리스 크롬은 스크린샷을 쓴 뒤에도 바로 끝나지 않는다(실측) → 파일이 다 써지면 끈다
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + TIMEOUT_S
            last = -1
            while time.monotonic() < deadline:
                if png.exists():
                    size = png.stat().st_size
                    if size > 0 and size == last:
                        break
                    last = size
                if proc.poll() is not None and not png.exists():
                    break
                time.sleep(0.3)
        finally:
            proc.kill()
            proc.wait(timeout=5)
        if not png.exists():
            log.warning("로드뷰 캡처 실패(시간 초과): %s,%s", lon, lat)
            return None
        # JPEG 로 줄인다 (macOS sips)
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "72", str(png), "--out", str(out)],
                       capture_output=True, timeout=20)
    if not out.exists():
        return None
    data = out.read_bytes()
    log.info("로드뷰 캡처 %s (%dKB)", out.name, len(data) // 1024)
    return data if len(data) >= MIN_BYTES else None
