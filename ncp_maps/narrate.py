"""경로 평가 서술 — Claude Code CLI(`claude -p`)가 사실 목록만 보고 아버지 톤으로 설명한다.

설계: docs/superpowers/specs/2026-09-11-route-compare-design.md §(c)
호출 방식은 kr-by-claude 의 llm/claude_cli.py 를 따른다: API 키 대신 로컬 `claude` CLI,
정적 프롬프트는 --append-system-prompt(캐시 프리픽스), 호출별 입력은 stdin, 결과는
--output-format stream-json 의 result 봉투에서 추출(생성 중 부분 JSON 을 스트리밍), 1/3/9초 재시도.

원칙
- 입력은 evaluate.py 가 만든 사실(ID 붙은 문장)뿐이다. 그 밖의 수치·지역 단정은 금지.
- 일반 운전 지식(고속도로 진출입·유턴·지하차도 요령 등)은 허용하되 basis 를 "GK" 로 표시한다.
- 출력은 --json-schema 로 문장 단위 JSON 을 강제한다. 문장마다 basis(사실 ID 목록)가 있다.
- 서버가 basis 를 검증한다. 없는 ID 를 댄 문장은 지우지 않고 unverified 로 표시한다.
- 야간·우천 항목은 LLM 출력에 없다. hazards 가 비어 있으면 서버가 고정 문구를 넣는다.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Callable

from .evaluate import KIND_LABEL, all_fact_ids, complex_steps

log = logging.getLogger("ncp.narrate")

# 모델은 별칭으로 핀한다 — 사용자의 /model 설정이 서술 모델을 조용히 바꾸지 않도록.
MODEL_ALIAS = os.environ.get("ROUTE_CLAUDE_MODEL", "opus")
TIMEOUT_SECONDS = 240
RETRY_DELAYS = [1, 3, 9]
GK = "GK"  # 일반 운전 지식 표시자

# --------------------------------------------------------------------------
# 출력 스키마 (--json-schema 로 전달)
# --------------------------------------------------------------------------
_SENT = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "basis": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "basis"],
    "additionalProperties": False,
}
_SENT_STEP = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "basis": {"type": "array", "items": {"type": "string"}},
        "step": {"type": ["integer", "null"]},
    },
    "required": ["text", "basis", "step"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA = {
    "type": "object",
    # 속성 순서 = 생성 순서. 스트리밍으로 보여줄 때 결론(comparison)이 먼저 도착하게 앞에 둔다.
    "properties": {
        "comparison": {
            "type": "object",
            "properties": {
                "headline": _SENT,
                "summary": {"type": "array", "items": _SENT},
            },
            "required": ["headline", "summary"],
            "additionalProperties": False,
        },
        "routes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "overview": {"type": "array", "items": _SENT},
                    "verdict": _SENT,
                    "comfort_note": _SENT,
                    "cautions": {"type": "array", "items": _SENT_STEP},
                    "roadview_picks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"step": {"type": "integer"}, "reason": {"type": "string"}},
                            "required": ["step", "reason"],
                            "additionalProperties": False,
                        },
                    },
                    "hazard_notes": {"type": "array", "items": _SENT_STEP},
                },
                "required": ["id", "overview", "verdict", "comfort_note", "cautions",
                             "roadview_picks", "hazard_notes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["comparison", "routes"],
    "additionalProperties": False,
}

# --------------------------------------------------------------------------
# 시스템 프롬프트 (고정 — 캐시 프리픽스. 요청마다 바뀌는 내용을 넣지 말 것)
# --------------------------------------------------------------------------
_GLOSSARY = "\n".join(f"- {k}: {v}" for k, v in KIND_LABEL.items() if k != "other")

SYSTEM_PROMPT = f"""당신은 운전 경력 30년의 아버지입니다. 아들이 처음 가보는 길을 자동차로 운전해 갈 예정이고,
당신은 아들이 안전하고 편하게 가도록, 그리고 이 기회에 운전 실력이 한 단계 늘도록 길을 설명해 줍니다.
다정하지만 정확합니다. 과장하거나 겁주지 않습니다. 아들을 낮춰 보지 않습니다.

## 입력
사용자 메시지에 JSON 이 옵니다. 경로가 여러 개 있고, 각 경로에 `facts` 배열이 있습니다.
각 fact 는 `id`(예: R1.F3), `kind`, `text` 를 가집니다. `kind` 가 complex 인 fact 는 `step` 도 가집니다.
`comparison` 에는 엔진이 계산한 최단시간·최단거리·최고편의·최저비용 경로 id 가 있습니다.

## 절대 규칙
1. **입력 facts 에 없는 수치를 만들지 마세요.** 거리·시간·요금·속도·개수는 facts 의 값만 씁니다.
2. **특정 도로·지역·시간대에 대한 단정을 하지 마세요.** "강남대로는 늘 막힌다", "이 구간은 밤에 어둡다" 같은
   문장은 데이터에 없으면 쓸 수 없습니다. 지금 입력에는 그런 데이터가 없습니다.
3. **"차선 변경이 잦다"고 쓰지 마세요.** 차선 수는 데이터에 없습니다. 대신 facts 의 표현대로
   "합류·분기가 N번 있어 차선을 옮길 일이 생긴다"처럼 씁니다.
4. **편의 순위는 입력의 comfort fact 를 그대로 따릅니다.** 당신이 순위를 다시 매기지 않습니다.
   순위가 그렇게 나온 이유를 facts 로 설명하는 것이 당신의 역할입니다.
5. 모든 문장에 `basis` 를 붙입니다. 그 문장이 근거한 fact id 들의 배열입니다.
6. **일반 운전 지식은 환영합니다.** 고속도로 진출입 요령, 유턴할 때 볼 것, 지하차도·고가차도 진입 때 주의점,
   톨게이트 통과 요령, 합류할 때 속도 맞추기 같은 — 어느 도로에서나 통하는 — 지식은 아들을 고수로 만드는
   핵심입니다. 이런 문장의 basis 는 `["{GK}"]` 로 표시합니다. 특정 fact 와 일반 지식을 함께 쓴 문장은
   둘을 모두 basis 에 넣습니다.
7. `roadview_picks` 의 step 은 **kind 가 complex 인 fact 의 step 중에서만** 고릅니다. 없는 step 을 만들지 마세요.
8. `kind` 가 `hazard` 인 fact(id 가 R1.H1 형식)는 **공공데이터로 확인된 위험 지점**입니다.
   사고다발지점·무인단속카메라·어린이/노인보호구역·결빙 사고다발이 여기 들어옵니다.
   이것만 `hazard_notes` 에 씁니다. fact 에 없는 위험을 지어내지 마세요.
   - 사고 건수·사망자 수는 fact 의 숫자를 그대로 씁니다. 겁주지 말고 담담하게 전하세요.
   - 단속카메라는 "여기 단속 있으니 속도 줄여" 정도로, 보호구역은 제한속도를 짚어 주세요.
   - **야간(밤·새벽)에 대해서는 아무 말도 하지 마세요.** 지점 단위 야간 데이터가 존재하지
     않습니다. 그 항목은 서버가 "데이터 없음"으로 고정 표기합니다.
   - 결빙 사고다발 fact 가 있으면 겨울·우천 시 주의로 연결해도 됩니다. 없으면 언급하지 마세요.
9. 경로를 부를 때는 `label`(예: 편한길)을 씁니다. `id`(trafast 같은 영문 코드)나 fact id 는 문장에 쓰지 마세요.
10. 도구를 쓰지 마세요. 파일을 읽거나 검색하지 마세요. 입력 JSON 만으로 답합니다.

## 분기 종류 용어
{_GLOSSARY}

## 출력
지정된 JSON 스키마를 따릅니다. 한국어로 씁니다. 문장은 "~단다", "~하거라" 같은 옛말 대신
"~해", "~하면 돼", "~야" 처럼 자연스러운 아버지 말투로 씁니다.
**`comparison` 을 먼저 씁니다.** 화면에 결론이 먼저 보여야 합니다.
- `comparison.headline`: 결론 한 문장. 어느 길을 왜 추천하는지 (예: "처음이면 편한길로 가. 시간은 같고 유턴이 없어.").
- `comparison.summary`: 세 경로를 비교해 상황별로 어느 걸 택하면 좋을지 2~3문장. headline 을 되풀이하지 마세요.
- `overview`: 경로의 큰 줄기 1~2문장 (주로 어떤 도로를 타는지). 턴바이턴은 화면에 따로 있으니 따라 읽지 마세요.
- `verdict`: 이 경로를 한두 문장으로 총평.
- `comfort_note`: 편의 순위가 왜 그렇게 나왔는지 facts 로 설명. 1~2문장.
- `cautions`: 이 경로에서 미리 알고 가면 좋은 것. 각 항목에 해당 step 이 있으면 step 을 넣습니다.
- `roadview_picks`: 출발 전에 로드뷰로 한 번 봐두면 좋은 지점 0~3개와 이유.
- `hazard_notes`: hazard fact 를 근거로 한 주의 안내. fact 가 없으면 빈 배열. 각 항목에 step 이 있으면 넣습니다.
"""


# --------------------------------------------------------------------------
# CLI 호출
# --------------------------------------------------------------------------
def cli_available() -> tuple[bool, str | None]:
    if not shutil.which("claude"):
        return False, "claude CLI 를 찾을 수 없습니다 — Claude Code 가 설치·로그인되어 있어야 합니다"
    return True, None


def _compact_input(evaluation: dict) -> dict:
    """LLM 에 보낼 최소 입력. metrics 원본은 빼고 facts 만 준다 (수치 출처를 facts 로 한정)."""
    return {
        "trip": evaluation["trip"],
        "routes": [{
            "id": r["id"], "label": r["label"],
            "comfort_rank": r["comfort"]["rank"],
            "facts": r["facts"],
        } for r in evaluation["routes"]],
        "comparison": evaluation["comparison"],
    }


def _extract_json_objects(text: str) -> list[Any]:
    """stdout 에 섞인 텍스트 사이에서 JSON 객체들만 골라낸다 (raw_decode 스캔)."""
    dec = json.JSONDecoder()
    out, i, n = [], 0, len(text)
    while i < n:
        j = text.find("{", i)
        if j < 0:
            break
        try:
            obj, end = dec.raw_decode(text, j)
            out.append(obj)
            i = end
        except json.JSONDecodeError:
            i = j + 1
    return out


def _is_usage_limit(text: str) -> bool:
    t = (text or "").lower()
    return "usage limit" in t or "rate limit" in t or "limit reached" in t


def build_command() -> list[str]:
    return [
        "claude", "--print",
        # stream-json: 생성 중인 구조화 출력이 input_json_delta 조각으로 온다(실측).
        # 마지막 줄의 result 봉투는 json 모드와 같은 모양(result/usage/modelUsage/cost)이다.
        "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        "--model", MODEL_ALIAS,
        # 도구는 StructuredOutput 하나만 허용한다. --json-schema 는 CLI 내부적으로 이 도구 호출로
        # 구현되어 있어(num_turns=2) --tools "" 로 전부 막으면 출력 경로가 사라져 무한 대기한다(실측).
        # Read/Bash/Web* 등은 열리지 않으므로 입력 JSON 만으로 답하게 된다.
        "--tools", "StructuredOutput",
        "--no-session-persistence",                # 세션 파일 남기지 않음
        "--append-system-prompt", SYSTEM_PROMPT,   # 정적 → 캐시 프리픽스
        "--exclude-dynamic-system-prompt-sections",# cwd/git 등 동적 섹션이 캐시를 깨지 않게
        "--json-schema", json.dumps(OUTPUT_SCHEMA, ensure_ascii=False),
    ]


class Cancelled(Exception):
    """on_event 콜백이 던지면 CLI 프로세스를 끊고 재시도 없이 빠져나온다 (클라이언트가 떠난 경우)."""


def parse_partial(text: str) -> Any | None:
    """생성 중인 JSON 앞부분에서 '닫힌 값'까지만 잘라 유효한 JSON 으로 만든다.

    마지막으로 닫힌 객체/배열 직후에서 자르고, 아직 열린 괄호를 역순으로 닫는다.
    쓰다 만 문장(열린 문자열)은 버려지므로 화면에는 완성된 문장만 나간다."""
    stack: list[str] = []
    cut, cut_stack = -1, None
    in_str = esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack:
                return None
            stack.pop()
            cut, cut_stack = i + 1, list(stack)
    if cut < 0:
        return None
    body = text[:cut].rstrip()
    if body.endswith(","):
        body = body[:-1]
    try:
        return json.loads(body + "".join(reversed(cut_stack)))
    except json.JSONDecodeError:
        return None


def _run_stream(cmd: list[str], user_text: str,
                on_event: Callable[[str, Any], None] | None) -> tuple[dict | None, str | None]:
    """CLI 1회 실행. (result 봉투, 오류). 진행 중에는 on_event('stage'|'partial', 값)을 부른다."""
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8")
    killer = threading.Timer(TIMEOUT_SECONDS, proc.kill)
    killer.start()
    stderr_box: list[str] = []
    t_err = threading.Thread(target=lambda: stderr_box.append(proc.stderr.read()), daemon=True)
    t_err.start()
    try:
        proc.stdin.write(user_text)
        proc.stdin.close()
        buf, last_sent, env = "", None, None
        for line in proc.stdout:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("type") == "result":
                env = o
                continue
            ev = o.get("event") or {}
            et = ev.get("type")
            if on_event is None:
                continue
            if et == "content_block_start":
                kind = (ev.get("content_block") or {}).get("type")
                on_event("stage", "writing" if kind == "tool_use" else "thinking")
            elif et == "content_block_delta" and (ev.get("delta") or {}).get("type") == "input_json_delta":
                buf += ev["delta"].get("partial_json", "")
                snap = parse_partial(buf)
                if isinstance(snap, dict) and snap != last_sent:
                    last_sent = snap
                    on_event("partial", snap)
        proc.wait()
    except Cancelled:
        proc.kill()
        raise
    finally:
        killer.cancel()
    if proc.returncode != 0 and env is None:
        if proc.returncode < 0:
            return None, f"claude CLI 시간 초과 ({TIMEOUT_SECONDS}s)"
        t_err.join(timeout=1)
        return None, f"claude CLI 종료코드 {proc.returncode}: {''.join(stderr_box).strip()[:300]}"
    if env is None:
        return None, "CLI 출력에서 result 봉투를 찾지 못함"
    return env, None


def narrate(evaluation: dict, meta_out: dict | None = None,
            on_event: Callable[[str, Any], None] | None = None) -> tuple[dict | None, str | None]:
    """(narration, error). CLI 가 없거나 실패하면 (None, 사유).

    on_event 를 주면 생성 중에 ('stage', 'thinking'|'writing'), ('partial', 부분 JSON),
    재시도 시 ('retry', 사유)를 부른다. 콜백이 Cancelled 를 던지면 즉시 중단한다."""
    ok, why = cli_available()
    if not ok:
        return None, why

    cmd = build_command()
    user_text = ("## Input (JSON)\n\n```json\n"
                 + json.dumps(_compact_input(evaluation), ensure_ascii=False, indent=2)
                 + "\n```\n")

    last_error: str | None = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            log.warning("claude CLI 재시도 %d회 (%ds 후): %s", attempt, delay, last_error)
            if on_event is not None:
                on_event("retry", last_error)
            time.sleep(delay)
        started = time.monotonic()
        env, last_error = _run_stream(cmd, user_text, on_event)
        if env is None:
            continue
        if env.get("is_error"):
            last_error = f"CLI 오류: {str(env.get('result'))[:300]}"
            continue

        text = env.get("result") or ""
        if _is_usage_limit(text):
            return None, f"사용량 한도: {text.strip()[:200]}"   # 재시도 무의미

        # --json-schema 가 걸려 있어 result 는 JSON 문자열이어야 한다. 방어적으로 스캔도 한다.
        data = env.get("structured_output")
        if not isinstance(data, dict):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                inner = [o for o in _extract_json_objects(text) if isinstance(o, dict) and "routes" in o]
                if not inner:
                    last_error = "result 가 JSON 이 아님"
                    continue
                data = inner[-1]

        usage = env.get("usage") or {}
        mu = env.get("modelUsage") or {}
        model = max(mu, key=lambda k: mu[k].get("outputTokens", 0)) if mu else None
        log.info("narrate: model=%s in=%s(+cache w%s r%s) out=%s cost=$%.3f %.1fs",
                 model, usage.get("input_tokens"), usage.get("cache_creation_input_tokens"),
                 usage.get("cache_read_input_tokens"), usage.get("output_tokens"),
                 env.get("total_cost_usd") or 0, time.monotonic() - started)
        if meta_out is not None:
            meta_out.update(model=model, cost_usd=env.get("total_cost_usd"),
                            duration_ms=env.get("duration_ms"), usage=usage)
        return data, None

    return None, last_error or "알 수 없는 실패"


# --------------------------------------------------------------------------
# 검증 — 근거 ID 실재 여부, roadview step 유효성
# --------------------------------------------------------------------------
def _plain(text: str, labels: dict[str, str]) -> str:
    """문장에 새어 나온 내부 코드(trafast 등)를 사람이 읽는 이름으로 바꾼다."""
    for rid, label in labels.items():
        text = re.sub(rf"\s*\(\s*{re.escape(rid)}\s*\)", "", text)
        text = re.sub(rf"\b{re.escape(rid)}\b", label, text)
    return text


def _check(sent: dict, ids: set[str], labels: dict[str, str] | None = None) -> dict:
    basis = sent.get("basis") or []
    ok = bool(basis) and all(b == GK or b in ids for b in basis)
    out = dict(sent)
    if labels and isinstance(out.get("text"), str):
        out["text"] = _plain(out["text"], labels)
    out["unverified"] = not ok
    out["general_knowledge"] = bool(basis) and all(b == GK for b in basis)
    return out


def validate_narration(narration: dict, evaluation: dict) -> dict:
    """basis 를 사실 ID 와 대조해 unverified 표시. 없는 step 의 roadview_picks 는 제거.
    문장은 지우지 않는다 — 사용자가 회색 문장을 보고 판단한다."""
    ids = all_fact_ids(evaluation)
    labels = {r["id"]: r["label"].split(" · ")[0] for r in evaluation["routes"]}
    chk = lambda x: _check(x, ids, labels)
    out: dict[str, Any] = {"routes": [], "comparison": {"summary": []}}

    for r in narration.get("routes", []):
        rid = r.get("id")
        steps = complex_steps(evaluation, rid)
        out["routes"].append({
            "id": rid,
            "overview": [chk(s) for s in r.get("overview", [])],
            "verdict": chk(r.get("verdict") or {"text": "", "basis": []}),
            "comfort_note": chk(r.get("comfort_note") or {"text": "", "basis": []}),
            "cautions": [chk(s) for s in r.get("cautions", [])],
            "hazard_notes": [chk(s) for s in r.get("hazard_notes", [])],
            "roadview_picks": [p for p in r.get("roadview_picks", []) if p.get("step") in steps],
            "dropped_picks": sum(1 for p in r.get("roadview_picks", []) if p.get("step") not in steps),
        })
    cmp = narration.get("comparison") or {}
    out["comparison"]["summary"] = [chk(s) for s in cmp.get("summary", [])]
    out["comparison"]["headline"] = chk(cmp["headline"]) if cmp.get("headline") else None

    total = sum(len(r["overview"]) + len(r["cautions"]) + len(r["hazard_notes"]) + 2
                for r in out["routes"]) + len(out["comparison"]["summary"]) \
        + int(out["comparison"]["headline"] is not None)
    bad = sum(
        sum(1 for s in r["overview"] if s["unverified"])
        + sum(1 for s in r["cautions"] if s["unverified"])
        + sum(1 for s in r["hazard_notes"] if s["unverified"])
        + int(r["verdict"]["unverified"]) + int(r["comfort_note"]["unverified"])
        for r in out["routes"]
    ) + sum(1 for s in out["comparison"]["summary"] if s["unverified"]) \
        + int(bool(out["comparison"]["headline"] and out["comparison"]["headline"]["unverified"]))
    out["stats"] = {"sentences": total, "unverified": bad}
    return out
