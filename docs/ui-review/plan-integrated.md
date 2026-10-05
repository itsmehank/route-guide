# route-guide UI 개선 — 통합 계획 (2026-10-02)

입력 4종을 코드와 대조해 하나로 합쳤다.

| 출처 | 파일 | 성격 |
|---|---|---|
| 서브에이전트 리뷰 | `review-subagent.md` | 코드 분석 + Chrome 일부 실행 |
| Cowork 리뷰 | `review-cowork.md` + `cowork-shots/`(30장) | Chrome 시나리오 7종 실행, [확인]/[코드]/[추정] 구분 |
| 서브에이전트 조사 | `research-subagent.md` | 최신 기술·UX 조사 |
| 웹 Claude 조사 | `research-web-claude.md` | 최신 기술·UX 조사 (npm·web-features 데이터셋 기준) |

## 0. 코드로 직접 재확인한 것

| 주장 | 결과 | 근거 |
|---|---|---|
| 비교표 동률이면 첫 칸만 강조 | 맞음 | `web/app.html:1260-1261` `vals.indexOf(m)` |
| 교통량 레이어 기본 ON | 맞음 | `web/app.html:382` `checked`, `:1388` `setMap(map)` |
| 검색 0건이면 조용히 닫힘 | 맞음 | `web/app.html:868`, `:871` `catch(){}` |
| 경유지 선택 시 재탐색 안 함 | 맞음 | `web/app.html:851` (`refreshGo()`만 호출) |
| 같은 경로 병합 없음 | 맞음 | `serve.py:163-178` 옵션별로 그대로 append |
| 반응형 CSS 없음 | 맞음 | `@media` 0개 |
| (웹 Claude) 스트리밍하려면 `ThreadingHTTPServer` 필요 | **이미 적용됨** | `serve.py:19`, `serve.py:316` |
| (양쪽 미확인) `--json-schema`와 스트리밍 동시 사용 | **가능 — 실측** | `claude -p --output-format stream-json --verbose --include-partial-messages --tools StructuredOutput --json-schema …` → `input_json_delta` 40조각 + 최종 `structured_output`. 부분 JSON을 파싱해 **문장이 완성될 때마다** 내보낼 수 있다 |

## 1. 네 문서가 일치한 것 (확정)

1. **같은 경로 카드 병합** — 카드 1=3 (Cowork: 경로점 547/547 동일 실측).
2. **비교표 동률 강조 버그**.
3. **교통량 레이어 기본 OFF** — 경로 색과 같은 3색이라 경로가 묻힘.
4. **경로 비교 2단계화** — 지표·비교표·위험은 즉시, 서술만 이어서. 실측 117~155초 무피드백.
5. **비교 결과 정보 구조** — 결론 1줄을 맨 위로, 핵심 4지표, 나머지 접기. 탭당 약 4,000자.
6. **제거 대상** — `🚗 자동차` 칩, `Directions 5/15` 표기, 택시비, 상세 헤더 요약 중복, 단계 `◎` 버튼.
7. **단일 패널 + 모바일 바텀시트(3단)** — 지금은 패널 3장이 absolute로 겹치고, 상세가 열리면 642px가 지도를 덮고, 390px에서는 지도가 78px만 남음.
8. **위험 지점 지도 표시** — 지금은 목록에만 있음.
9. **접근성 기본기** — 카드·단계 키보드 불가, 라벨 0개, `aria-live` 0개, 10~11.5px 글자 30곳.
10. **생성형 UI(AI가 화면 구성)는 부적합** — LLM에게서는 데이터만 받고, 고정 컴포넌트가 그린다.
11. **기술 경로: 빌드 없는 A안을 먼저**, 상태 관리가 버거워지면 컴포넌트 프레임워크로.

## 2. 의견이 갈린 것 → 권장안

| 쟁점 | 의견 | 권장 | 이유 |
|---|---|---|---|
| B안 프레임워크 | 웹 Claude: Preact+Signals(1순위)·Vue. 서브에이전트: Svelte 5+Vite. Cowork: Lit/Preact+htm | **Preact + htm + Signals (import map, 빌드 없음)**, 10.x 고정 | A안에서 끊김 없이 넘어갈 수 있음. Preact 11은 2026-09-30에 나와 쓰기엔 아직 이르다. 빌드를 도입하기로 하면 그때 Svelte 5 재검토 |
| 본문 글자 크기 | 웹 Claude 16~17px(KRDS), 서브에이전트 15px, Cowork 15~16px | **본문 15px, 보조 13px, 최소 12px**로 시작해 화면 보고 조정 | KRDS는 공공 사이트 기준. 지도 옆 좁은 패널에서는 15px이 균형점. 카드의 시간 숫자만 크게 |
| 스트리밍 방식 | 웹 Claude: POST fetch 스트리밍(SSE는 GET만). 서브에이전트: SSE | **SSE(GET)** | 서버가 이미 출발·도착 키로 경로를 캐시한다(`serve.py:144-148`). 경로 데이터를 POST로 보낼 필요가 없음 |
| 중복 경로 병합 위치 | 서브에이전트: 클라이언트. Cowork: 서버 | **서버** (path 비교, 라벨 합치기 "빠른길 · 최적") | 비교 엔진과 LLM 서술도 중복 입력을 받지 않게 됨 |
| 근거 사실 표 | 서브에이전트: 삭제. Cowork: 접어서 맨 아래 | **접어서 유지** | 스펙 D2(근거 기반 서술)의 검증 수단 |
| LLM 출력 스키마 | 웹 Claude: summary/pros/cons/recommendation/citations | **현 스키마(문장마다 근거 ID) 유지 + `verdict`(결론 1줄) 필드만 추가** | 숫자를 API 값에서 가져오는 근거 구조는 스펙 D2에 이미 있음 |

## 3. 한쪽에서만 나온 중요한 발견

- **Cowork:** 로드뷰가 240×124 말풍선이라 노면 화살표를 읽기 어려움(상). 위험 지점의 `지도` 버튼이 위험 지점이 아닌 가장 가까운 안내 단계로 감. 같은 출발·도착이면 서버 원문 JSON 노출. 자동완성에 충남 장항선이 섞임(거리 정렬 없음). 지도 라벨·저작권 표기 겹침. 다시입력 후 상태 잔존.
- **서브에이전트 리뷰:** `/api/route`도 Abort가 없어 늦은 응답이 화면을 덮을 수 있음(`app.html:916`). `esc()`가 `"`를 이스케이프하지 않는데 title 속성에 들어감(`app.html:433`, `:1250`).
- **웹 Claude:** NCP Polyline hover 이벤트는 `clickable: true`일 때만 발생(카드↔경로선 연동의 전제). Google Maps(2026-03)는 대안 경로 장단점을 한 문장으로 보여줌 → 카드 차별점 태그의 근거. 데이터셋 기준 지원 현황표(Baseline).

## 4. 실행 계획

### P0 — 오판과 잡음 제거 (약 1일, 구조 변경 없음)
| # | 할 일 | 위치 |
|---|---|---|
| 1 | 비교표 동률 강조 수정 | `app.html:1258-1262` |
| 2 | 교통량 레이어 기본 OFF | `app.html:382`, `:1388` |
| 3 | 검색 0건·오류 시 드롭다운에 안내 | `app.html:866-871` |
| 4 | 경유지 선택 시 자동 재탐색 (출발·도착이 있으면) | `app.html:851` |
| 5 | `🚗` 칩, `Directions N`, 택시비, 단계 `◎` 제거, 상세 헤더 1줄 | `app.html:336`, `:355`, `:922`, `:941`, `:1046`, `:1066` |
| 6 | 같은 출발·도착 차단 + 에러 문구를 사용자 언어로 | `app.html:907`, `:918-919` |
| 7 | `/api/route`·`/api/compare` AbortController + 요청 key 검사, `cmpData` 일치 시 즉시 렌더 | `app.html:916`, `:1222-1243` |
| 8 | 다시입력 시 상태 초기화 | `app.html:1427-1437` |
| 9 | `esc()` 따옴표 이스케이프 | `app.html:433` |
| 10 | 위험 목록 `<details>`로 접고 유형별 개수 요약 | `app.html:1330-1346` |

### P1 — 서버: 중복 병합과 비교 2단계화 (1~2일)
- `/api/route`: path가 같은 옵션 병합, 라벨 합치기.
- `/api/compare` 분리 → `/api/evaluate`(지표·비교표·위험, 즉시) + `/api/narrate`(SSE). `input_json_delta`를 이어 붙여 문장이 완성될 때마다 `event: sentence` 전송, 끝에 `event: done`.
- 화면: 비교표 즉시 → "설명 작성 중 · 38초" + 중지 버튼 → 문장이 하나씩 추가 → 끝나면 `role=status`로 한 줄 알림.

### P2 — 골격: A안 (3~5일)
- `app.html`을 ES 모듈로 분리: `geometry.js`(454-673, 그대로), `map.js`, `search.js`, `routes.js`, `detail.js`, `compare.js`, `state.js`.
- 상태 한 곳: `{inputs, routes, sel, view: 'list'|'detail'|'compare', step, compare:{status, data}}`. 패널은 `view`에 따라 그린다(지금처럼 DOM class로 판단하지 않음).
- 단일 패널(목록 ↔ 상세 ↔ 비교 전환, View Transitions), 데스크톱 접이식 사이드 패널 / 모바일 3단 바텀시트(container queries + `@media`).
- 디자인 변수: 색(출발 파랑·경유 주황·도착 빨강·혼잡도 3색), 글자 15/13/12, Pretendard 동적 서브셋, `keep-all`, `tabular-nums`.
- `<dialog>`·Popover·`command`/`commandfor`로 열고 닫기 JS 줄이기. Limited 기능(`interpolate-size` 등)은 `@supports`로 감싼 장식만.

### P3 — 핵심 기능 고도화 (P2 위에서)
- **로드뷰를 주요 요소로:** 패널 상단 16:9 + 전체화면, 다음·이전 단계 예열.
- **위험 지점 지도 레이어:** 유형별 아이콘, 목록 ↔ 지도 상호 강조, 클릭하면 위험 좌표로 이동(패널 유지).
- **경로 카드 재설계:** 시간 크게 + 차별점 태그 1개 + 혼잡 비율 막대 1줄. 카드 선택 = 상세 열기. 카드 hover ↔ 경로선 강조(`clickable: true`).
- **비교 정보 구조:** 결론 1줄(`verdict`) → 핵심 4지표 → 출발 전 체크리스트(주의 + 로드뷰 추천 통합) → 접힌 상세(서술·위험 원문·근거 사실).
- **접근성:** 자동완성 combobox(↑↓·Enter·Esc), 카드·단계 `<button>`, 24px 이상 타깃(모바일 44px), `aria-live`.
- 자동완성 거리 정렬(출발지·지도 중심 기준) — `/api/search`에 좌표를 넘길 수 있는지 확인 필요.

### P4 — (조건부) Preact + Signals 전환
- 신호: 한 동작이 카드·지도·비교 세 곳을 손으로 갱신해야 하고 순서 버그가 생기면.
- 지도 인스턴스는 한 번만 만들고, 이후엔 경로선·마커 메서드만 호출. Shadow DOM 안에 지도를 넣지 않는다.

## 5. 결정이 필요한 것
1. 진행 순서 P0 → P1 → P2 → P3 동의 여부 (P0·P1은 지금 구조에서도 바로 가능)
2. 본문 글자 크기 15px 시작안
3. 첫 진입 시 죽전역→강남역 자동 입력(데모용) 유지 여부
4. 경유지 1개 제한 유지 여부 (Directions 15는 최대 5개 지원)
5. P4 프레임워크 전환을 미리 정할지, 신호가 보일 때 정할지

## 6. 남은 미확인
- View Transitions가 실제 NCP 지도 위에서 문제없는지 (P2에서 프로토타입으로 확인)
- Popover·`<dialog>`(top layer)와 지도 드래그·휠 이벤트 충돌
- NCP TrafficLayer 투명도 옵션, 로드뷰 정적 썸네일 API 존재 여부
- Pretendard 고정폭 숫자(tnum) 렌더링
