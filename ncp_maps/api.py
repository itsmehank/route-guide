"""NCP Maps API 별 요청 래퍼 + 응답 파싱 헬퍼.

좌표는 전부 (경도 lon, 위도 lat) 튜플로 다룬다. NCP Maps 는 모든 API 에서
"경도,위도" 순서를 쓴다 — 위도/경도 순서로 넣으면 조용히 엉뚱한 결과가 나온다.
"""
from __future__ import annotations

import html
import math
import re
from typing import Any, Sequence

from .client import (
    MapsClient,
    PATH_DIRECTIONS_5,
    PATH_DIRECTIONS_15,
    PATH_GEOCODE,
    PATH_LOCAL_SEARCH,
    PATH_REVERSE_GEOCODE,
    PATH_STATIC_MAP,
)

Coord = tuple[float, float]  # (경도, 위도)

DRIVING_OPTIONS = ("trafast", "tracomfort", "traoptimal")
OPTION_LABELS = {
    "trafast": "실시간 빠른길",
    "tracomfort": "편한길",
    "traoptimal": "실시간 최적",
    "traavoidtoll": "무료 우선",
    "traavoidcaronly": "자동차전용도로 회피",
}


def fmt_coord(coord: Coord) -> str:
    """API 쿼리용 '경도,위도' 문자열."""
    return f"{coord[0]},{coord[1]}"


# --------------------------------------------------------------------------
# 지역 검색 (NAVER API HUB) — 장소명/상호/랜드마크 검색
# --------------------------------------------------------------------------
# 실측으로 확인된 제약 (2026-09-10):
#   - display 는 1~5. 그 이상 못 받는다.
#   - start 파라미터가 무시된다. 페이징 불가.
#   - total 은 전체 결과 수가 아니라 반환 건수(= display).
#   - title 에 <b> 태그가 섞여 온다. 반드시 스트립할 것.
#   - mapx/mapy 는 WGS84 × 10^7 정수 문자열. 1e7 로 나눠야 경도/위도가 된다.
#   - telephone 은 항상 빈 값.
LOCAL_SEARCH_MAX_DISPLAY = 5
TRANSIT_CATEGORY_PREFIX = "교통,운수"

_TAG_RE = re.compile(r"<[^>]+>")


def local_search(client: MapsClient, query: str, name: str,
                 display: int = LOCAL_SEARCH_MAX_DISPLAY,
                 sort: str = "random") -> dict:
    """장소명으로 POI 를 검색한다. Maps 가 아니라 NAVER API HUB 클라이언트를 넘길 것."""
    if not 1 <= display <= LOCAL_SEARCH_MAX_DISPLAY:
        raise ValueError(f"display 는 1~{LOCAL_SEARCH_MAX_DISPLAY} 만 가능합니다.")
    return client.get(name, PATH_LOCAL_SEARCH,
                      {"query": query, "display": display, "sort": sort})


def strip_tags(text: str) -> str:
    """title 에 섞여 오는 <b> 등의 태그를 제거한다."""
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def hub_coord(item: dict) -> Coord:
    """mapx/mapy (WGS84 × 10^7 정수 문자열) → (경도, 위도)."""
    return (int(item["mapx"]) / 1e7, int(item["mapy"]) / 1e7)


def parse_places(payload: dict, *, transit_only: bool = False) -> list[dict]:
    """지역 검색 응답을 다루기 쉬운 후보 목록으로 정규화한다."""
    places = []
    for item in payload.get("items", []):
        category = item.get("category", "")
        if transit_only and not category.startswith(TRANSIT_CATEGORY_PREFIX):
            continue
        places.append({
            "title": strip_tags(item.get("title", "")),
            "category": category,
            "road_address": item.get("roadAddress", ""),
            "jibun_address": item.get("address", ""),
            "coord": hub_coord(item),
        })
    return places


# --------------------------------------------------------------------------
# Geocoding
# --------------------------------------------------------------------------
def geocode(client: MapsClient, query: str, name: str, count: int = 1) -> dict:
    """주소 → 좌표. 지번/도로명 주소는 잘 되지만 '죽전역' 같은 POI 명은 실패할 수 있다."""
    return client.get(name, PATH_GEOCODE, {"query": query, "count": count})


def first_address(payload: dict) -> dict | None:
    addresses = payload.get("addresses") or []
    return addresses[0] if addresses else None


def address_to_coord(address: dict) -> Coord:
    """addresses[0] 의 x=경도, y=위도. (문자열로 오므로 float 변환 필요)"""
    return (float(address["x"]), float(address["y"]))


# --------------------------------------------------------------------------
# Reverse Geocoding
# --------------------------------------------------------------------------
def reverse_geocode(client: MapsClient, coord: Coord, name: str,
                    orders: str = "roadaddr,addr") -> dict:
    """좌표 → 주소. output=json 을 명시하지 않으면 XML 이 돌아온다."""
    return client.get(name, PATH_REVERSE_GEOCODE, {
        "coords": fmt_coord(coord),
        "orders": orders,
        "output": "json",
    })


def format_reverse_result(result: dict) -> str:
    """results[] 한 건을 사람이 읽는 주소 문자열로 조립."""
    region = result.get("region", {})
    land = result.get("land") or {}
    parts = [region.get(f"area{i}", {}).get("name", "") for i in range(1, 5)]
    parts = [p for p in parts if p]

    if result.get("name") == "roadaddr":
        # 도로명: area1 area2 + 도로명 + 건물번호(-번호2) + 건물명
        road = land.get("name", "")
        number = land.get("number1", "")
        if land.get("number2"):
            number = f"{number}-{land['number2']}"
        building = (land.get("addition0") or {}).get("value", "")
        head = " ".join(p for p in parts[:2] if p)
        tail = " ".join(p for p in (road, number, building) if p)
        return " ".join(p for p in (head, tail) if p)

    # 지번(addr): area1~area4 + 번지
    number = land.get("number1", "")
    if land.get("number2"):
        number = f"{number}-{land['number2']}"
    return " ".join(p for p in (*parts, number) if p)


def reverse_results_by_name(payload: dict) -> dict[str, dict]:
    return {r.get("name", "?"): r for r in payload.get("results", [])}


# --------------------------------------------------------------------------
# Directions 5 / 15
# --------------------------------------------------------------------------
def directions(client: MapsClient, start: Coord, goal: Coord, name: str,
               *, version: int = 5,
               waypoints: Sequence[Coord] = (),
               options: Sequence[str] = DRIVING_OPTIONS) -> dict:
    """자동차 경로 탐색.

    option 은 ':' 로 최대 3개까지 한 번에 요청할 수 있다 —
    옵션마다 따로 호출하면 호출 건수가 3배가 되므로 한 번에 묶어 보낸다.
    waypoints 는 '|' 로 최대 5개.
    """
    if len(options) > 3:
        raise ValueError("option 은 한 번에 최대 3개까지만 지정할 수 있습니다.")
    if len(waypoints) > 5:
        raise ValueError("waypoints 는 최대 5개까지만 지정할 수 있습니다.")

    params: dict[str, Any] = {
        "start": fmt_coord(start),
        "goal": fmt_coord(goal),
        "option": ":".join(options),
    }
    if waypoints:
        params["waypoints"] = "|".join(fmt_coord(w) for w in waypoints)

    path = PATH_DIRECTIONS_5 if version == 5 else PATH_DIRECTIONS_15
    return client.get(name, path, params)


def route_summaries(payload: dict) -> dict[str, dict]:
    """route.{option}[0] 을 옵션별 요약 dict 로 정규화한다.

    distance 는 meter, duration 은 millisecond 로 온다.
    """
    summaries: dict[str, dict] = {}
    for option, routes in (payload.get("route") or {}).items():
        if not routes:
            continue
        route = routes[0]
        summary = route.get("summary", {})
        summaries[option] = {
            "option": option,
            "label": OPTION_LABELS.get(option, option),
            "distance_km": summary.get("distance", 0) / 1000,
            "duration_min": summary.get("duration", 0) / 1000 / 60,
            "taxi_fare": summary.get("taxiFare"),
            "toll_fare": summary.get("tollFare"),
            "fuel_price": summary.get("fuelPrice"),
            "bbox": summary.get("bbox"),
            "path": route.get("path", []),
            "section_count": len(route.get("section", [])),
            "guide_count": len(route.get("guide", [])),
        }
    return summaries


def path_midpoint(path: Sequence[Sequence[float]]) -> Coord:
    """경로 좌표 배열의 '중간 지점'(누적 거리 기준이 아니라 인덱스 기준 중앙)."""
    if not path:
        raise ValueError("path 가 비어 있습니다.")
    point = path[len(path) // 2]
    return (float(point[0]), float(point[1]))


# --------------------------------------------------------------------------
# Static Map
# --------------------------------------------------------------------------
def pick_level(bbox: Sequence[Sequence[float]], width: int, height: int) -> int:
    """bbox 가 이미지 안에 들어오는 최대 확대 레벨을 고른다 (0~20).

    웹 메르카토르 기준 level 0 에서 256px 이 경도 360도를 덮는다는 관계를 쓴다.
    """
    (min_lon, min_lat), (max_lon, max_lat) = bbox
    lon_span = max(abs(max_lon - min_lon), 1e-6)
    lat_span = max(abs(max_lat - min_lat), 1e-6)

    def merc_y(lat: float) -> float:
        """위도를 [-1, 1] 로 정규화한 웹 메르카토르 Y."""
        lat = max(min(lat, 85.05), -85.05)
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / math.pi

    # level z 에서 세계 지도는 256 * 2^z px, 가로로 360도 / 세로로 정규화 2 단위를 덮는다.
    y_span = max(abs(merc_y(max_lat) - merc_y(min_lat)), 1e-9)

    level_lon = math.log2(360 * width / (256 * lon_span))
    level_lat = math.log2(2 * height / (256 * y_span))
    return max(0, min(20, int(min(level_lon, level_lat)) - 1))


def marker(coord: Coord, *, color: str = "red", label: str | None = None,
           size: str = "mid") -> str:
    """Static Map markers 파라미터 1개. pos 는 '경도 위도'(공백 구분)."""
    parts = [f"type:{'d' if label is None else 'a'}", f"size:{size}",
             f"color:{color}", f"pos:{coord[0]} {coord[1]}"]
    if label:
        parts.append(f"label:{label}")
    return "|".join(parts)


def static_map(client: MapsClient, center: Coord, level: int, name: str,
               *, width: int = 800, height: int = 600,
               markers: Sequence[str] = (), fmt: str = "png",
               scale: int = 2) -> bytes:
    """지도 이미지(바이너리)를 받아온다. w/h 는 1~1024, level 은 0~20."""
    params: dict[str, Any] = {
        "w": width,
        "h": height,
        "center": fmt_coord(center),
        "level": level,
        "format": fmt,
        "scale": scale,
    }
    if markers:
        params["markers"] = list(markers)  # 같은 이름으로 반복 전송된다
    return client.get(name, PATH_STATIC_MAP, params, binary=True)
