"""경로 평가 지표 엔진 — LLM 없이 결정적으로 계산한다.

설계: docs/superpowers/specs/2026-09-11-route-compare-design.md

입력은 serve.py 가 만든 경로 dict 목록(summary/path/sections/guides 정규화본).
출력은 (1) 지표, (2) 편의 점수·순위, (3) LLM 에 넘길 '사실' 목록이다.
사실마다 ID(R1.F3 형식)를 붙여 LLM 이 문장별 근거로 인용하게 하고,
서버가 그 ID 가 실재하는지 검증한다.

알려진 한계: 차선 정보가 응답에 없어 '차선 변경'은 측정 불가. 합류·분기 횟수로 대리한다.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

# --------------------------------------------------------------------------
# 분기점 분류
# --------------------------------------------------------------------------
# guide.type 중 실제 응답과 문서로 확인된 코드만 쓴다. 나머지는 문구로 판정한다.
CODE_KIND = {
    1: "straight", 2: "left", 3: "right", 6: "uturn",
    42: "branch", 55: "overpass", 62: "overpass", 67: "hwy_exit",
    73: "underpass", 74: "sideroad", 87: "via", 88: "goal",
    121: "toll", 122: "toll", 123: "toll",
}

KIND_LABEL = {
    "uturn": "유턴", "toll": "톨게이트", "hwy_exit": "고속도로 출구",
    "overpass": "고가차도 진입", "underpass": "지하차도 진입", "sideroad": "옆길·합류",
    "branch": "분기(방향 선택)", "left": "좌회전", "right": "우회전",
    "straight": "직진", "via": "경유지", "goal": "목적지", "other": "기타",
}

# 차선을 옮길 일이 생기는 종류 — '합류·분기 횟수'의 정의
LANE_SHIFT_KINDS = ("branch", "hwy_exit", "sideroad", "overpass", "underpass")
# 로드뷰로 미리 봐두면 좋은 종류
COMPLEX_KINDS = ("uturn", "overpass", "underpass", "branch", "hwy_exit", "sideroad")

# 편의 점수 가중치 (낮을수록 편함). 첫 시안 — 여기서만 바꾼다.
WEIGHTS = {
    "base": 1.0,          # goal/via 제외 모든 분기점
    "uturn": 3.0,
    "grade_sep": 2.0,     # overpass + underpass
    "lane_shift": 2.0,    # branch + hwy_exit + sideroad
    "toll": 1.0,
    "slow_per_km": 0.5,   # 속도 < 20 구간 km 당
    "highway_bonus": 3.0, # 고속화 비율 × 이 값 만큼 감점
}
SLOW_SPEED_KMH = 20
HIGHWAY_SPEED_KMH = 60
HIGHWAY_NAME_RE = re.compile(r"고속도로|고속화도로|자동차전용")

_QUOTED_RE = re.compile(r"'[^']*'\s*방면으로\s*")
_AT_RE = re.compile(r"^.*?에서\s+")


def _tail(text: str) -> str:
    """'X에서', ''…' 방면으로' 를 벗겨 실제 동작 문구만 남긴다.

    '판교IC(서울·청계·송파)' 방면으로 좌회전 → 좌회전   (IC 가 아니라 좌회전이다)
    서초IC에서 '양재역' 방면으로 오른쪽 고속도로 출구 → 오른쪽 고속도로 출구
    """
    t = _QUOTED_RE.sub("", text or "")
    t = _AT_RE.sub("", t)
    return t.strip()


def classify(guide: dict) -> str:
    """분기점 종류(kind). 코드 우선, 문구 폴백, 모르면 'other'."""
    kind = CODE_KIND.get(guide.get("type"))
    if kind:
        return kind
    t = _tail(guide.get("instructions", ""))
    if "유턴" in t:                       return "uturn"
    if "톨게이트" in t:                    return "toll"
    if "고속도로 출구" in t:               return "hwy_exit"
    if "고가" in t:                        return "overpass"
    if "지하차도" in t and "진입" in t:     return "underpass"
    if "옆길" in t or "합류" in t:         return "sideroad"
    if "좌회전" in t:                      return "left"
    if "우회전" in t:                      return "right"
    if "목적지" in t or t == "도착":       return "goal"
    if "경유지" in t:                      return "via"
    if re.search(r"(오른쪽|왼쪽)\s*(방향|도로)", t): return "branch"
    if "직진" in t:                        return "straight"
    return "other"


def at_interchange(guide: dict) -> bool:
    return bool(re.search(r"(IC|JC|분기점)에서", guide.get("instructions", "")))


# --------------------------------------------------------------------------
# 지표
# --------------------------------------------------------------------------
def _congestion_label(c: int) -> str:
    return {0: "정보없음", 1: "원활", 2: "서행", 3: "혼잡"}.get(c, "정보없음")


def route_metrics(route: dict) -> dict:
    guides = route.get("guides", [])
    sections = route.get("sections", [])
    dist_km = float(route.get("distance_km") or 0)

    kinds = [classify(g) for g in guides]
    counts = Counter(kinds)
    real = [k for k in kinds if k not in ("goal", "via")]

    lane_shift = sum(counts[k] for k in LANE_SHIFT_KINDS)
    grade_sep = counts["overpass"] + counts["underpass"]

    highway_km = sum(
        s["distance"] / 1000 for s in sections
        if HIGHWAY_NAME_RE.search(s.get("name", "")) or s.get("speed", 0) >= HIGHWAY_SPEED_KMH
    )
    slow = [s for s in sections if 0 < s.get("speed", 0) < SLOW_SPEED_KMH]
    slow_km = sum(s["distance"] / 1000 for s in slow)

    gaps_km = [g["distance"] / 1000 for g in guides if g.get("distance")]

    complex_points = [
        {
            "step": i,
            "kind": k,
            "label": KIND_LABEL[k],
            "instruction": g.get("instructions", ""),
            "at_interchange": at_interchange(g),
        }
        for i, (g, k) in enumerate(zip(guides, kinds)) if k in COMPLEX_KINDS
    ]

    score = (
        len(real) * WEIGHTS["base"]
        + counts["uturn"] * WEIGHTS["uturn"]
        + grade_sep * WEIGHTS["grade_sep"]
        + sum(counts[k] for k in ("branch", "hwy_exit", "sideroad")) * WEIGHTS["lane_shift"]
        + counts["toll"] * WEIGHTS["toll"]
        + slow_km * WEIGHTS["slow_per_km"]
        - (highway_km / dist_km if dist_km else 0) * WEIGHTS["highway_bonus"]
    )

    return {
        "maneuver_total": len(real),
        "maneuver_counts": {k: counts[k] for k in KIND_LABEL if counts[k]},
        "lane_shift_count": lane_shift,
        "uturn_count": counts["uturn"],
        "toll_count": counts["toll"],
        "avg_gap_km": round(dist_km / len(real), 2) if real else dist_km,
        "longest_gap_km": round(max(gaps_km), 2) if gaps_km else 0.0,
        "highway_ratio": round(highway_km / dist_km, 3) if dist_km else 0.0,
        "highway_km": round(highway_km, 1),
        "slow_sections": [{"name": s["name"], "km": round(s["distance"] / 1000, 1),
                           "speed": s["speed"]} for s in slow],
        "slow_km": round(slow_km, 1),
        "complex_points": complex_points,
        "comfort_score": round(score, 1),
    }


# --------------------------------------------------------------------------
# 사실 목록 (LLM 인터페이스)
# --------------------------------------------------------------------------
def _fact(rid: str, seq: int, kind: str, text: str, **extra) -> dict:
    f = {"id": f"{rid}.F{seq}", "kind": kind, "text": text}
    f.update(extra)
    return f


def build_facts(route: dict, metrics: dict, rid: str, rank: int, n_routes: int, tied: bool = False) -> list[dict]:
    facts: list[dict] = []
    seq = 0

    def add(kind, text, **extra):
        nonlocal seq
        seq += 1
        facts.append(_fact(rid, seq, kind, text, **extra))

    toll = route.get("toll_fare") or 0
    add("summary",
        f"총 {route['distance_km']}km, 예상 {route['duration_min']}분, "
        f"통행료 {toll:,}원{'(무료)' if not toll else ''}, 연료비 {route.get('fuel_price') or 0:,}원, "
        f"택시 요금 {route.get('taxi_fare') or 0:,}원")

    for s in route.get("sections", []):
        add("road",
            f"{s['name']} {s['distance']/1000:.1f}km — 평균 {s['speed']}km/h, {_congestion_label(s.get('congestion', 0))}",
            road=s["name"])

    mc = metrics["maneuver_counts"]
    parts = ", ".join(f"{KIND_LABEL[k]} {v}" for k, v in mc.items() if k not in ("goal", "via"))
    add("maneuver", f"분기점 {metrics['maneuver_total']}개: {parts}")
    add("maneuver",
        f"차선을 옮길 일이 생기는 합류·분기·출구·고가·지하차도 진입이 {metrics['lane_shift_count']}번 "
        f"(차선 수 자체는 데이터에 없음)")
    add("gap",
        f"분기점 사이 평균 {metrics['avg_gap_km']}km, 가장 긴 무분기 구간 {metrics['longest_gap_km']}km")
    add("gap",
        f"고속도로·고속화도로 성격 구간 {metrics['highway_km']}km — 전체의 {metrics['highway_ratio']*100:.0f}% 이상 "
        f"(교통정보가 있는 구간만 집계한 하한값)")
    if metrics["slow_sections"]:
        add("slow", "저속 구간: " + ", ".join(
            f"{s['name']} {s['km']}km({s['speed']}km/h)" for s in metrics["slow_sections"]))
    else:
        add("slow", "교통정보가 있는 구간 중 20km/h 미만 저속 구간 없음")

    for cp in metrics["complex_points"]:
        add("complex",
            f"{cp['label']} — {cp['instruction']}" + (" (인터체인지)" if cp["at_interchange"] else ""),
            step=cp["step"], maneuver_kind=cp["kind"])

    add("comfort",
        f"편의 점수 {metrics['comfort_score']} — {n_routes}개 경로 중 {'공동 ' if tied else ''}{rank}위 (낮을수록 편함; "
        f"분기 수·유턴·고가/지하·합류분기·톨게이트·저속구간을 더하고 고속화 비율만큼 뺀 값)")
    return facts


# --------------------------------------------------------------------------
# 진입점
# --------------------------------------------------------------------------
def evaluate_routes(routes: list[dict], trip: dict) -> dict:
    """경로 목록 → {trip, routes[metrics, comfort, facts, hazards], comparison}."""
    metrics = [route_metrics(r) for r in routes]

    # 편의 순위. 점수가 같으면 같은 순위(공동 N위) — 동점을 1·2·3위로 갈라 놓으면 없는 차이를 만든다.
    # most_comfortable 하나를 고를 때만 시간 짧은 쪽으로 타이브레이크한다.
    order = sorted(range(len(routes)),
                   key=lambda i: (metrics[i]["comfort_score"], routes[i]["duration_min"]))
    uniq = sorted({m["comfort_score"] for m in metrics})
    rank_of = {i: uniq.index(metrics[i]["comfort_score"]) + 1 for i in range(len(routes))}
    tied = {i: sum(1 for m in metrics if m["comfort_score"] == metrics[i]["comfort_score"]) > 1
            for i in range(len(routes))}

    out_routes = []
    for i, (r, m) in enumerate(zip(routes, metrics)):
        rid = f"R{i+1}"
        out_routes.append({
            "id": r["option"],
            "rid": rid,
            "label": r["label"],
            "summary": {
                "distance_km": r["distance_km"], "duration_min": r["duration_min"],
                "toll_fare": r.get("toll_fare") or 0, "fuel_price": r.get("fuel_price") or 0,
                "taxi_fare": r.get("taxi_fare") or 0,
            },
            "metrics": m,
            "comfort": {"score": m["comfort_score"], "rank": rank_of[i], "tied": tied[i]},
            "facts": build_facts(r, m, rid, rank_of[i], len(routes), tied[i]),
            "hazards": [],   # (b) 트랙이 채운다
        })

    def pick(key):
        return min(range(len(routes)), key=key)

    comparison = {
        "fastest": routes[pick(lambda i: routes[i]["duration_min"])]["option"],
        "shortest": routes[pick(lambda i: routes[i]["distance_km"])]["option"],
        "most_comfortable": routes[order[0]]["option"],
        "cheapest": routes[pick(lambda i: (routes[i].get("toll_fare") or 0) + (routes[i].get("fuel_price") or 0))]["option"],
    }
    return {"trip": trip, "routes": out_routes, "comparison": comparison}


def all_fact_ids(evaluation: dict) -> set[str]:
    return {f["id"] for r in evaluation["routes"] for f in r["facts"]}


def complex_steps(evaluation: dict, route_id: str) -> set[int]:
    for r in evaluation["routes"]:
        if r["id"] == route_id:
            return {cp["step"] for cp in r["metrics"]["complex_points"]}
    return set()


def attach_hazards(evaluation: dict, hazards_by_route: dict[str, list[dict]]) -> dict:
    """route id → hazard 목록을 evaluation 에 붙이고 사실(R1.H1)로도 등록한다.

    hazard 사실은 F 계열과 ID 공간이 분리되므로(H) LLM 이 인용할 때 구분된다.
    """
    from .hazards import to_facts

    for r in evaluation["routes"]:
        hz = hazards_by_route.get(r["id"], [])
        r["hazards"] = hz
        facts = to_facts(hz, r["rid"])
        r["hazard_facts"] = facts
        r["facts"] = r["facts"] + facts
    return evaluation
