"""경로 위험 구간 매칭 — (b) 트랙.

설계: docs/superpowers/specs/2026-09-11-route-compare-design.md §(b)

두 종류의 소스를 하나의 hazard 스키마로 정규화한다.

  1) 도로교통공단 사고다발지역 API (data.go.kr B552061)
     - 경로가 지나는 시군구만 조회한다. 전국을 긁을 필요가 없다.
     - siDo = 행정표준코드 앞 2자리, guGun = 뒤 3자리 (11680 → "11" + "680"). 실측 확인.
     - geom_json 이 EPSG:4326 정상 JSON 이라 재투영이 필요 없다.
     - 폴리곤은 선정반경으로 만든 원의 근사이므로, 중심점(lo_crd/la_crd) + 유형별 반경으로
       충분하다. 폴리곤 교차 판정을 하지 않는 이유다.

  2) 표준데이터 파일 (data/*.json)
     - 단속카메라, 어린이보호구역, 노인장애인보호구역: 위도/경도 = WGS84. 그대로 쓴다.
     - 전국교통사고다발지역: 폴리곤이 EPSG:5179 라 쓰지 않고 위도/경도(WGS84)만 쓴다.
       (API 가 못 주는 '스쿨존어린이' 보완용)

좌표는 전부 (경도, 위도) WGS84 로 정규화해 격자 색인에 넣는다.
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger("ncp.hazards")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MLAT = 110540.0


def mlon(lat: float) -> float:
    return 111320.0 * math.cos(math.radians(lat))


# --------------------------------------------------------------------------
# 소스 정의
# --------------------------------------------------------------------------
# 사고다발지역: 서비스명 → (표시명, 선정반경 m). 반경은 data.go.kr 각 API 설명 기준.
# 실측으로 엔드포인트가 확인된 5종만 둔다 (보행자·스쿨존·법규위반별은 KOROAD 자체 포털 필요).
KOROAD_SERVICES = {
    "frequentzoneLg":      ("교통사고 다발지역", 150),
    "frequentzoneChild":   ("보행어린이 사고다발", 200),
    "frequentzoneOldman":  ("보행노인 사고다발", 100),
    "frequentzoneFreezing": ("결빙 사고다발", 200),
    "frequentzoneBicycle": ("자전거 사고다발", 200),
}
KOROAD_BASE = "http://apis.data.go.kr/B552061"

# 보행자 사고다발은 data.go.kr B552061 에 등록돼 있지 않다(실측 HTTP 400).
# KOROAD 자체 개방포털이 별도 authKey 로 제공한다. 응답 스키마는 B552061 과 동일하다.
KOROAD_PORTAL_BASE = "https://opendata.koroad.or.kr/data/rest/frequentzone"
KOROAD_PORTAL_TYPES = {
    "pedstrians": ("보행자 사고다발", 100),
}

# 표준데이터 파일: 파일명 → (type, 표시명, 기본 반경 m, 필드 매핑)
FILE_SOURCES = {
    "speed_camera": {
        "file": "전국무인교통단속카메라표준데이터.json",
        "label": "무인단속카메라", "radius": 60,
    },
    "school_zone": {
        "file": "전국어린이보호구역표준데이터.json",
        "label": "어린이보호구역", "radius": 200,
    },
    "senior_zone": {
        "file": "전국노인장애인보호구역표준데이터.json",
        "label": "노인·장애인보호구역", "radius": 200,
    },
    "accident_file": {
        "file": "전국교통사고다발지역표준데이터.json",
        "label": "사고다발지역", "radius": 200,
    },
}

# 단속구분 코드가 기관마다 다르게 들어온다(1/01/2/02/99/"01+02"...). 속도 단속만 신뢰한다.
SPEED_CAMERA_CODES = {"1", "01"}


# --------------------------------------------------------------------------
# 격자 색인 — 0.01도(약 1km) 셀. 전국 수만 점을 매 요청마다 전수 비교하지 않기 위해.
# --------------------------------------------------------------------------
CELL = 0.01


class GridIndex:
    def __init__(self) -> None:
        self.cells: dict[tuple[int, int], list[dict]] = {}
        self.count = 0

    def add(self, item: dict) -> None:
        lon, lat = item["coord"]
        key = (int(lon / CELL), int(lat / CELL))
        self.cells.setdefault(key, []).append(item)
        self.count += 1

    def near(self, lon: float, lat: float, radius_m: float) -> Iterable[dict]:
        # 반경을 셀 수로 환산해 주변 셀만 훑는다
        rx = max(1, int(radius_m / (mlon(lat) * CELL)) + 1)
        ry = max(1, int(radius_m / (MLAT * CELL)) + 1)
        cx, cy = int(lon / CELL), int(lat / CELL)
        for dx in range(-rx, rx + 1):
            for dy in range(-ry, ry + 1):
                yield from self.cells.get((cx + dx, cy + dy), ())


# --------------------------------------------------------------------------
# 파일 로딩
# --------------------------------------------------------------------------
def _rows(path: Path) -> list[dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d["records"] if isinstance(d, dict) and "records" in d else d


def _f(v: Any) -> float | None:
    try:
        x = float(v)
        return x if x else None
    except (TypeError, ValueError):
        return None


def load_file_sources(data_dir: Path = DATA_DIR) -> GridIndex:
    """표준데이터 파일들을 하나의 격자 색인으로 적재한다. 없는 파일은 건너뛴다."""
    idx = GridIndex()
    for kind, spec in FILE_SOURCES.items():
        path = data_dir / spec["file"]
        if not path.exists():
            log.warning("데이터 파일 없음: %s", path.name)
            continue
        n = 0
        for r in _rows(path):
            lon, lat = _f(r.get("경도")), _f(r.get("위도"))
            if lon is None or lat is None:
                continue
            item = _normalize_file_row(kind, spec, r, lon, lat)
            if item:
                idx.add(item)
                n += 1
        log.info("  %-14s %6d건 적재", kind, n)
    log.info("위험 격자 색인: %d건 / %d셀", idx.count, len(idx.cells))
    return idx


def _normalize_file_row(kind: str, spec: dict, r: dict, lon: float, lat: float) -> dict | None:
    base = {"type": kind, "coord": (lon, lat), "radius": spec["radius"]}

    if kind == "speed_camera":
        # 속도 단속만 쓴다. 주정차·전용차로는 운전 경로 안내에 의미가 없고 제한속도도 0이다.
        if str(r.get("단속구분", "")).strip() not in SPEED_CAMERA_CODES:
            return None
        spd = _f(r.get("제한속도"))
        base["text"] = f"무인단속카메라 — 제한속도 {int(spd)}km/h" if spd else "무인단속카메라"
        base["source"] = f"경찰청 표준데이터 {r.get('데이터기준일자', '')}"
        base["detail"] = r.get("설치장소") or r.get("소재지도로명주소", "")
        return base

    if kind in ("school_zone", "senior_zone"):
        spd = _f(r.get("제한속도"))
        name = r.get("대상시설명", "")
        label = spec["label"]
        base["text"] = f"{label} — {name}" + (f" (제한속도 {int(spd)}km/h)" if spd else "")
        base["source"] = f"표준데이터 {r.get('데이터기준일자', '')}"
        base["detail"] = r.get("소재지도로명주소", "")
        return base

    if kind == "accident_file":
        # API 가 주지 못하는 '스쿨존어린이'만 파일에서 보완한다. 나머지는 API 가 더 최신이다.
        if r.get("사고유형구분") != "스쿨존어린이":
            return None
        yr, cnt = r.get("사고연도", ""), r.get("사고건수", "")
        dead = _f(r.get("사망자수")) or 0
        base["type"] = "accident_schoolzone"
        base["radius"] = 300          # 스쿨존어린이 선정반경
        base["text"] = (f"어린이보호구역 내 어린이 사고다발 — {yr}년 {cnt}건"
                        + (f", 사망 {int(dead)}명" if dead else ""))
        base["source"] = f"TAAS {yr}"
        base["detail"] = r.get("사고지역위치명", "")
        return base
    return None


# --------------------------------------------------------------------------
# 사고다발지역 API
# --------------------------------------------------------------------------
def fetch_koroad(api_key: str, service: str, region_code: str,
                 year: str, timeout: int = 20) -> list[dict]:
    """region_code 는 행정표준코드 5자리. siDo 2 + guGun 3 으로 쪼개 보낸다."""
    label, radius = KOROAD_SERVICES[service]
    rest = f"getRest{service[0].upper()}{service[1:]}"
    q = urllib.parse.urlencode({
        "serviceKey": api_key, "type": "json", "searchYearCd": year,
        "siDo": region_code[:2], "guGun": region_code[2:],
        "numOfRows": 100, "pageNo": 1,
    })
    url = f"{KOROAD_BASE}/{service}/{rest}?{q}"
    d = None
    for attempt in range(3):                      # 포털이 간헐적으로 느리다. 2회까지 재시도.
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            break
        except Exception as exc:
            if attempt == 2:
                log.warning("사고다발 조회 실패 %s/%s: %s", service, region_code, exc)
                return []
            time.sleep(1 + attempt)

    return _parse_frequentzone(d, service, label, radius, year)


# 지자체별(frequentzoneLg)은 구 단위가 아니라 '시' 단위 top3 를 돌려준다(실측).
# 용인시 수지구/기흥구가 동일 결과이므로 시 코드(앞 4자리)로 한 번만 호출한다.
CITY_LEVEL_SERVICES = {"frequentzoneLg"}


def plan_calls(service: str, codes: list[str]) -> list[str]:
    """이 서비스에 대해 실제로 호출할 시군구 코드 목록."""
    if service not in CITY_LEVEL_SERVICES:
        return codes
    seen, out = set(), []
    for c in codes:
        if c[:4] not in seen:
            seen.add(c[:4]); out.append(c)
    return out


def dedupe(items: list[dict]) -> list[dict]:
    """같은 지점이 여러 경로로 들어오는 것을 막는다 (유형 + 좌표 5자리)."""
    seen, out = set(), []
    for it in items:
        key = (it["type"], round(it["coord"][0], 5), round(it["coord"][1], 5))
        if key in seen:
            continue
        seen.add(key); out.append(it)
    return out


def fetch_koroad_portal(auth_key: str, kind: str, region_code: str,
                        year: str, timeout: int = 25) -> list[dict]:
    """KOROAD 자체 포털(보행자 등). B552061 과 파라미터·응답이 같고 키 이름만 authKey 다."""
    label, radius = KOROAD_PORTAL_TYPES[kind]
    q = urllib.parse.urlencode({
        "authKey": auth_key, "type": "json", "searchYearCd": year,
        "siDo": region_code[:2], "guGun": region_code[2:],
        "numOfRows": 100, "pageNo": 1,
    })
    url = f"{KOROAD_PORTAL_BASE}/{kind}?{q}"
    d = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            break
        except Exception as exc:
            if attempt == 2:
                log.warning("KOROAD 포털 조회 실패 %s/%s: %s", kind, region_code, exc)
                return []
            time.sleep(1 + attempt)
    return _parse_frequentzone(d, kind, label, radius, year)


def _parse_frequentzone(d: dict | None, type_key: str, label: str,
                        radius: int, year: str) -> list[dict]:
    """사고다발지역 응답(B552061 / KOROAD 포털 공통 스키마) → hazard 목록."""
    if not d or not d.get("totalCount"):
        return []
    out = []
    for it in d["items"]["item"]:
        lon, lat = _f(it.get("lo_crd")), _f(it.get("la_crd"))
        if lon is None or lat is None:
            continue
        dead = it.get("dth_dnv_cnt") or 0
        severe = it.get("se_dnv_cnt") or 0
        out.append({
            "type": type_key, "coord": (lon, lat), "radius": radius,
            "text": (f"{label} — {year}년 {it.get('occrrnc_cnt')}건, "
                     f"사상 {it.get('caslt_cnt')}명"
                     + (f" (사망 {dead}명)" if dead else f" (중상 {severe}명)" if severe else "")),
            "source": f"TAAS {year}",
            "detail": it.get("spot_nm", ""),
        })
    return out


def region_codes(maps_client, path: list, samples: int = 5) -> list[str]:
    """경로를 따라 몇 지점을 역지오코딩해 시군구 행정표준코드(5자리)를 모은다.

    경로 전체가 아니라 지나는 시군구만 조회하면 되므로 호출이 크게 줄어든다.
    """
    from .api import reverse_geocode

    if not path:
        return []
    step = max(1, len(path) // max(1, samples))
    codes: list[str] = []
    for i in range(0, len(path), step):
        lon, lat = path[i][0], path[i][1]
        try:
            d = reverse_geocode(maps_client, (lon, lat), name=f"region_{i}", orders="legalcode")
        except Exception as exc:
            log.warning("역지오코딩 실패(%d): %s", i, exc)
            continue
        for res in d.get("results", []):
            cid = (res.get("code") or {}).get("id") or ""
            if len(cid) >= 5 and cid[:5] not in codes:
                codes.append(cid[:5])
    return codes


# --------------------------------------------------------------------------
# 매칭
# --------------------------------------------------------------------------
def _dist_to_segment_m(p, a, b) -> float:
    lat = (a[1] + b[1]) / 2
    ml = mlon(lat)
    px, py = (p[0] - a[0]) * ml, (p[1] - a[1]) * MLAT
    bx, by = (b[0] - a[0]) * ml, (b[1] - a[1]) * MLAT
    L2 = bx * bx + by * by
    t = max(0.0, min(1.0, (px * bx + py * by) / L2)) if L2 else 0.0
    return math.hypot(px - bx * t, py - by * t)


# 데이터의 radius 는 '사고가 모인 범위(선정 반경)'라 경로와의 관련성 기준으로는 너무 넓다.
# (실측: 경부고속도로 경로에 247m 옆 일반도로의 서초초교 어린이 사고다발이 붙었다)
# 그래서 '내가 지나는 도로 위'인지로 다시 거른다: 경로선에서 이 거리 안이어야 한다.
ON_ROAD_M = {"speed_camera": 30, "school_zone": 60, "senior_zone": 60}
ON_ROAD_DEFAULT_M = 50                 # 사고다발 지점: 교차로 중심 기준
ON_FAST_ROAD_M = 30                    # 고속·자동차전용도로 위: 도로 폭 안쪽만
# 고속·자동차전용도로에는 보행자·자전거가 없고 학교·복지시설 앞도 아니다 — 옆 일반도로의 일이다
NOT_ON_FAST_ROAD = {"pedstrians", "frequentzoneChild", "frequentzoneOldman", "frequentzoneBicycle",
                    "accident_schoolzone", "school_zone", "senior_zone"}
FAST_ROAD_RE = re.compile(r"고속도로|고속화도로|도시고속|자동차전용|올림픽대로|강변북로|내부순환|"
                          r"북부간선|동부간선|서부간선|분당수서|제2경인|제3경인|수도권제1순환")


def fast_road_at(sections: list | None, idx: int) -> bool:
    for s in sections or []:
        if s["pointIndex"] <= idx <= s["pointIndex"] + s["pointCount"]:
            return bool(FAST_ROAD_RE.search(s.get("name", "")))
    return False


def on_route(h: dict, sections: list | None) -> bool:
    """이 위험 지점이 경로가 실제로 지나는 도로 위의 일인가."""
    if fast_road_at(sections, h["path_index"]):
        return h["type"] not in NOT_ON_FAST_ROAD and h["distance_m"] <= ON_FAST_ROAD_M
    return h["distance_m"] <= ON_ROAD_M.get(h["type"], ON_ROAD_DEFAULT_M)


def match_route(path: list, items: Iterable[dict], guides: list | None = None,
                sections: list | None = None) -> list[dict]:
    """경로선에서 각 위험지점의 반경 안에 들어오고, 경로가 지나는 도로 위인 것만 남긴다.
    가장 가까운 path 인덱스를 붙인다."""
    hits = []
    for it in items:
        best, best_i = float("inf"), 0
        for i in range(len(path) - 1):
            d = _dist_to_segment_m(it["coord"], path[i], path[i + 1])
            if d < best:
                best, best_i = d, i
                if best == 0:
                    break
        if best <= it["radius"]:
            h = dict(it)
            h["distance_m"] = round(best)
            h["path_index"] = best_i
            if not on_route(h, sections):
                continue
            if guides:
                h["step_near"] = min(
                    range(len(guides)),
                    key=lambda g: abs(guides[g].get("pointIndex", 0) - best_i))
            hits.append(h)
    hits.sort(key=lambda h: h["path_index"])
    return hits


def collect(path: list, guides: list, grid: GridIndex | None,
            koroad_items: Iterable[dict] = (), sections: list | None = None) -> list[dict]:
    """경로 하나에 대한 위험 구간 목록. 격자에서 후보를 뽑아 반경 매칭한다."""
    cand: dict[int, dict] = {}
    if grid is not None:
        step = max(1, len(path) // 200)     # 200점 간격으로 주변 셀만 훑는다
        for i in range(0, len(path), step):
            lon, lat = path[i][0], path[i][1]
            for it in grid.near(lon, lat, 350):
                cand[id(it)] = it
    items = dedupe(list(cand.values()) + list(koroad_items))
    return match_route(path, items, guides, sections)


def to_facts(hazards: list[dict], rid: str) -> list[dict]:
    """evaluate.py 의 사실 스키마에 맞춰 변환한다 (R1.H1 형식)."""
    out = []
    for n, h in enumerate(hazards, 1):
        text = h["text"]
        if h.get("detail"):
            text += f" — {h['detail']}"
        f = {"id": f"{rid}.H{n}", "kind": "hazard", "type": h["type"],
             "text": text, "source": h.get("source", ""),
             "distance_m": h["distance_m"]}
        if "step_near" in h:
            f["step"] = h["step_near"]
        out.append(f)
    return out


# --------------------------------------------------------------------------
# 진입점 — 경로 하나에 대한 위험 구간 수집
# --------------------------------------------------------------------------
def fetch_all(data_key: str | None, koroad_key: str | None, codes: list[str],
              year: str = "2024", workers: int = 8) -> tuple[list[dict], int]:
    """경로가 지나는 시군구들에 대해 사고다발 전 유형을 모은다. (hazards, 호출수)

    KOROAD 포털이 호출당 10초 넘게 걸리는 경우가 있어 병렬로 던진다.
    순차 실행 시 34회에 113초, 병렬 8로 약 20초(실측).
    """
    from concurrent.futures import ThreadPoolExecutor

    jobs = []
    if data_key:
        for svc in KOROAD_SERVICES:
            jobs += [(fetch_koroad, data_key, svc, c, year) for c in plan_calls(svc, codes)]
    if koroad_key:
        for kind in KOROAD_PORTAL_TYPES:
            jobs += [(fetch_koroad_portal, koroad_key, kind, c, year) for c in codes]

    items: list[dict] = []
    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for part in pool.map(lambda j: j[0](*j[1:]), jobs):
                items += part
    return items, len(jobs)
