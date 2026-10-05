#!/usr/bin/env python3
"""NCP Maps API 테스트 시나리오: 죽전역 → 강남역 자동차 경로.

실행:  python3 run_scenario.py

호출 건수(1회 실행 기준, 무료 이용량 아끼려고 최소화):
  Geocoding 3 / Directions 5 1 / Directions 15 1 / Reverse Geocoding 1 / Static Map 1
  Directions 는 option 을 ':' 로 묶어 3개 옵션을 한 번에 받는다.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import unicodedata
from pathlib import Path

from ncp_maps import MapsClient, NcpApiError, load_env
from ncp_maps.api import (
    Coord,
    DRIVING_OPTIONS,
    LOCAL_SEARCH_MAX_DISPLAY,
    local_search,
    parse_places,
    address_to_coord,
    directions,
    first_address,
    format_reverse_result,
    geocode,
    marker,
    path_midpoint,
    pick_level,
    reverse_geocode,
    reverse_results_by_name,
    route_summaries,
    static_map,
)
from ncp_maps.client import (
    CallCounter,
    DEFAULT_HOST,
    HUB_HOST,
    OUT_DIR,
    PROJECT_ROOT,
)

log = logging.getLogger("ncp.scenario")

# 지점별 해석 전략: ① 지역 검색(장소명) → ② Geocoding(주소) → ③ 폴백 좌표
#
# ①이 주력이다. Geocoding 은 주소 검색이라 "죽전역" 같은 장소명이 안 되고,
# 역의 실제 도로명주소('포은대로 지하 464')도 색인에 없어 빈 결과가 온다.
# 장소명 검색이 생기기 전에는 ③ 하드코딩 좌표에 의존해야 했다.
PLACES = {
    "origin": {
        "title": "죽전역",
        "query": "죽전역",                                        # ① 지역 검색
        "address_query": "경기도 용인시 수지구 포은대로 지하 464",   # ② Geocoding
        "fallback": (127.1076, 37.3245),                          # ③ 최후 수단
    },
    "goal": {
        "title": "강남역",
        "query": "강남역",
        "address_query": "서울특별시 강남구 강남대로 396",
        "fallback": (127.0276, 37.4979),
    },
    "waypoint": {
        "title": "판교역",
        "query": "판교역",
        "address_query": "경기도 성남시 분당구 판교역로 160",
        "fallback": (127.1112, 37.3947),
    },
}


# --------------------------------------------------------------------------
# 콘솔 표 출력 (한글 폭 보정)
# --------------------------------------------------------------------------
def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int, align: str = "left") -> str:
    gap = max(0, width - _width(text))
    return text + " " * gap if align == "left" else " " * gap + text


def print_table(headers: list[str], rows: list[list[str]], aligns: list[str] | None = None) -> None:
    aligns = aligns or ["left"] + ["right"] * (len(headers) - 1)
    widths = [max(_width(headers[i]), *(_width(r[i]) for r in rows)) if rows
              else _width(headers[i]) for i in range(len(headers))]
    line = "-+-".join("-" * w for w in widths)
    print("  " + " | ".join(_pad(h, widths[i], "left") for i, h in enumerate(headers)))
    print("  " + line)
    for row in rows:
        print("  " + " | ".join(_pad(c, widths[i], aligns[i]) for i, c in enumerate(row)))


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def money(value) -> str:
    return f"{value:,}원" if isinstance(value, (int, float)) else "-"


# --------------------------------------------------------------------------
# 1단계: 장소 해석 (지역 검색 → Geocoding → 폴백)
# --------------------------------------------------------------------------
def choose_place(places: list[dict], title: str, interactive: bool) -> dict:
    """후보 목록을 보여주고 하나를 고른다. 비대화형이면 1위를 자동 선택."""
    print()
    print(f"  '{title}' 검색 결과 {len(places)}건:")
    for n, place in enumerate(places, 1):
        print(f"    {n}. {place['title']}  [{place['category']}]")
        print(f"       {place['road_address']}  ({place['coord'][0]:.6f}, {place['coord'][1]:.6f})")

    # --interactive 는 명시적 opt-in 이므로 tty 여부로 막지 않는다.
    # (파이프로 선택지를 흘려넣어 재현 가능한 테스트를 돌릴 수 있어야 한다)
    if not interactive:
        print("  → 1번 자동 선택 (--interactive 로 직접 고를 수 있음)")
        return places[0]
    if len(places) == 1:
        print("  → 후보가 1건이라 자동 선택")
        return places[0]

    while True:
        try:
            raw = input(f"  선택 [1-{len(places)}, 기본 1]: ").strip()
        except EOFError:
            return places[0]
        if not raw:
            return places[0]
        if raw.isdigit() and 1 <= int(raw) <= len(places):
            return places[int(raw) - 1]
        print("  잘못된 번호입니다.")


def resolve_place(hub: MapsClient | None, maps: MapsClient, key: str,
                  *, interactive: bool = False, transit_only: bool = False) -> dict:
    """장소명 → 좌표. ① 지역 검색 ② Geocoding ③ 폴백 순으로 시도한다."""
    place = PLACES[key]
    info = {"key": key, "title": place["title"], "query": place["query"]}

    # ① 지역 검색 (장소명)
    if hub is not None:
        try:
            payload = local_search(hub, place["query"], name=f"localsearch_{key}",
                                   display=LOCAL_SEARCH_MAX_DISPLAY)
            candidates = parse_places(payload, transit_only=transit_only)
            if transit_only and not candidates:
                # 교통 필터로 다 걸러졌으면 필터 없이 다시 본다 (추가 호출 없음)
                candidates = parse_places(payload)
                if candidates:
                    log.warning("  %s → '%s' 카테고리 결과가 없어 필터를 해제했습니다",
                                place["title"], "교통,운수")
            if candidates:
                chosen = choose_place(candidates, place["title"], interactive)
                info.update(
                    coord=chosen["coord"],
                    road_address=chosen["road_address"],
                    jibun_address=chosen["jibun_address"],
                    matched_title=chosen["title"],
                    category=chosen["category"],
                    source="localsearch",
                    candidate_count=len(candidates),
                )
                log.info("  %s → '%s' 선택 (%.6f, %.6f)", place["title"],
                         chosen["title"], *chosen["coord"])
                return info
            log.warning("  %s → 지역 검색 결과 없음. Geocoding 으로 넘어갑니다", place["title"])
        except NcpApiError as exc:
            log.error("지역 검색 실패: %s", exc)
            log.error(exc.hint())

    # ② Geocoding (주소)
    address = None
    try:
        payload = geocode(maps, place["address_query"], name=f"geocode_{key}")
        address = first_address(payload)
    except NcpApiError as exc:
        log.error("지오코딩 실패: %s", exc)
        log.error(exc.hint())

    if address:
        info.update(
            coord=address_to_coord(address),
            road_address=address.get("roadAddress", ""),
            jibun_address=address.get("jibunAddress", ""),
            matched_title=address.get("roadAddress", ""),
            category="",
            source="geocoding",
            candidate_count=1,
        )
        log.info("  %s → %s (%.6f, %.6f)", place["title"], info["road_address"],
                 *info["coord"])
        return info

    # ③ 폴백 좌표
    info.update(
        coord=tuple(place["fallback"]),
        road_address="", jibun_address="", matched_title="(폴백 좌표)",
        category="", source="fallback", candidate_count=0,
    )
    log.warning("  %s → 검색·지오코딩 모두 실패. 폴백 좌표 사용 (%.4f, %.4f)",
                place["title"], *place["fallback"])
    return info


# --------------------------------------------------------------------------
# 4단계: 왕복 변환 검증
# --------------------------------------------------------------------------
def normalize_address(text: str) -> str:
    """비교용 정규화 — 공백 제거 + 건물명/부가정보 무시."""
    return "".join(text.split())


def roundtrip_check(expected: str, road_address: str) -> tuple[bool, str]:
    """1단계에서 얻은 주소가 역지오코딩 결과와 같은 곳을 가리키는지 확인.

    비교 대상은 '검색어'가 아니라 1단계가 확정한 도로명주소다.
    장소명 검색으로 넘어온 뒤로는 검색어("강남역")와 주소를 비교해봐야 의미가 없다.
    """
    wanted = normalize_address(expected)
    got = normalize_address(road_address)
    if not got:
        return False, "역지오코딩 도로명주소 없음"
    if wanted and (wanted in got or got in wanted):
        return True, "완전 일치"
    # 도로명 + 건물번호만 비교 (시/도 표기, 건물명 유무로 흔히 어긋난다)
    tokens = [t for t in expected.split() if t]
    core = "".join(tokens[-2:]) if len(tokens) >= 2 else wanted
    if core and core in got:
        return True, f"핵심 일치 ('{' '.join(tokens[-2:])}')"
    return False, "불일치"


# --------------------------------------------------------------------------
# Dynamic Map 산출물
# --------------------------------------------------------------------------
def write_web_assets(client_id: str, payload: dict) -> tuple[Path, Path]:
    route_json = OUT_DIR / "route.json"
    route_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    template = (PROJECT_ROOT / "web" / "index.template.html").read_text(encoding="utf-8")
    index_html = OUT_DIR / "index.html"
    index_html.write_text(template.replace("__NCP_KEY_ID__", client_id), encoding="utf-8")
    return route_json, index_html


# --------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="NCP Maps 시나리오: 장소 검색 → 선택 → 경로 탐색")
    ap.add_argument("--from", dest="origin", metavar="검색어",
                    help=f"출발지 검색어 (기본: {PLACES['origin']['query']})")
    ap.add_argument("--to", dest="goal", metavar="검색어",
                    help=f"도착지 검색어 (기본: {PLACES['goal']['query']})")
    ap.add_argument("--via", dest="waypoint", metavar="검색어",
                    help=f"경유지 검색어 (기본: {PLACES['waypoint']['query']})")
    ap.add_argument("--interactive", action="store_true",
                    help="후보 목록에서 직접 번호를 골라 선택 (기본: 1위 자동 선택)")
    ap.add_argument("--transit-only", action="store_true",
                    help="'교통,운수' 카테고리(역·터미널)만 후보로 남긴다")
    ap.add_argument("--no-search", action="store_true",
                    help="지역 검색을 건너뛰고 Geocoding 부터 시작한다")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    for key, value in (("origin", args.origin), ("goal", args.goal),
                       ("waypoint", args.waypoint)):
        if value:
            PLACES[key]["query"] = value
            PLACES[key]["address_query"] = value  # 사용자가 준 검색어를 그대로 Geocoding 에도 시도
            PLACES[key]["title"] = value

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    env = load_env()
    host = env.get("NCP_MAPS_API_HOST", DEFAULT_HOST)
    counter = CallCounter()
    try:
        client = MapsClient(env.get("NCP_MAPS_CLIENT_ID", ""),
                            env.get("NCP_MAPS_CLIENT_SECRET", ""), host=host,
                            counter=counter)
    except ValueError as exc:
        log.error("%s", exc)
        return 1

    # 지역 검색은 NAVER API HUB — Maps 와 호스트도 키도 다른 별개 상품이다.
    hub_host = env.get("NAVER_HUB_API_HOST", HUB_HOST)
    hub: MapsClient | None = None
    if args.no_search:
        log.info("--no-search: 지역 검색을 건너뜁니다")
    elif env.get("NAVER_HUB_CLIENT_ID") and env.get("NAVER_HUB_CLIENT_SECRET"):
        hub = MapsClient(env["NAVER_HUB_CLIENT_ID"], env["NAVER_HUB_CLIENT_SECRET"],
                         host=hub_host, counter=counter)
    else:
        log.warning("NAVER_HUB_CLIENT_ID/SECRET 미설정 — 장소명 검색을 건너뛰고 "
                    "Geocoding(주소)으로만 진행합니다")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Maps 호스트: %s", host)
    if hub:
        log.info("Hub  호스트: %s (지역 검색)", hub_host)
    report: dict = {"host": host, "hub_host": hub_host if hub else None}

    # ---------------- 1. Geocoding ----------------
    section("1단계 · 장소 해석 — 지역 검색 → 선택 → 좌표")
    resolve = lambda key: resolve_place(hub, client, key,
                                        interactive=args.interactive,
                                        transit_only=args.transit_only)
    origin = resolve("origin")
    goal = resolve("goal")
    waypoint = resolve("waypoint")

    source_label = {"localsearch": "지역검색", "geocoding": "지오코딩", "fallback": "폴백좌표"}
    print()
    print_table(
        ["지점", "검색어", "선택된 장소", "경도(x)", "위도(y)", "출처"],
        [[p["title"], p["query"], p["matched_title"][:24],
          f"{p['coord'][0]:.6f}", f"{p['coord'][1]:.6f}", source_label[p["source"]]]
         for p in (origin, goal, waypoint)],
        ["left", "left", "left", "right", "right", "left"],
    )
    report["places"] = {p["key"]: p for p in (origin, goal, waypoint)}

    # ---------------- 2. Directions 5 ----------------
    section("2단계 · Directions 5 — 옵션 3종 비교 (호출 1회)")
    try:
        d5_payload = directions(client, origin["coord"], goal["coord"],
                                name="directions5", version=5,
                                options=DRIVING_OPTIONS)
    except NcpApiError as exc:
        log.error("%s", exc)
        log.error(exc.hint())
        return 1

    d5 = route_summaries(d5_payload)
    if not d5:
        log.error("경로를 찾지 못했습니다: code=%s message=%s",
                  d5_payload.get("code"), d5_payload.get("message"))
        return 1

    ordered = [d5[o] for o in DRIVING_OPTIONS if o in d5]
    print()
    print_table(
        ["옵션", "설명", "거리(km)", "소요(분)", "택시요금", "통행료"],
        [[s["option"], s["label"], f"{s['distance_km']:.1f}",
          f"{s['duration_min']:.1f}", money(s["taxi_fare"]), money(s["toll_fare"])]
         for s in ordered],
        ["left", "left", "right", "right", "right", "right"],
    )
    report["directions5"] = {
        k: {kk: vv for kk, vv in v.items() if kk != "path"} for k, v in d5.items()
    }

    # ---------------- 3. Directions 15 (경유지) ----------------
    section("3단계 · Directions 15 — 판교역 경유 (호출 1회, 월 3,000건 무료)")
    try:
        d15_payload = directions(client, origin["coord"], goal["coord"],
                                 name="directions15", version=15,
                                 waypoints=[waypoint["coord"]],
                                 options=DRIVING_OPTIONS)
        d15 = route_summaries(d15_payload)
    except NcpApiError as exc:
        log.error("Directions 15 실패: %s", exc)
        log.error(exc.hint())
        d15 = {}

    if d15:
        rows = []
        for option in DRIVING_OPTIONS:
            base, via = d5.get(option), d15.get(option)
            if not (base and via):
                continue
            rows.append([
                option,
                f"{base['distance_km']:.1f} → {via['distance_km']:.1f}",
                f"{via['distance_km'] - base['distance_km']:+.1f}",
                f"{base['duration_min']:.1f} → {via['duration_min']:.1f}",
                f"{via['duration_min'] - base['duration_min']:+.1f}",
                f"{(via['toll_fare'] or 0) - (base['toll_fare'] or 0):+,}원",
            ])
        print()
        print(f"  경유지: {waypoint['title']} ({waypoint['coord'][0]:.4f}, {waypoint['coord'][1]:.4f})")
        print()
        print_table(
            ["옵션", "거리 D5→D15(km)", "Δ거리", "소요 D5→D15(분)", "Δ소요", "Δ통행료"],
            rows, ["left", "right", "right", "right", "right", "right"])
        report["directions15"] = {
            k: {kk: vv for kk, vv in v.items() if kk != "path"} for k, v in d15.items()
        }

    # ---------------- 4. Reverse Geocoding ----------------
    section("4단계 · Reverse Geocoding — 도착 좌표 → 주소 왕복 검증")
    roundtrip = None
    try:
        rg_payload = reverse_geocode(client, goal["coord"], name="reversegeocode",
                                     orders="roadaddr,addr")
        results = reverse_results_by_name(rg_payload)
        road = results.get("roadaddr")
        jibun = results.get("addr")
        road_text = format_reverse_result(road) if road else ""
        jibun_text = format_reverse_result(jibun) if jibun else ""

        # 도로명·지번 두 축으로 각각 대조한다. POI 좌표는 대표 지점(출입구 등)이라
        # 도로명이 어긋나도 같은 필지(지번)인 경우가 흔하다.
        expected_from = ("지역검색" if goal["source"] == "localsearch"
                         else "지오코딩" if goal["source"] == "geocoding" else "검색어")
        road_ok, road_why = roundtrip_check(
            goal["road_address"] or goal["query"], road_text)
        jibun_ok, jibun_why = roundtrip_check(
            goal["jibun_address"] or goal["query"], jibun_text)
        matched = road_ok or jibun_ok

        roundtrip = {
            "expected_road": goal["road_address"], "expected_jibun": goal["jibun_address"],
            "expected_from": expected_from, "roadaddr": road_text, "addr": jibun_text,
            "road_matched": road_ok, "jibun_matched": jibun_ok, "matched": matched,
        }
        mark = lambda ok: "✅" if ok else "⚠️ "
        print()
        print(f"  좌표         : {goal['coord'][0]:.6f}, {goal['coord'][1]:.6f}")
        print(f"  1단계 출처   : {expected_from}")
        print()
        print(f"  {mark(road_ok)} 도로명  1단계: {goal['road_address'] or '(없음)'}")
        print(f"          역변환: {road_text or '(없음)'}  → {road_why}")
        print(f"  {mark(jibun_ok)} 지번    1단계: {goal['jibun_address'] or '(없음)'}")
        print(f"          역변환: {jibun_text or '(없음)'}  → {jibun_why}")
        print()
        print(f"  판정         : {'✅ 같은 장소' if matched else '⚠️  불일치'}"
              f" ({'도로명·지번 모두 일치' if road_ok and jibun_ok else
                  '지번 기준 동일 필지' if jibun_ok else
                  '도로명만 일치' if road_ok else '두 축 모두 불일치'})")
        if matched and not (road_ok and jibun_ok):
            print("    ↳ POI 좌표는 그 장소의 대표 지점(출입구 등)이라 등록 주소와")
            print("      역지오코딩 도로명이 어긋날 수 있다. 좌표가 틀린 것은 아니다.")
        report["roundtrip"] = roundtrip
    except NcpApiError as exc:
        log.error("역지오코딩 실패: %s", exc)
        log.error(exc.hint())

    # ---------------- 5. Static Map ----------------
    section("5단계 · Static Map — 경로 중간 지점 지도 이미지")
    best = d5.get("traoptimal") or ordered[0]
    center = path_midpoint(best["path"])
    level = pick_level(best["bbox"], 800, 600) if best.get("bbox") else 11
    image_path = OUT_DIR / "static-map.png"
    try:
        image = static_map(
            client, center, level, name="staticmap", width=800, height=600,
            markers=[
                marker(origin["coord"], color="blue", label="S"),
                marker(goal["coord"], color="red", label="G"),
                marker(waypoint["coord"], color="green", label="W"),
            ],
        )
        image_path.write_bytes(image)
        print()
        print(f"  중심 좌표 : {center[0]:.6f}, {center[1]:.6f} (traoptimal 경로 중간)")
        print(f"  확대 레벨 : {level}")
        print(f"  저장       : {image_path.relative_to(PROJECT_ROOT)} ({len(image):,} bytes)")
        report["static_map"] = {"center": center, "level": level,
                                "file": str(image_path.relative_to(PROJECT_ROOT))}
    except NcpApiError as exc:
        log.error("Static Map 실패: %s", exc)
        log.error(exc.hint())

    # ---------------- Dynamic Map 산출물 ----------------
    section("Dynamic Map · 브라우저 확인용 out/index.html 생성")
    web_payload = {
        "places": {k: {"title": v["title"], "coord": list(v["coord"]),
                       "matched": v["matched_title"], "category": v["category"],
                       "roadAddress": v["road_address"], "source": v["source"]}
                   for k, v in (("origin", origin), ("goal", goal), ("waypoint", waypoint))},
        "directions5": {opt: {"label": s["label"], "distance_km": s["distance_km"],
                              "duration_min": s["duration_min"],
                              "toll_fare": s["toll_fare"], "taxi_fare": s["taxi_fare"],
                              "path": s["path"]}
                        for opt, s in d5.items()},
        "directions15": {opt: {"label": s["label"], "distance_km": s["distance_km"],
                               "duration_min": s["duration_min"],
                               "toll_fare": s["toll_fare"], "taxi_fare": s["taxi_fare"],
                               "path": s["path"]}
                         for opt, s in d15.items()},
    }
    route_json, index_html = write_web_assets(env.get("NCP_MAPS_CLIENT_ID", ""), web_payload)
    print()
    print(f"  {route_json.relative_to(PROJECT_ROOT)} / {index_html.relative_to(PROJECT_ROOT)} 생성")
    print("  ⚠️  Web Dynamic Map 인증은 콘솔에 등록된 서비스 URL에서만 통과한다.")
    print("      다음으로 띄운 뒤 http://localhost:3000 으로 열 것:")
    print("        python3 -m http.server 3000 -d out")

    # ---------------- 요약 리포트 ----------------
    section("요약 리포트")
    fastest = min(ordered, key=lambda s: s["duration_min"])
    shortest = min(ordered, key=lambda s: s["distance_km"])
    cheapest = min(ordered, key=lambda s: (s["toll_fare"] or 0) + (s["fuel_price"] or 0))
    print()
    print(f"  구간          : {origin['title']} → {goal['title']}")
    print(f"  최단 시간     : {fastest['option']} ({fastest['duration_min']:.1f}분, "
          f"{fastest['distance_km']:.1f}km)")
    print(f"  최단 거리     : {shortest['option']} ({shortest['distance_km']:.1f}km)")
    print(f"  최저 비용     : {cheapest['option']} (통행료 {money(cheapest['toll_fare'])} "
          f"+ 연료비 {money(cheapest['fuel_price'])})")
    if d15:
        via_opt = next((o for o in DRIVING_OPTIONS if o in d15), None)
        if via_opt:
            delta = d15[via_opt]["duration_min"] - d5[via_opt]["duration_min"]
            print(f"  경유지 영향   : {waypoint['title']} 경유 시 {via_opt} 기준 "
                  f"{delta:+.1f}분 ({d15[via_opt]['distance_km'] - d5[via_opt]['distance_km']:+.1f}km)")
    if roundtrip:
        axes = []
        if roundtrip["road_matched"]:
            axes.append("도로명")
        if roundtrip["jibun_matched"]:
            axes.append("지번")
        print(f"  주소 왕복검증 : {'일치' if roundtrip['matched'] else '불일치'}"
              f"{' (' + '·'.join(axes) + ' 기준)' if axes else ''} — "
              f"{roundtrip['addr'] or roundtrip['roadaddr'] or '(없음)'}")
    print(f"  장소 해석     : " + ", ".join(
        f"{p['title']}={source_label[p['source']]}" for p in (origin, goal, waypoint)))
    print(f"  총 API 호출   : {counter.value}회 (원본 응답: out/raw/)")
    print()

    (OUT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
