"""NCP Maps API 저수준 HTTP 클라이언트.

- .env 에서 키를 읽고
- 모든 호출의 상태코드/소요시간/응답요약을 로깅하고
- 원본 응답을 out/raw/ 아래에 순번을 붙여 저장한다.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Iterable

import requests

log = logging.getLogger("ncp.client")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "out"
RAW_DIR = OUT_DIR / "raw"

# 2026-09 기준 실제로 동작하는 호스트.
# 공식 문서 일부 페이지(Directions/Reverse Geocoding 영문판)에는 아직
# naveropenapi.apigw.ntruss.com 이 남아 있으나, 신규 발급 키로 호출하면
# 401 {"errorCode":"210","message":"Permission Denied"} 가 떨어진다.
DEFAULT_HOST = "https://maps.apigw.ntruss.com"

# API 별 경로
PATH_GEOCODE = "/map-geocode/v2/geocode"
PATH_REVERSE_GEOCODE = "/map-reversegeocode/v2/gc"
PATH_DIRECTIONS_5 = "/map-direction/v1/driving"
PATH_DIRECTIONS_15 = "/map-direction-15/v1/driving"
PATH_STATIC_MAP = "/map-static/v2/raster"

# NAVER API HUB — Maps 와 다른 상품이라 호스트도 키도 별개다.
# 인증 헤더 이름은 같으므로(대소문자 무관) 같은 클라이언트 클래스를 재사용한다.
HUB_HOST = "https://naverapihub.apigw.ntruss.com"
PATH_LOCAL_SEARCH = "/search/v1/local"


class NcpApiError(RuntimeError):
    """API 호출 실패. 상태코드와 응답 본문을 그대로 들고 다닌다."""

    def __init__(self, name: str, status: int, body: str, url: str):
        self.name = name
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"[{name}] HTTP {status} — {body[:500]}")

    def hint(self) -> str:
        if self.status in (401, 403):
            return (
                "인증/권한 문제일 가능성이 큽니다. 확인할 것:\n"
                "  1) .env 의 NCP_MAPS_CLIENT_ID / NCP_MAPS_CLIENT_SECRET 오타·공백\n"
                "  2) NCP 콘솔에서 해당 Application 에 이 API(Geocoding/Directions/Static Map)가 '신청' 되어 있는지\n"
                "  3) 호스트: 현재 유효한 값은 maps.apigw.ntruss.com 이며, 구 호스트\n"
                "     naveropenapi.apigw.ntruss.com 은 신규 키에 401 Permission Denied 를 반환합니다\n"
                "  4) 서비스 환경(Web 서비스 URL / Android·iOS 앱 패키지) 등록 여부"
            )
        if self.status == 429:
            return "호출량 제한(Rate limit)에 걸렸습니다. 잠시 후 재시도하세요."
        if self.status == 400:
            return "요청 파라미터 오류입니다. 좌표 순서(경도,위도)와 파라미터 이름을 확인하세요."
        return ""


def load_env(path: Path | None = None) -> dict[str, str]:
    """.env 를 읽어 dict 로 돌려준다. 이미 export 된 환경변수가 우선한다."""
    path = path or (PROJECT_ROOT / ".env")
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    else:
        log.warning(".env 파일이 없습니다: %s (.env.example 을 복사해서 만드세요)", path)
    for key in ("NCP_MAPS_CLIENT_ID", "NCP_MAPS_CLIENT_SECRET", "NCP_MAPS_API_HOST",
                "NAVER_HUB_CLIENT_ID", "NAVER_HUB_CLIENT_SECRET", "NAVER_HUB_API_HOST"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def _redact(text: str, secrets: Iterable[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


class CallCounter:
    """여러 클라이언트가 out/raw/ 파일 순번을 공유하기 위한 카운터."""

    def __init__(self) -> None:
        self.value = 0

    def next(self) -> int:
        self.value += 1
        return self.value


class MapsClient:
    """NCP API Gateway 호출기.

    Maps 와 NAVER API HUB 는 상품도 호스트도 키도 다르지만 인증 헤더 이름이 같아
    같은 클래스를 host/key 만 바꿔 재사용한다.
    호출 1건 = 요금 1건이므로 재시도 루프를 두지 않는다.
    """

    def __init__(self, key_id: str, key: str, host: str = DEFAULT_HOST,
                 raw_dir: Path = RAW_DIR, counter: "CallCounter | None" = None):
        if not key_id or not key:
            raise ValueError(
                "NCP_MAPS_CLIENT_ID / NCP_MAPS_CLIENT_SECRET 가 비어 있습니다. "
                ".env 를 확인하세요."
            )
        self.host = host.rstrip("/")
        self.key_id = key_id
        self.key = key
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.counter = counter or CallCounter()
        self.session = requests.Session()
        self.session.headers.update({
            "x-ncp-apigw-api-key-id": key_id,
            "x-ncp-apigw-api-key": key,
            "Accept": "application/json",
        })

    def get(self, name: str, path: str, params: dict[str, Any],
            binary: bool = False) -> Any:
        """GET 1회. 성공하면 dict(또는 bytes), 실패하면 NcpApiError."""
        seq = self.counter.next()
        url = f"{self.host}{path}"
        started = time.monotonic()
        response = self.session.get(url, params=params, timeout=15)
        elapsed_ms = (time.monotonic() - started) * 1000

        safe_url = _redact(response.url, (self.key_id, self.key))
        log.info("[%02d] %s → HTTP %d (%.0f ms, %d bytes)",
                 seq, name, response.status_code, elapsed_ms,
                 len(response.content))
        log.debug("      URL: %s", safe_url)

        if response.status_code != 200:
            body = _redact(response.text, (self.key_id, self.key))
            self._save_raw(seq, name, body.encode("utf-8"), "error.txt")
            raise NcpApiError(name, response.status_code, body, safe_url)

        if binary:
            self._save_raw(seq, name, response.content,
                           _ext_for(response.headers.get("Content-Type", "")))
            return response.content

        try:
            payload = response.json()
        except ValueError as exc:
            body = _redact(response.text, (self.key_id, self.key))
            self._save_raw(seq, name, body.encode("utf-8"), "invalid.txt")
            raise NcpApiError(name, response.status_code,
                              f"JSON 파싱 실패: {exc} / 본문: {body[:300]}", safe_url)

        self._save_raw(seq, name, json.dumps(payload, ensure_ascii=False,
                                             indent=2).encode("utf-8"), "json")
        log.info("      %s", _summarize(payload))
        return payload

    def _save_raw(self, seq: int, name: str, content: bytes, ext: str) -> Path:
        target = self.raw_dir / f"{seq:02d}_{name}.{ext}"
        target.write_bytes(content)
        log.debug("      raw 저장: %s", target)
        return target


def _ext_for(content_type: str) -> str:
    if "png" in content_type:
        return "png"
    if "jpeg" in content_type or "jpg" in content_type:
        return "jpg"
    return "bin"


def _summarize(payload: dict) -> str:
    """응답 한 줄 요약 — API 마다 성공 표시 필드가 다르다."""
    if "items" in payload:  # 지역 검색 (NAVER API HUB)
        # total 은 전체 검색 결과 수가 아니라 반환 건수다 (display 와 항상 같음)
        return (f"items={len(payload['items'])} "
                f"(total={payload.get('total')} = 반환 건수, 총건수 아님)")
    if "status" in payload:  # Geocoding / Reverse Geocoding
        status = payload["status"]
        if isinstance(status, dict):  # Reverse Geocoding
            results = payload.get("results", [])
            names = ",".join(r.get("name", "?") for r in results)
            return (f"status={status.get('name')}({status.get('code')}) "
                    f"results={len(results)} [{names}]")
        meta = payload.get("meta", {})  # Geocoding
        return (f"status={status} totalCount={meta.get('totalCount')} "
                f"addresses={len(payload.get('addresses', []))}")
    if "code" in payload:  # Directions
        routes = payload.get("route") or {}
        opts = ",".join(routes.keys())
        return f"code={payload['code']} message={payload.get('message')} route=[{opts}]"
    return f"keys={list(payload.keys())}"
