"""출발 전 브리핑 — 초행길 운전자가 '언제부터 무엇을 보고 차로를 옮길지'를 미리 익히게 한다.

LLM 없이 결정적으로 만든다. 입력은 serve.py 의 경로 dict(path/guides/sections)와 evaluate 결과(위험 지점).

핵심은 진입·진출·분기 지점마다 '준비 지점 후보'를 멀리서부터 고르는 것이다.
거리만 기계적으로 자르지 않고, 운전자가 눈으로 확인할 수 있는 단서에 맞춘다.
  1) 표지판 — 고속도로·도시고속화도로의 출구·분기 예고 표지는 보통 2km·1km·500m 앞에 선다
     (도로표지규칙의 일반 배치). 실제 위치는 다를 수 있으므로 로드뷰로 그 지점을 보여준다.
  2) 랜드마크 — 바로 앞 안내 지점(교차로·IC·터널 이름). 그곳을 지나는 순간이 눈에 보이는 신호다.
  3) 진입 직전 — 노면 화살표가 보이는 정지선 앞 (몇 초 전 지점).
표지판에서 찾아야 할 방면 이름('서울, 양재')을 함께 알려준다.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .evaluate import COMPLEX_KINDS, HIGHWAY_NAME_RE, HIGHWAY_SPEED_KMH, KIND_LABEL, classify

MLAT = 110540.0


def _mlon(lat: float) -> float:
    return 111320.0 * math.cos(math.radians(lat))


def _dist(a, b) -> float:
    lat = (a[1] + b[1]) / 2
    return math.hypot((b[0] - a[0]) * _mlon(lat), (b[1] - a[1]) * MLAT)


def walk_back(path: list, idx: int, meters: float) -> dict:
    """path[idx] 에서 경로를 거슬러 meters 만큼 뒤로 간 지점."""
    i, acc = min(idx, len(path) - 1), 0.0
    while i > 0:
        a, b = path[i - 1], path[i]
        d = _dist(a, b)
        if acc + d >= meters and d > 0:
            t = (meters - acc) / d
            return {"coord": [b[0] + (a[0] - b[0]) * t, b[1] + (a[1] - b[1]) * t],
                    "index": i - 1, "dist": round(meters)}
        acc += d
        i -= 1
    return {"coord": list(path[0]), "index": 0, "dist": round(acc)}


def bearing_at(path: list, i: int) -> float:
    a, b = path[max(0, i - 2)], path[min(len(path) - 1, i + 2)]
    lat = (a[1] + b[1]) / 2
    return round(math.degrees(math.atan2((b[0] - a[0]) * _mlon(lat), (b[1] - a[1]) * MLAT)), 1)


def time_index(route: dict) -> callable:
    """path 인덱스 → 출발 후 초. guide.duration 은 '앞 안내 지점에서 여기까지'이므로 누적하고,
    안내 지점 사이는 거리 비율로 보간한다 (시내·고속도로 속도 차이가 반영된다)."""
    path, guides = route["path"], route["guides"]
    cum = cumulative(path)
    knots = [(0, 0.0)]
    acc = 0.0
    for g in guides:
        acc += (g.get("duration") or 0) / 1000
        knots.append((min(g["pointIndex"], len(path) - 1), acc))

    def at(idx: int) -> float:
        idx = max(0, min(idx, len(path) - 1))
        for (i0, t0), (i1, t1) in zip(knots, knots[1:]):
            if i0 <= idx <= i1:
                span = cum[i1] - cum[i0]
                return t0 + (t1 - t0) * ((cum[idx] - cum[i0]) / span if span else 0)
        return knots[-1][1]
    return at


def cumulative(path: list) -> list[float]:
    out, acc = [0.0], 0.0
    for a, b in zip(path, path[1:]):
        acc += _dist(a, b)
        out.append(acc)
    return out


# --------------------------------------------------------------------------
# 안내 문구에서 단서 뽑기
# --------------------------------------------------------------------------
_TARGET_RE = re.compile(r"'([^']+)'\s*방면")
_AT_RE = re.compile(r"^(.+?)에서\s")


def sign_target(text: str) -> str | None:
    """표지판에서 찾을 방면 이름. "'서울, 양재' 방면으로" → '서울, 양재'"""
    m = _TARGET_RE.search(text or "")
    return m.group(1) if m else None


def place_name(text: str) -> str | None:
    """안내 지점 이름. "서초IC에서 '양재역' 방면으로…" → '서초IC'"""
    m = _AT_RE.match(text or "")
    if not m:
        return None
    name = m.group(1).strip()
    return name if len(name) <= 20 else None


def lane_side(kind: str, text: str) -> str | None:
    if kind == "uturn" or "왼쪽" in text or "좌회전" in text:
        return "left"
    if "오른쪽" in text or "우회전" in text or kind == "hwy_exit":
        return "right"
    return None


SIDE_KO = {"left": "왼쪽", "right": "오른쪽"}


def josa(word: str, a: str, b: str) -> str:
    """받침 있으면 a(을/이/은), 없으면 b(를/가/는). 따옴표·괄호는 건너뛰고 본다.
    영문·숫자로 끝나면(IC, JC) 읽는 소리 기준: IC·JC 는 '씨'·'씨'로 받침 없음."""
    core = (word or "").rstrip("’')\" ")
    ch = core[-1:] or " "
    if "가" <= ch <= "힣":
        return word + (a if (ord(ch) - 0xAC00) % 28 else b)
    if ch.upper() in "LMNR0136":                     # 엘·엠·엔·알·영·일·삼·육 → 받침 있음
        return word + a
    return word + b


def _section_at(sections: list, idx: int) -> dict | None:
    for s in sections:
        if s["pointIndex"] <= idx <= s["pointIndex"] + s["pointCount"]:
            return s
    return None


def _is_fast_road(sections: list, idx: int) -> bool:
    s = _section_at(sections, idx)
    return bool(s and (HIGHWAY_NAME_RE.search(s.get("name", "")) or s.get("speed", 0) >= HIGHWAY_SPEED_KMH))


# --------------------------------------------------------------------------
# 준비 지점 후보
# --------------------------------------------------------------------------
# 빠른 도로의 진출·분기: 예고 표지 배치(2km·1km·500m)에 맞춘다
FAST_MARKS = [(2000, "sign"), (1000, "sign"), (500, "sign")]
# 일반 도로: 차로 변경에 필요한 여유. 표지판(방향 예고)은 교차로 앞 150~300m 에 많다
CITY_MARKS = [(300, "sign"), (150, "prep")]
APPROACH_SEC = 8


def candidates(route: dict, step: int, kind: str) -> list[dict]:
    path, guides, sections = route["path"], route["guides"], route.get("sections", [])
    g = guides[step]
    idx = min(g["pointIndex"], len(path) - 1)
    text = g.get("instructions", "")
    side = SIDE_KO.get(lane_side(kind, text) or "", "")
    target = sign_target(text)
    fast = _is_fast_road(sections, max(0, idx - 3))
    room = float(g.get("distance") or 0)               # 앞 안내 지점에서 여기까지 같은 길로 오는 거리
    mps = (g["distance"] / (g["duration"] / 1000)) if g.get("duration") else (22.0 if fast else 9.0)

    marks = FAST_MARKS if fast and kind in ("hwy_exit", "branch", "sideroad") else CITY_MARKS
    if kind == "uturn":
        marks = [(300, "prep")]
    if kind == "toll":
        marks = [(500, "sign")]
    out: list[dict] = []
    prev_name = place_name(guides[step - 1].get("instructions", "")) if step > 0 else None
    prev_ref = f"‘{prev_name}’" if prev_name else "앞 안내 지점"
    far = max(m for m, _ in marks)

    if step > 0 and room <= 150:
        # 연속 동작: 앞 지점과 너무 가까워 그 사이에서는 준비할 틈이 없다 → 앞 지점 전부터 준비
        out.append({"back": room + 150, "role": "combo",
                    "title": f"{prev_ref} 전부터 · 연속 동작",
                    "say": f"{josa(prev_ref, '을', '를')} 지나자마자 {room:.0f}m 만에 이 동작이 이어져. "
                           + (f"앞 지점을 지나기 전부터 {side} 차로 쪽을 염두에 둬." if side
                              else "앞 지점에서 빠져나오면서 바로 다음 표지를 찾아.")})
    elif step > 0 and room - 40 < far:
        # 앞 안내 지점이 준비 범위 안이면, 그곳을 '지난 직후'가 눈으로 확인되는 가장 이른 신호다
        out.append({"back": room - 40, "role": "landmark",
                    "title": f"{prev_ref} 지난 직후",
                    "say": f"{josa(prev_ref, '을', '를')} 지나면 바로 다음이 이 지점이야. "
                           + (f"{side} 차로로 옮길 준비를 시작해." if side else "속도를 줄이고 표지판을 찾아.")})

    for m, role in marks:
        if m >= room - 30:                              # 앞 안내 지점보다 멀면 다른 길 위다
            continue
        if kind == "toll":
            say, title = "톨게이트 차로 안내 표지가 보이기 시작해. 하이패스 차로인지 일반 차로인지 미리 골라 둬.", "500m 앞 · 차로 안내"
        elif kind == "uturn":
            say, title = "유턴은 가장 왼쪽 차로에서 해. 지금부터 1차로로 옮겨.", "300m 앞 · 1차로로"
        elif role == "sign":
            say = (f"{'출구·분기 예고 표지' if fast else '방향 예고 표지'}가 보일 즈음이야."
                   + (f" 표지판에서 ‘{target}’ 방면을 찾아." if target else "")
                   + (f" 지금부터 {side} 차로로 한 칸씩 옮겨." if side and m <= 1000 else ""))
            title = f"{m // 1000}km 앞 · 예고 표지" if m >= 1000 else f"{m}m 앞 · 예고 표지"
        else:
            say = (f"이제 {side} 끝 차로에 있어야 해." if side else "진입할 차로를 확정해.")
            title = f"{m}m 앞 · 차로 확정"
        out.append({"back": m, "role": role, "title": title, "say": say})

    # 진입 직전: 노면 화살표가 보이는 지점
    # 앞 지점 '지난 직후' 후보와 겹치지 않도록 진입 직전은 그보다 가까이 둔다
    near = max(25.0, min(250.0, mps * APPROACH_SEC, room - 70 if room > 110 else room * 0.5 if room > 50 else 25.0))
    last_say = {
        "toll": "요금소 위 차로 표시(하이패스·일반)를 보고 그 차로를 유지해.",
        "uturn": "유턴 표지와 신호(좌회전 시 유턴 등)를 확인하고, 맞은편 차를 보고 돌아.",
    }.get(kind, "정지선 앞 노면 화살표로 내 차로가 맞는지 마지막으로 확인해.")
    out.append({"back": near, "role": "approach", "title": "진입 직전 · 노면 화살표" if kind not in ("toll", "uturn") else "진입 직전",
                "say": last_say})

    # 멀리서 가까이 순서, 너무 가까운 후보(80m 이내)는 합친다
    out.sort(key=lambda c: -c["back"])
    merged: list[dict] = []
    for c in out:
        if merged and merged[-1]["back"] - c["back"] < 80 and c["role"] not in ("approach", "combo"):
            continue
        if merged and c["role"] == "approach" and merged[-1]["back"] - c["back"] < 25:
            merged.pop()
        merged.append(c)

    res = []
    for c in merged:
        v = walk_back(path, idx, c["back"])
        res.append({
            "role": c["role"], "title": c["title"], "say": c["say"],
            "dist_m": v["dist"], "seconds": round(v["dist"] / mps) if mps > 0.5 else None,
            "coord": [round(v["coord"][0], 7), round(v["coord"][1], 7)],
            "path_index": v["index"], "bearing": bearing_at(path, v["index"]),
        })
    return res


# --------------------------------------------------------------------------
# 브리핑
# --------------------------------------------------------------------------
HAZARD_ITEM_TYPES = ("frequentzoneFreezing", "frequentzoneLg", "pedstrians", "frequentzoneChild",
                     "frequentzoneOldman", "frequentzoneBicycle", "accident_schoolzone")


def road_legs(route: dict, lo: int = 0, hi: int | None = None) -> list[dict]:
    """경로(또는 path 인덱스 lo~hi 구간)를 큰 도로 단위로. section 이 덮지 않는 구간은 '일반도로'."""
    path = route["path"]
    cum = cumulative(path)
    hi = len(path) - 1 if hi is None else min(hi, len(path) - 1)
    legs: list[dict] = []

    def add(name, a, b, congestion=0, speed=None):
        km = (cum[b] - cum[a]) / 1000
        if km < 0.05:
            return
        if legs and legs[-1]["name"] == name:
            legs[-1]["km"] = round(legs[-1]["km"] + km, 1)
            return
        legs.append({"name": name, "km": round(km, 1), "congestion": congestion, "speed": speed,
                     "from_km": round(cum[a] / 1000, 1)})

    cur = lo
    for sec in sorted(route.get("sections", []), key=lambda x: x["pointIndex"]):
        a = max(lo, sec["pointIndex"])
        b = min(hi, sec["pointIndex"] + sec["pointCount"])
        if b <= a:
            continue
        if cum[a] - cum[cur] > 300:
            add("일반도로", cur, a)
        add(sec["name"], a, b, sec.get("congestion", 0), sec.get("speed"))
        cur = max(cur, b)
    if cum[hi] - cum[cur] > 300:
        add("일반도로", cur, hi)
    return legs


def segments(route: dict, items: list[dict], minor: list[dict], t_at) -> list[dict]:
    """체크 지점 사이의 '그냥 따라가는' 구간 설명. 출발 → 1번, 1번 → 2번, …, 마지막 → 도착.
    체크리스트만 보면 그 사이를 어떻게 가는지(언제 그 지점이 나오는지)를 모른다."""
    path, guides = route["path"], route["guides"]
    cum = cumulative(path)
    end = len(path) - 1
    item_steps = {it["step"] for it in items if it["type"] == "maneuver"}
    bounds = [0] + [it["path_index"] for it in items] + [end]
    out = []
    for k in range(len(bounds) - 1):
        a, b = bounds[k], bounds[k + 1]
        km = (cum[b] - cum[a]) / 1000
        steps = [{"text": g.get("instructions", ""), "km": round(cum[min(g["pointIndex"], end)] / 1000, 1),
                  "kind": classify(g)}
                 for i, g in enumerate(guides)
                 if a < g["pointIndex"] < b and i not in item_steps and classify(g) not in ("goal",)]
        nxt = items[k] if k < len(items) else None
        prep = None
        if nxt and nxt["type"] == "maneuver" and nxt["candidates"]:
            prep = nxt["candidates"][0]["dist_m"]
        out.append({
            "from": k - 1, "to": k if k < len(items) else None,      # 체크 번호(0부터). -1 = 출발, None = 도착
            "from_km": round(cum[a] / 1000, 1), "to_km": round(cum[b] / 1000, 1),
            "km": round(km, 1), "min": max(1, round((t_at(b) - t_at(a)) / 60)) if km > 0.05 else 0,
            "roads": road_legs(route, a, b),
            "steps": steps,
            "cameras": sum(1 for h in minor if h["type"] == "speed_camera" and a <= h["path_index"] < b),
            "zones": sum(1 for h in minor if h["type"] in ("school_zone", "senior_zone") and a <= h["path_index"] < b),
            "prep_m": prep,
        })
    return out


def build_briefing(route: dict, eval_route: dict | None, narr_route: dict | None,
                   headline: dict | None = None) -> dict[str, Any]:
    path, guides = route["path"], route["guides"]
    cum = cumulative(path)
    t_at = time_index(route)

    def at(idx: int) -> dict:
        idx = max(0, min(idx, len(path) - 1))
        return {"km": round(cum[idx] / 1000, 1), "min": round(t_at(idx) / 60)}

    notes: dict[int, list[str]] = {}
    picks: dict[int, str] = {}
    if narr_route:
        for c in narr_route.get("cautions", []):
            if c.get("step") is not None and c.get("text"):
                notes.setdefault(c["step"], []).append(c["text"])
        for p in narr_route.get("roadview_picks", []):
            picks[p["step"]] = p.get("reason", "")

    items: list[dict] = []
    for i, g in enumerate(guides):
        kind = classify(g)
        if kind not in COMPLEX_KINDS and kind != "toll" and i not in picks:
            continue
        text = g.get("instructions", "")
        items.append({
            "type": "maneuver", "step": i, "kind": kind, "label": KIND_LABEL.get(kind, "기타"),
            "instruction": text, "target": sign_target(text), "place": place_name(text),
            "side": lane_side(kind, text),
            "coord": path[min(g["pointIndex"], len(path) - 1)],
            "path_index": g["pointIndex"], **at(g["pointIndex"]),
            "candidates": candidates(route, i, kind),
            "ai_notes": notes.get(i, []), "ai_pick": picks.get(i),
        })

    hz = (eval_route or {}).get("hazards", [])
    for h in hz:
        if h["type"] not in HAZARD_ITEM_TYPES:
            continue
        items.append({
            "type": "hazard", "kind": h["type"], "text": h.get("text", ""), "detail": h.get("detail", ""),
            "coord": h["coord"], "path_index": h.get("path_index", 0), "distance_m": h.get("distance_m"),
            "bearing": bearing_at(path, h.get("path_index", 0)),
            "view": walk_back(path, h.get("path_index", 0), 60)["coord"],
            **at(h.get("path_index", 0)),
        })
    items.sort(key=lambda it: it["path_index"])

    minor = [h for h in hz if h["type"] not in HAZARD_ITEM_TYPES]
    segs = segments(route, items, minor, t_at)
    summary = {
        "maneuvers": sum(1 for it in items if it["type"] == "maneuver"),
        "accident_spots": sum(1 for it in items if it["type"] == "hazard"),
        "cameras": sum(1 for h in minor if h["type"] == "speed_camera"),
        "zones": sum(1 for h in minor if h["type"] in ("school_zone", "senior_zone")),
    }
    return {
        "route": {k: route[k] for k in ("option", "label", "distance_km", "duration_min", "toll_fare", "fuel_price")},
        "path": path, "legs": road_legs(route), "summary": summary, "items": items, "segments": segs,
        "minor_hazards": [{"type": h["type"], "text": h.get("text", ""), "coord": h["coord"],
                           "path_index": h.get("path_index", 0), **at(h.get("path_index", 0))} for h in minor],
        "ai": {
            "headline": headline.get("text") if headline else None,
            "verdict": (narr_route or {}).get("verdict", {}).get("text") if narr_route else None,
            "overview": [s["text"] for s in (narr_route or {}).get("overview", [])] if narr_route else [],
        },
    }
