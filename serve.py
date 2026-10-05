#!/usr/bin/env python3
"""로컬 개발 서버 — 정적 파일 + NCP API 프록시.

브라우저에서 검색·길찾기를 직접 부를 수 없어서(CORS, 그리고 REST 키를
브라우저에 노출할 수 없어서) 이 서버가 중계한다. REST 키는 서버에만 남는다.
Dynamic Map 의 ncpKeyId 만 페이지에 주입된다 — 원래 브라우저용 키다.

    python3 serve.py            # http://localhost:3000

⚠️ 호출 1건 = 요금 1건이다. 검색은 사용자가 엔터/버튼을 눌렀을 때만 나가고,
   같은 질의는 서버 캐시에서 준다.
"""
from __future__ import annotations

import json
import logging
import sys
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ncp_maps import MapsClient, NcpApiError, load_env
from ncp_maps.api import (
    DRIVING_OPTIONS,
    LOCAL_SEARCH_MAX_DISPLAY,
    OPTION_LABELS,
    address_to_coord,
    directions,
    geocode,
    local_search,
    parse_places,
    route_summaries,
    static_map,
)
from ncp_maps.client import CallCounter, DEFAULT_HOST, HUB_HOST, OUT_DIR, PROJECT_ROOT
from ncp_maps.evaluate import attach_hazards, evaluate_routes
from ncp_maps.narrate import Cancelled, cli_available, narrate, validate_narration
from ncp_maps import hazards as hz
from ncp_maps.briefing import build_briefing
from ncp_maps import panoshot

log = logging.getLogger("ncp.serve")

PORT = 3000
WEB_DIR = PROJECT_ROOT / "web"
RAW_DIR = OUT_DIR / "raw_server"     # 서버 경유 호출의 원본 응답


class Backend:
    """API 클라이언트 묶음 + 질의 캐시."""

    def __init__(self) -> None:
        env = load_env()
        self.counter = CallCounter()
        self.maps_key_id = env.get("NCP_MAPS_CLIENT_ID", "")
        if not self.maps_key_id or not env.get("NCP_MAPS_CLIENT_SECRET"):
            raise SystemExit("NCP_MAPS_CLIENT_ID / NCP_MAPS_CLIENT_SECRET 가 없습니다. .env 확인.")

        self.maps = MapsClient(self.maps_key_id, env["NCP_MAPS_CLIENT_SECRET"],
                               host=env.get("NCP_MAPS_API_HOST", DEFAULT_HOST),
                               raw_dir=RAW_DIR, counter=self.counter)
        self.hub = None
        if env.get("NAVER_HUB_CLIENT_ID") and env.get("NAVER_HUB_CLIENT_SECRET"):
            self.hub = MapsClient(env["NAVER_HUB_CLIENT_ID"], env["NAVER_HUB_CLIENT_SECRET"],
                                  host=env.get("NAVER_HUB_API_HOST", HUB_HOST),
                                  raw_dir=RAW_DIR, counter=self.counter)
        else:
            log.warning("NAVER_HUB_* 미설정 — 장소 검색이 비활성화됩니다")

        self._search_cache: dict[str, list] = {}
        self._route_cache: dict[str, dict] = {}

        # 경로 평가·서술은 로컬 `claude` CLI(-p)로 호출한다. API 키 불필요.
        ok, why = cli_available()
        if not ok:
            log.warning("%s — 경로 비교의 서술 기능이 비활성화됩니다", why)
        self._eval_cache: dict[str, dict] = {}
        self._narr_cache: dict[str, dict] = {}
        self._static_cache: dict[str, bytes] = {}

        # (b) 위험 데이터 — 표준데이터 파일은 기동 시 격자 색인으로 한 번만 적재한다.
        self.data_key = env.get("DATA_GO_KR_KEY")      # data.go.kr (사고다발 5종)
        self.koroad_key = env.get("KOROAD_AUTH_KEY")   # KOROAD 포털 (보행자)
        self.hazard_grid = hz.load_file_sources()
        if not self.data_key:
            log.warning("DATA_GO_KR_KEY 미설정 — 사고다발 조회를 건너뜁니다")
        self._region_cache: dict[str, list[str]] = {}

    # -- 검색 ------------------------------------------------------------
    # 지역 검색은 한 번에 최대 5건이고 페이징이 안 된다(start 무시).
    # 그래서 서로 다른 결과를 주는 소스를 합쳐 후보를 늘린다:
    #   ① 지역 검색 sort=random  (정확도순, 가장 관련도 높음)
    #   ② Geocoding             (주소로 입력한 경우. 최대 5건만 취함)
    #   ③ 지역 검색 sort=comment (①과 겹치지 않는 다른 5건. 부족할 때만)
    def search(self, query: str, want: int = 10) -> list[dict]:
        if query in self._search_cache:
            log.info("검색 캐시 적중: %s", query)
            return self._search_cache[query]

        found: list[dict] = []
        seen: set = set()

        def add(items):
            for it in items:
                key = (it["title"], round(it["coord"][0], 5), round(it["coord"][1], 5))
                if key in seen:
                    continue
                seen.add(key)
                found.append(it)

        if self.hub is not None:
            add(parse_places(local_search(self.hub, query,
                                          name=f"search_{query[:10]}",
                                          display=LOCAL_SEARCH_MAX_DISPLAY,
                                          sort="random")))

        # 주소로 입력한 경우를 위해 Geocoding 도 함께 본다 (장소명이면 0건이라 손해가 없다)
        try:
            payload = geocode(self.maps, query, name=f"gc_{query[:10]}", count=5)
            add([{
                "title": a.get("roadAddress") or a.get("jibunAddress", ""),
                "category": "주소",
                "kind": "address",
                "road_address": a.get("roadAddress", ""),
                "jibun_address": a.get("jibunAddress", ""),
                "coord": list(address_to_coord(a)),
            } for a in (payload.get("addresses") or [])])
        except NcpApiError as exc:
            log.warning("지오코딩 보조 검색 실패(무시): %s", exc)

        # 아직 부족하면 다른 정렬로 한 번 더 (겹치지 않는 결과가 나온다)
        if self.hub is not None and len(found) < want:
            try:
                add(parse_places(local_search(self.hub, query,
                                              name=f"search2_{query[:10]}",
                                              display=LOCAL_SEARCH_MAX_DISPLAY,
                                              sort="comment")))
            except NcpApiError as exc:
                log.warning("보조 정렬 검색 실패(무시): %s", exc)

        for item in found:
            item.setdefault("kind", "place")
        self._search_cache[query] = found
        return found

    # -- 경로 ------------------------------------------------------------
    def route(self, start: str, goal: str, waypoints: str = "") -> dict:
        key = f"{start}|{goal}|{waypoints}"
        if key in self._route_cache:
            log.info("경로 캐시 적중")
            return self._route_cache[key]

        def coord(text: str):
            lon, lat = text.split(",")
            return (float(lon), float(lat))

        way = [coord(w) for w in waypoints.split("|") if w.strip()]
        payload = directions(self.maps, coord(start), coord(goal),
                             name="route15" if way else "route5",
                             version=15 if way else 5,
                             waypoints=way, options=DRIVING_OPTIONS)
        raw_routes = payload.get("route") or {}
        summaries = route_summaries(payload)

        routes = []
        for option in DRIVING_OPTIONS:          # 표시 순서를 고정한다
            if option not in summaries:
                continue
            s = summaries[option]
            raw = raw_routes[option][0]
            routes.append({
                "option": option,
                "label": OPTION_LABELS.get(option, option),
                "distance_km": round(s["distance_km"], 1),
                "duration_min": round(s["duration_min"]),
                "taxi_fare": s["taxi_fare"],
                "toll_fare": s["toll_fare"],
                "fuel_price": s["fuel_price"],
                "bbox": s["bbox"],
                "path": s["path"],
                "sections": raw.get("section", []),
                "guides": raw.get("guide", []),
                "options": [option],
            })
        routes = merge_identical(routes)
        result = {"routes": routes, "via": bool(way),
                  "api": "Directions 15" if way else "Directions 5"}
        self._route_cache[key] = result
        return result


    # -- 평가·비교 ------------------------------------------------------
    # 비교 화면은 두 단계로 받는다: ① evaluate(지표·비교표·위험 지점, 수 초) → 바로 그린다
    # ② narrate(LLM 서술, 수십 초~분) → SSE 로 문장이 완성될 때마다 흘려 보낸다.
    def evaluate(self, start: str, goal: str, waypoints: str, trip: dict) -> dict:
        key = f"{start}|{goal}|{waypoints}"
        if key in self._eval_cache:
            return self._eval_cache[key]

        routes = self.route(start, goal, waypoints)["routes"]   # 경로 캐시 재사용
        evaluation = evaluate_routes(routes, trip)

        # 위험 구간: 경로가 지나는 시군구만 조회한다 (전국을 긁지 않는다)
        hazard_calls = 0
        try:
            base_path = routes[0]["path"]
            if key in self._region_cache:
                codes = self._region_cache[key]
            else:
                codes = hz.region_codes(self.maps, base_path)
                self._region_cache[key] = codes
            spots, hazard_calls = hz.fetch_all(self.data_key, self.koroad_key, codes)
            log.info("위험 데이터: 시군구 %d개, 조회 %d회 → %d건",
                     len(codes), hazard_calls, len(spots))
            by_route = {r["option"]: hz.collect(r["path"], r["guides"], self.hazard_grid, spots,
                                                  sections=r.get("sections"))
                        for r in routes}
            attach_hazards(evaluation, by_route)
            log.info("경로별 위험 매칭: %s",
                     {k: len(v) for k, v in by_route.items()})
        except Exception as exc:                       # 위험 데이터가 없어도 비교는 동작해야 한다
            log.exception("위험 구간 수집 실패 — 빈 값으로 진행: %s", exc)

        result = {"key": key, "evaluation": evaluation, "hazard_calls": hazard_calls,
                  "narration_cached": key in self._narr_cache}
        self._eval_cache[key] = result
        return result

    def narration(self, start: str, goal: str, waypoints: str, trip: dict,
                  on_event=None) -> tuple[dict | None, str | None, dict]:
        """(검증된 서술, 오류, meta). on_event 로 부분 결과(검증 포함)를 흘려 보낸다."""
        key = f"{start}|{goal}|{waypoints}"
        if key in self._narr_cache:
            log.info("서술 캐시 적중")
            return self._narr_cache[key], None, {"cached": True}

        evaluation = self.evaluate(start, goal, waypoints, trip)["evaluation"]

        def relay(kind, value):
            if on_event is None:
                return
            if kind == "partial":
                value = validate_narration(value, evaluation)
            on_event(kind, value)

        meta: dict = {}
        narration, err = narrate(evaluation, meta_out=meta, on_event=relay)
        if narration is None:
            log.warning("서술 없음: %s", err)
            return None, err, meta
        narration = validate_narration(narration, evaluation)
        log.info("서술 검증: 문장 %d, 근거 미확인 %d",
                 narration["stats"]["sentences"], narration["stats"]["unverified"])
        # 실패한 결과는 캐시하지 않는다 (다음 요청에서 바로 재시도되도록)
        self._narr_cache[key] = narration
        if key in self._eval_cache:
            self._eval_cache[key]["narration_cached"] = True
        return narration, None, meta

    def briefing(self, start: str, goal: str, waypoints: str, trip: dict, option: str) -> dict:
        """출발 전 브리핑. LLM 을 새로 부르지 않는다 — 이미 만든 서술이 캐시에 있으면 곁들인다."""
        routes = self.route(start, goal, waypoints)["routes"]
        route = next((r for r in routes if option in r["options"]), routes[0])
        ev = self.evaluate(start, goal, waypoints, trip)["evaluation"]
        er = next((r for r in ev["routes"] if r["id"] == route["option"]), None)
        narr = self._narr_cache.get(f"{start}|{goal}|{waypoints}")
        nr = next((r for r in narr["routes"] if r["id"] == route["option"]), None) if narr else None
        out = build_briefing(route, er, nr, narr["comparison"].get("headline") if narr else None)
        out["trip"] = trip
        out["alternatives"] = len(routes)
        return out

    def static_image(self, center: str, level: int, w: int, h: int) -> bytes:
        """브리핑 내려받기용 지도 이미지. 같은 요청은 캐시한다 (호출 1건 = 요금 1건)."""
        key = f"{center}|{level}|{w}|{h}"
        if key not in self._static_cache:
            lon, lat = (float(v) for v in center.split(","))
            self._static_cache[key] = static_map(self.maps, (lon, lat), level, name="brief_static",
                                                 width=w, height=h, scale=2)
        return self._static_cache[key]

    def compare(self, start: str, goal: str, waypoints: str, trip: dict) -> dict:
        """(호환용) 평가 + 서술을 한 번에. 화면은 evaluate + narrate(SSE)를 쓴다."""
        ev = self.evaluate(start, goal, waypoints, trip)
        narration, err, meta = self.narration(start, goal, waypoints, trip)
        return {"evaluation": ev["evaluation"], "narration": narration, "narration_error": err,
                "narration_meta": meta or None, "hazard_calls": ev["hazard_calls"]}


def merge_identical(routes: list[dict]) -> list[dict]:
    """옵션이 달라도 경로가 완전히 같으면(실측: 빠른길 = 최적이 자주 같다) 한 장으로 합친다.
    라벨은 '실시간 빠른길 · 실시간 최적'처럼 잇고, 대표 option(id)은 먼저 나온 것을 쓴다."""
    out: list[dict] = []
    for r in routes:
        same = next((o for o in out
                     if o["path"] == r["path"] and len(o["guides"]) == len(r["guides"])), None)
        if same is None:
            out.append(r)
        else:
            same["options"].append(r["option"])
            same["label"] = f"{same['label']} · {r['label']}"
            log.info("동일 경로 병합: %s ← %s", same["option"], r["option"])
    return out


class Handler(SimpleHTTPRequestHandler):
    backend: Backend

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB_DIR), **kw)

    def log_message(self, fmt, *args):          # 기본 로그가 시끄러워서 줄인다
        # send_error 경로에서는 args 가 (HTTPStatus, str) 로 들어온다 — 문자열로 정규화
        text = fmt % args if args else fmt
        if "/api/" in text or "code 4" in text or "code 5" in text:
            log.info("%s", text)

    def do_GET(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            if parsed.path in ("/", "/index.html", "/app.html"):
                return self._page()
            if parsed.path in ("/briefing", "/briefing.html"):
                return self._page("briefing.html")
            if parsed.path == "/pano-shot.html":
                return self._page("pano-shot.html")                      # 편집 즉시 반영 (개발용)
            return super().do_GET()                      # web/ 아래 모듈·스타일

        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        try:
            if parsed.path == "/api/search":
                query = (params.get("q") or "").strip()
                if not query:
                    return self._json({"error": "검색어가 비어 있습니다"}, 400)
                places = self.backend.search(query)
                return self._json({"query": query, "places": places})

            if parsed.path == "/api/route":
                if not params.get("start") or not params.get("goal"):
                    return self._json({"error": "start/goal 이 필요합니다"}, 400)
                return self._json(self.backend.route(
                    params["start"], params["goal"], params.get("waypoints", "")))

            if parsed.path == "/api/roadview-shot":
                img = panoshot.shoot(f"http://localhost:{PORT}", OUT_DIR / "pano_cache",
                                     float(params["lon"]), float(params["lat"]), float(params.get("pan", 0)),
                                     w=max(160, min(1280, int(params.get("w", 640)))),
                                     h=max(90, min(720, int(params.get("h", 360)))))
                if img is None:
                    return self._json({"error": "이 지점은 로드뷰가 없거나 찍지 못했어요"}, 404)
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(img)))
                self.end_headers()
                self.wfile.write(img)
                return

            if parsed.path == "/api/staticmap":
                w = max(1, min(1024, int(params.get("w", 640))))
                h = max(1, min(1024, int(params.get("h", 400))))
                level = max(0, min(20, int(params.get("level", 12))))
                img = self.backend.static_image(params["center"], level, w, h)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(img)))
                self.end_headers()
                self.wfile.write(img)
                return

            if parsed.path in ("/api/evaluate", "/api/narrate", "/api/briefing"):
                if not params.get("start") or not params.get("goal"):
                    return self._json({"error": "start/goal 이 필요합니다"}, 400)
                trip = {"origin": params.get("o", "출발지"), "goal": params.get("g", "도착지"),
                        "via": params.get("v") or None}
                args = (params["start"], params["goal"], params.get("waypoints", ""), trip)
                if parsed.path == "/api/briefing":
                    return self._json(self.backend.briefing(*args, params.get("route", "")))
                if parsed.path == "/api/evaluate":
                    return self._json(self.backend.evaluate(*args))
                return self._sse_narrate(args)

            if parsed.path == "/api/compare":
                if not params.get("start") or not params.get("goal"):
                    return self._json({"error": "start/goal 이 필요합니다"}, 400)
                trip = {"origin": params.get("o", "출발지"), "goal": params.get("g", "도착지"),
                        "via": params.get("v") or None}
                return self._json(self.backend.compare(
                    params["start"], params["goal"], params.get("waypoints", ""), trip))

            return self._json({"error": "알 수 없는 엔드포인트"}, 404)

        except NcpApiError as exc:
            log.error("%s", exc)
            return self._json({"error": str(exc), "status": exc.status,
                               "hint": exc.hint()}, 502)
        except Exception as exc:                      # noqa: BLE001
            log.exception("처리 실패")
            return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def _page(self, name: str = "app.html"):
        html = (WEB_DIR / name).read_text(encoding="utf-8")
        body = html.replace("__NCP_KEY_ID__", self.backend.maps_key_id).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # 개발 중 모듈 수정이 바로 보이도록 정적 파일도 캐시하지 않는다
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _sse_narrate(self, args):
        """서술을 Server-Sent Events 로 흘려 보낸다.
        event: stage {"stage": thinking|writing} · partial {narration} · retry {reason}
               done {narration, meta} · fail {error}
        클라이언트가 연결을 끊으면(EventSource.close) 쓰기가 실패하고, CLI 프로세스를 끊는다."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def send(event: str, data) -> None:
            try:
                chunk = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError) as exc:
                log.info("서술 스트림: 클라이언트가 떠남 — 생성 중단")
                raise Cancelled() from exc

        def on_event(kind, value):
            if kind == "stage":
                send("stage", {"stage": value})
            elif kind == "partial":
                send("partial", {"narration": value})
            elif kind == "retry":
                send("retry", {"reason": value})

        try:
            send("stage", {"stage": "start"})
            narration, err, meta = self.backend.narration(*args, on_event=on_event)
            if narration is None:
                send("fail", {"error": err})
            else:
                send("done", {"narration": narration, "meta": meta})
        except Cancelled:
            pass
        except Exception as exc:                      # noqa: BLE001
            log.exception("서술 스트림 실패")
            try:
                send("fail", {"error": f"{type(exc).__name__}: {exc}"})
            except Cancelled:
                pass

    def _json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    backend = Backend()
    Handler.backend = backend

    log.info("http://localhost:%d 에서 서비스 중 (Ctrl+C 로 종료)", PORT)
    log.info("Dynamic Map 인증은 콘솔에 등록된 http://localhost:%d 에서만 통과합니다", PORT)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("종료합니다. 총 API 호출 %d회", backend.counter.value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
