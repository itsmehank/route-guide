# route-guide UI 개편 리서치 — 2026 웹 UI 기술·UX 패턴

- 작성일: 2026-10-02 (서브에이전트 웹 리서치)
- 대상: `web/app.html` (1,461줄, vanilla JS + inline CSS + innerHTML 템플릿, 빌드 없음) + `serve.py` (Python stdlib) + NCP Web Dynamic Map JS v3
- 표기: **[미검증]** = 1차 출처로 확인 못 했거나 출처 간 상충. 브라우저 지원 수치는 주로 web-features explorer(Baseline 공식 데이터, 2026-10 조회) 기준.

---

## TL;DR

1. **2026년 현재 "JS를 줄여주는" 네이티브 기능 대부분이 Baseline이다.** `<dialog>`, Popover, Invoker Commands(`command`/`commandfor`, 2025-12 Baseline), View Transitions(same-document, 2025-10 Baseline), Navigation API(2026-01 Baseline), `@starting-style`, container queries, `:has()`, CSS nesting, `@scope`(2026-03), `light-dark()`, `field-sizing`(2026-06)는 바로 써도 된다. 반면 customizable `<select>`, `interpolate-size`/`calc-size()`, 스크롤 기반 애니메이션, 문서 간 view transition, `text-wrap: pretty`는 아직 **Firefox(또는 Safari)가 막고 있으니** 점진적 향상(progressive enhancement)으로만 쓴다. anchor positioning은 출처마다 말이 다르다(아래 참고).
2. **프레임워크 추천: (A) 빌드 없이 "ES 모듈로 쪼개기 + 네이티브 플랫폼 + (선택) Preact+htm+Signals를 import map으로 붙이기"**, **(B) Vite 8 + Svelte 5(runes, 컴포넌트 단위 스타일) + Tailwind v4**. Svelte 5의 `{@attach}`가 명령형 지도 SDK를 감싸기에 가장 깔끔하다. SvelteKit은 필요 없다(백엔드가 Python이고 화면이 하나뿐).
3. **가독성 개선 효과가 가장 큰 단일 조치는 타이포그래피다.** 지금 본문은 `13px/1.5` 시스템 폰트인데, 공공 디자인 시스템 KRDS는 본문 17px·행간 150%를 쓴다. 패널 본문 15–16px, Pretendard Variable(동적 서브셋), `word-break: keep-all`, `font-variant-numeric: tabular-nums`(시간·거리 숫자 정렬)로 바꾼다.
4. **지도 앱 UX의 표준 레이아웃**: 데스크톱은 접을 수 있는 좌측 패널(경로 카드 → 상세 2단계), 모바일은 3단 snap 바텀시트를 쓴다. 카드와 지도를 서로 연동하고(카드에 마우스를 올리면 해당 폴리라인 강조, 폴리라인을 클릭하면 카드 선택), 비교는 Google Maps처럼 **"트레이드오프 한 줄"(예: "8분 빠름 · 통행료 +1,200원")** 을 먼저 보여주고 표와 LLM 서술은 펼쳐서 보게 한다.
5. **느린 LLM 서술(수십 초)은 스트리밍과 분리 렌더링으로 처리한다.** `/api/compare`를 ① 즉시 나오는 숫자 표·위험 지점 ② 스트리밍되는 서술로 나눈다. 서버는 `claude -p --output-format stream-json --include-partial-messages`의 출력을 SSE로 그대로 넘기면 된다. 클라이언트는 서술 자리에 스켈레톤을 깔고 진행 단계 문구와 취소 버튼을 보여준다. "AI가 화면을 직접 구성하는" generative UI(A2UI 등)는 이 앱에는 과하다.

### 추천 스택 2안

| | **안 A: 최소 변경(no-build 유지)** | **안 B: 본격 전환** |
|---|---|---|
| 구성 | `app.html` → `index.html` + `css/*.css`(tokens/layout/components, `@layer`) + `js/*.js`(ES 모듈: `map.js`, `search.js`, `routes.js`, `compare.js`, `ui/*.js`). 템플릿은 `<template>` 복제, 또는 import map으로 **Preact + htm + @preact/signals**(빌드 불필요) | **Vite 8**(Rolldown) + **Svelte 5**(runes, 플레인 SPA, SvelteKit 없이) + **Tailwind v4** + (선택) **Bits UI/shadcn-svelte**. `serve.py`는 `/api/*`와 `dist/` 정적 서빙만 맡고, 개발 중에는 Vite proxy 사용 |
| 네이티브 활용 | dialog/popover/invoker commands, container queries, `:has()`, nesting, `@scope`, `light-dark()`, same-doc View Transitions, `@starting-style` | 왼쪽과 같음(프레임워크 위에서도 그대로 쓴다) |
| 지도 연동 | `map.js` 싱글턴. 경로 상태(선택/hover)는 signal 또는 CustomEvent로 전달 | `MapView.svelte` + `{@attach}`로 지도를 1회 생성. `$effect`로 폴리라인/마커만 동기화 |
| LLM UX | `serve.py`에 `/api/compare/stream`(SSE) 추가 + `fetch` 스트림 읽기 | 왼쪽과 같음 |
| 공수(1인) | **3–5일**(모듈 분리 1–2일, CSS 토큰·타이포·레이아웃 1–2일, 스트리밍 1일) | **1.5–3주**(셋업 0.5일, 컴포넌트화 5–8일, 바텀시트·반응형 2–3일, 스트리밍·마감 2–3일) |
| 장점 | 빌드 도구 없음, 위험 낮음, 데모 성격에 맞음 | 컴포넌트 경계가 명확하고, 동적 화면 구성(패널 상태 머신)과 유지보수가 쉬움 |
| 단점 | 상태가 늘어나면 innerHTML 패턴이 다시 엉킨다 | Node 툴체인이 생기고, 1회성 마이그레이션 비용이 든다 |

> 판단 기준: 앞으로 기능을 계속 붙일 계획이면 **B**, "데모를 깔끔하게"가 목표라면 **A**로 충분하다. A에서 B로 넘어갈 때 버리는 것이 거의 없도록(CSS 토큰, 모듈 경계, SSE API는 그대로 재사용) **A를 먼저 하고 필요하면 B로 가는 순서**를 권한다.

---

## 1. 네이티브 웹 플랫폼 기능 (JS 감소)

Baseline 정의: Chrome·Edge·Firefox·Safari(데스크톱+모바일)가 모두 지원하면 "Newly available", 그 후 30개월이 지나면 "Widely available"([web.dev Interop 2026](https://web.dev/blog/interop-2026), 2026-02-12).

| 기술 | 무엇 | 지원 현황(2026-10) | 이 앱 적용 포인트 | 출처 |
|---|---|---|---|---|
| `<dialog>` (+`showModal`) | 네이티브 모달(포커스 트랩, Esc, `::backdrop`) | Widely available | 경로 비교 화면, 로드뷰 확대 화면을 `<dialog>`로 만든다. 직접 짠 overlay/z-index/Esc 처리를 제거 | MDN |
| `dialog closedby="any"` | 바깥 클릭(light dismiss)으로 닫기 | **제한적**: Chrome 134, Firefox 141. Safari 미지원. Interop 2026 대상 | 지원하지 않는 브라우저용으로 backdrop 클릭 JS 3줄을 fallback으로 둔다 | [web-features: dialog-closedby](https://web-platform-dx.github.io/web-features-explorer/features/dialog-closedby/) |
| Popover API (`popover`) | top-layer 오버레이, light dismiss, 접근성 기본 제공 | Baseline Newly (2025-01-27) | 자동완성 목록, 경로 카드 "⋯" 메뉴, 혼잡도 범례, 토스트(`popover="manual"`) | [web-features: popover](https://web-platform-dx.github.io/web-features-explorer/features/popover/) |
| `popover="hint"` | auto popover를 닫지 않는 툴팁 | 제한적: Chrome 151, Firefox 153. Safari 미지원 | 폴리라인 구간 툴팁 등. fallback은 `manual` | [web-features: popover-hint](https://web-platform-dx.github.io/web-features-explorer/features/popover-hint/) |
| Invoker Commands (`command`/`commandfor`) | 버튼에서 JS 없이 dialog·popover 열기/닫기 | Baseline Newly (2025-12-12; Chrome 135, Firefox 144, Safari 26.2) | `<button commandfor="cmp" command="show-modal">비교</button>` 형태로 onclick 핸들러를 제거 | [web-features: invoker-commands](https://web-platform-dx.github.io/web-features-explorer/features/invoker-commands/) |
| CSS Anchor Positioning | 요소를 다른 요소 기준으로 배치(툴팁·드롭다운) | **[상충]** Firefox 147(2026-01)로 Baseline Newly라는 web.dev 1월 글이 있다. 반면 현재 web-features 데이터와 caniuse는 Chrome 125+/Firefox 147+를 "부분 지원", Safari 27만 "완전 지원"으로 표시한다(기능 정의가 바뀐 것으로 보임). Interop 2025·2026 연속 대상 | 자동완성 목록을 입력창에 붙이는 기본 `position-anchor` + `position-area` 정도만 쓰고, `@position-try` flip은 fallback을 둔다 | [web.dev 2026-01](https://web.dev/blog/web-platform-01-2026), [caniuse](https://caniuse.com/css-anchor-positioning), [web-features](https://web-platform-dx.github.io/web-features-explorer/features/anchor-positioning/) |
| View Transitions (same-document) | `document.startViewTransition()`으로 DOM 변경 전후를 애니메이션 | Baseline Newly (2025-10-14, Firefox 144) | "경로 목록 ↔ 상세" 전환, 카드 선택 시 카드 확대(morph). `view-transition-name`은 패널 요소에만 붙이고 **지도 컨테이너는 제외**(리스크 절 참고) | [web-features: view-transitions](https://web-platform-dx.github.io/web-features-explorer/features/view-transitions/) |
| View Transitions (cross-document) | MPA 페이지 이동 간 전환 | 제한적: Chrome 126, Safari 18.2. Firefox 미지원 | 단일 페이지 앱이라 해당 없음 | [web-features: cross-document-view-transitions](https://web-platform-dx.github.io/web-features-explorer/features/cross-document-view-transitions/) |
| Navigation API | `navigation.navigate`/`navigate` 이벤트로 SPA 라우팅·뒤로가기 처리 | Baseline Newly (2026-01; Firefox 147, Safari 26.2) | URL에 출발/도착/선택 경로/상세 단계를 담는다(`?o=..&g=..&r=1&view=detail`). 뒤로가기로 "상세 → 목록" 복귀, 새로고침해도 상태 복원, 링크로 상태 공유 | [web.dev Baseline Navigation API](https://web.dev/blog/baseline-navigation-api?hl=en), [InfoQ 2026-05](https://www.infoq.com/news/2026/05/navigation-api-browser/) |
| Container queries (size) | 부모 크기에 따라 스타일 지정 | Widely available (2025-08) | 패널 폭(접힘/320/480px)에 따라 경로 카드를 1열↔2열로 바꾸고 상세 정보를 노출/축약. 화면 폭이 아니라 패널 폭 기준이라 **동적 화면 구성**에 바로 맞는다 | [web-features: container-queries](https://web-platform-dx.github.io/web-features-explorer/features/container-queries/) |
| Container style queries | 커스텀 프로퍼티 값으로 `@container style()` | Interop 2026 대상(아직 전 브라우저 아님) | 테마나 밀도(`--density: compact`) 전환. 지금은 클래스 토글로 대체 | [web.dev Interop 2026](https://web.dev/blog/interop-2026) |
| `:has()` | 부모/형제 상태 선택자 | Baseline (2023-12~) | `#side:has(.card[aria-selected=true])`, `.inputs:has(input:focus)` 같은 식으로 상태 클래스 토글 JS를 줄인다 | MDN |
| CSS Nesting | Sass 없이 중첩 | Baseline (2023-12~) | inline CSS를 컴포넌트별로 중첩해 정리 | MDN |
| `@scope` | 선택자 적용 범위 제한(상·하한) | Baseline Newly (2026-03-24, Safari 26.4) | 빌드 없는 안 A에서 카드·상세·비교 스타일 충돌을 막는다(Svelte로 가면 자동으로 해결됨) | [web-features: scope](https://web-platform-dx.github.io/web-features-explorer/features/scope/) |
| `light-dark()` + `color-scheme` | 한 줄로 라이트/다크 색 지정 | Baseline Newly (2024-05), 2026-11 Widely 예정 | `--ink: light-dark(#1b1e21,#e8eaed)` 식으로 토큰화. 지도는 NCP 스타일에 맞춰야 하므로 다크는 우선순위 낮음 | [web-features: light-dark](https://web-platform-dx.github.io/web-features-explorer/features/light-dark/) |
| `@starting-style` | `display:none`에서 나타날 때 진입 트랜지션 | Baseline Newly (2024-08) | popover·dialog·토스트·카드의 등장 애니메이션을 JS 없이 처리(`transition-behavior: allow-discrete`와 함께) | [web-features: starting-style](https://web-platform-dx.github.io/web-features-explorer/features/starting-style/) |
| `interpolate-size` / `calc-size()` | `height: auto`로 가는 트랜지션 | **Chromium만**(129+). Firefox·Safari 미지원 | 턴바이턴 단계 펼침, `<details>` 아코디언. `:root{interpolate-size:allow-keywords}` 한 줄 추가로 미지원 브라우저는 즉시 펼쳐짐 | [web-features: interpolate-size](https://web-platform-dx.github.io/web-features-explorer/features/interpolate-size/) |
| Scroll-driven animations | `animation-timeline: scroll()/view()` | **제한적**: Chrome 115, Safari 26. Firefox 미지원(Interop 2026 대상). 블로그에는 "Baseline 됐다"는 글도 있으나 web-features 데이터가 우선 **[상충 → 미지원으로 간주]** | 바텀시트 높이에 연동한 헤더 그림자·지도 dim 정도의 장식에만 쓴다 | [web-features: scroll-driven-animations](https://web-platform-dx.github.io/web-features-explorer/features/scroll-driven-animations/) |
| Customizable `<select>` (`appearance: base-select`) | 네이티브 select의 picker·option을 CSS로 꾸미기 | 제한적: Chrome 135, **Safari 27(2026-09)**. Firefox 미지원 | "경로 옵션(실시간빠른/무료/최단)" 드롭다운. 미지원 브라우저에서는 일반 select로 보이므로 안전 | [web-features: customizable-select](https://web-platform-dx.github.io/web-features-explorer/features/customizable-select/) |
| `field-sizing: content` | 입력창이 내용에 맞춰 늘어남 | Baseline Newly (2026-06-16, Firefox 152) | 긴 장소명 입력, 경유지 칩 | [web-features: field-sizing](https://web-platform-dx.github.io/web-features-explorer/features/field-sizing/), [web.dev 2026-06](https://web.dev/blog/web-platform-06-2026) |
| `text-wrap: balance` / `pretty` | 제목 줄 균형 / 고아 단어 방지 | balance는 Baseline(2024). pretty는 Firefox 미지원 | 카드 제목과 LLM 요약 문단(pretty는 장식 수준) | [web-features: text-wrap-pretty](https://web-platform-dx.github.io/web-features-explorer/features/text-wrap-pretty/) |
| `focusgroup` 속성 | 방향키로 이동하는 composite 위젯 | Chrome 150만 | 경로 카드 목록의 방향키 이동. 지금은 roving tabindex를 직접 구현 | [web.dev 2026-06](https://web.dev/blog/web-platform-06-2026) |
| scroll-snap | 스냅 스크롤 | Baseline (Interop 2026에서 정합성 개선 중) | **모바일 바텀시트의 3단 snap**(peek/half/full)을 JS 제스처 라이브러리 없이 구현 | [web.dev Interop 2026](https://web.dev/blog/interop-2026) |

**이 앱에서 우선 적용할 순서**: ① `<dialog>`+invoker commands(비교/로드뷰) → ② popover(자동완성·토스트) → ③ container queries(패널 폭 반응형) → ④ View Transitions(목록↔상세) → ⑤ Navigation API(URL 상태) → ⑥ 나머지는 장식.

---

## 2. 프레임워크 옵션과 트레이드오프

앱 특성: 화면 1개, 상태는 적지만 서로 얽혀 있다(입력/후보/경로 3개/선택/hover/상세 단계/비교 상태). 명령형 지도 SDK가 DOM 일부와 전역 상태를 소유한다. 사용자는 1명이고 SEO·SSR은 필요 없다.

| 기술 | 무엇 | 지원 현황(2026) | 이 앱 적용 포인트 | 출처 |
|---|---|---|---|---|
| Vanilla + Web Components / **Lit 3** | 표준 Custom Elements + 반응형 템플릿(Lit) | Lit 3.3.x 안정. Lit 4는 확인되지 않음 | 빌드 없이 쓸 수 있다(CDN ESM). 다만 **Shadow DOM 안에 NCP 지도를 넣는 것은 피해야 한다**(SDK의 전역 CSS·이벤트 가정 때문. **[미검증]** 안전하게 light DOM 사용 권장) | [PkgPulse Lit vs Svelte 2026](https://www.pkgpulse.com/guides/lit-vs-svelte-2026) |
| **htmx 4** / Alpine | 서버가 HTML 조각을 반환 / 속성 기반 반응성 | htmx 4.0.0 출시 2026-08-28(fetch 기반, morph swap 내장, `hx-sse` 확장). npm `latest`는 2027 초까지 2.x 유지 | 서버(Python)가 카드 HTML을 렌더링하는 구조로 바꿔야 한다. 지도 연동은 결국 JS가 필요하고 hover 동기화 같은 클라이언트 상태가 많아 **맞지 않는 편** | [InfoQ htmx 4](https://www.infoq.com/news/2026/09/htmx-4-released/) |
| **Preact + Signals** (+htm) | 3KB대 React 호환 + 세밀한 반응성 | @preact/signals 2.11.x(2026-09). Preact 11은 2026-09 말 정식 출시 신호가 있음 **[미검증]**, 10.x는 안정 | **import map으로 빌드 없이** `htm` 태그드 템플릿을 쓸 수 있다. `selectedRoute`/`hoverRoute` signal을 지도 effect와 카드가 함께 구독. 안 A의 확장 옵션 | [OpenReplay Preact 2026](https://blog.openreplay.com/whats-new-preact-2026/), [npm @preact/signals](https://www.npmjs.com/package/@preact/signals) |
| **Svelte 5 (runes)** | 컴파일러 기반, `$state/$derived/$effect`, 컴포넌트 범위 CSS | 2024-10 정식 출시, 2026년에도 활발(5.4x~). `{@attach}`로 요소 생명주기 연결 | **명령형 SDK 통합이 가장 깔끔하다**: `<div {@attach mountMap}>`에서 지도를 1회 생성하고 cleanup 반환. `$effect`로 선택 경로 변경 시 폴리라인 스타일만 갱신. 마이그레이션이 HTML/CSS를 거의 그대로 옮기는 수준 | [Svelte attachments 문서](https://svelte.dev/docs/svelte/svelte-attachments), [What's new in Svelte 2026-06](https://svelte.dev/blog/whats-new-in-svelte-june-2026) |
| SvelteKit | 풀스택 메타프레임워크(remote functions 등) | 2.6x, remote functions 정착 | 백엔드가 Python이고 라우트가 1개라 **불필요**. 플레인 Vite+Svelte 권장 | [SvelteKit remote functions](https://svelte.dev/docs/kit/remote-functions) |
| SolidJS | 시그널 기반 JSX | **2.0이 RC**(2026-08), 1.x 안정 | 성능·모델은 좋지만 메이저 전환기라 지금 들어가기엔 애매하다 | [InfoQ Solid 2.0 beta](https://www.infoq.com/news/2026/05/solidjs-2-async/), [Road to 2.0](https://github.com/solidjs/solid/discussions/2425) |
| React 19.2 + **Compiler 1.0** | 자동 메모이제이션 | Compiler 1.0 정식(2025-10-07), React 19.2(2025-10-01) | 생태계가 가장 크다(shadcn/ui, Base UI). 하지만 이 규모 앱에는 런타임·보일러플레이트가 과하고, 지도 통합에는 `useRef`/`useEffect` 관용구가 필요(StrictMode에서 이중 실행 주의) | [React Compiler v1.0](https://react.dev/blog/2025/10/07/react-compiler-1) |
| Vue 3.5 / Vapor | SFC, Vapor = VDOM 없는 컴파일 | 3.5.x가 latest. **3.6 Vapor는 RC**(rc.9, 2026-09-18) | 대안으로 무난하지만 Vapor 이점을 누리려면 정식 출시를 기다려야 한다 | [Vue 3.6 Vapor RC](https://forkbyte.nl/en/blog/vue-36-vapor-mode-rc) **[2차 출처]** |
| Astro islands | 정적 페이지 + 부분 하이드레이션 | 안정 | 거의 모든 영역이 인터랙티브한 지도 앱이라 이점이 없다 | — |
| **Vite 8** (Rolldown) | 개발 서버 + 번들러 | Vite 8 정식 2026-03-12, Rolldown 1.0 2026-05-07 | 안 B의 기반. `server.proxy`로 `/api` → `serve.py` | [Vite 8 발표](https://vite.dev/blog/announcing-vite8), [The Register](https://www.theregister.com/2026/03/16/vite_8_rolldown/) |

### 추천

- **1순위(안 B): Vite 8 + Svelte 5(플레인 SPA).** 이유: ① `app.html`의 마크업과 CSS를 `.svelte` 파일로 거의 그대로 옮길 수 있다(innerHTML 문자열 → 템플릿 블록, `esc()` 불필요). ② `{@attach}`/`$effect`가 "지도 1회 생성 + 오버레이 동기화" 패턴과 정확히 맞는다. ③ 범위 CSS 덕분에 `@scope`나 명명 규칙에 신경 쓸 필요가 없다. ④ 번들이 작다.
- **2순위(안 A 확장): no-build + Preact/htm/Signals(import map).** 빌드 도구 없이 컴포넌트와 반응성을 얻는다. 나중에 Vite를 붙여도 코드가 그대로 동작한다.
- React 계열은 "shadcn/ui 같은 기성 컴포넌트를 꼭 쓰고 싶다"는 요구가 있을 때만 선택한다.

**지도 SDK 통합 공통 원칙**: 지도 인스턴스는 반응형 상태 밖(모듈 싱글턴)에 두고, 프레임워크는 "선택 경로 id, hover id, 경로 데이터"만 상태로 가진다. effect에서 폴리라인을 `setOptions({strokeOpacity, strokeWeight, zIndex})`로 **갱신**하고, 매번 새로 만들지 않는다. 마커 HTML(`icon.content`)은 프레임워크 밖에서 문자열로 생성한다(SDK가 직접 DOM을 관리하기 때문).

---

## 3. 스타일링·컴포넌트·타이포그래피

| 기술 | 무엇 | 지원 현황(2026) | 이 앱 적용 포인트 | 출처 |
|---|---|---|---|---|
| **Tailwind CSS v4.x** | CSS-first 설정(`@theme`), Oxide 엔진 | v4.2(2026-02-18), v4.3(2026-05 블로그, 스크롤바·logical 유틸), v4.3.3(2026-07) | 안 B에서 `@tailwindcss/vite`. `@theme`에 혼잡도 색(`--color-smooth` 등)을 토큰으로 정의. 안 A(no-build)에서는 Play CDN이 개발용이라 **비권장** | [Tailwind v4.3](https://tailwindcss.com/blog/tailwindcss-v4-3) |
| shadcn/ui (React) | 복사해 쓰는 컴포넌트 | **2026-07부터 Base UI가 기본**(Radix도 계속 지원) | React를 택할 때만 해당 | [shadcn changelog 2026-07](https://ui.shadcn.com/docs/changelog/2026-07-base-ui-default) |
| Base UI | Radix·Floating UI·MUI 출신이 만든 headless React | v1.0 (2025-12-11) | 위와 같음 | [shadcn/Base UI 비교](https://www.pkgpulse.com/guides/shadcn-ui-vs-base-ui-vs-radix-components-2026) **[2차 출처]** |
| shadcn-svelte / Bits UI / Melt UI | Svelte용 headless + 복사형 컴포넌트 | Svelte 5 대응 **[버전 미검증]** | 안 B에서 Combobox(자동완성), Tabs(경로 옵션), Collapsible(턴바이턴) 정도만 가져온다. 단, Dialog·Popover는 네이티브로 충분 | — |
| Ark UI | 프레임워크 무관(Zag 상태머신) headless | React/Vue/Solid/Svelte | Combobox 접근성이 필요할 때 대안 | — |
| Open Props | CSS 커스텀 프로퍼티 토큰 모음 | 안정(CDN 사용 가능) | 안 A에서 간격·그림자·이징 토큰을 빌려 쓸 수 있다 | — |
| 디자인 토큰(CSS custom properties) | 색·간격·타이포 변수 | — | 이미 `--smooth/--slow/--jam` 토큰이 있다. **원시 토큰 → 의미 토큰**(`--route-selected`, `--surface-1`, `--text-secondary`) 2계층으로 정리하고 `light-dark()`와 결합 | [KRDS 스타일](https://www.krds.go.kr/html/site/style/style_01.html) |
| **Pretendard Variable** | 한글 UI 표준처럼 쓰이는 가변 폰트 | v1.3.9, jsDelivr/cdnjs에 **variable dynamic subset** 제공(실측 2MB → ~306KB) | 1순위 서체. `<link>` 한 줄로 적용 | [Pretendard README](https://github.com/orioncactus/pretendard/blob/main/packages/pretendard/README.md) |
| SUIT Variable | 기하학적 UI 본문용 서체 | Variable woff2, OFL | 숫자와 라틴이 깔끔하다. 다만 **KS X 1001 2,350자 + 318자만 지원**해서 희귀 음절이 들어간 지명·상호가 대체 폰트로 깨질 수 있다 → 지명이 많은 이 앱엔 Pretendard가 안전 | [SUIT GitHub](https://github.com/sun-typeface/SUIT) |

### 고밀도 한국어 UI 가독성 가이드(이 앱 기준)

- **본문 크기**: KRDS는 본문 17px/400/행간 150%, 굵기는 400·700 두 가지만 쓴다([KRDS 스타일 요약](https://oh-my-design.kr/design-systems/krds), [KRDS](https://www.krds.go.kr/)). 지도 앱 패널은 밀도가 필요하므로 **본문 15px, 보조 13px, 핵심 수치(소요시간) 22–24px/700**을 권장한다. 지금의 13px 본문은 너무 작다.
- **숫자**: `font-variant-numeric: tabular-nums`로 카드끼리 시간·거리·요금 자릿수를 맞춘다. 단위(분·km·원)는 숫자보다 작고 옅게 표시한다.
- **줄바꿈**: 한국어 본문과 제목에 `word-break: keep-all`(어절 단위 줄바꿈)과 `overflow-wrap: anywhere`(긴 영문·URL 대비)를 함께 건다. `auto-phrase`는 사실상 일본어 전용이다([Chrome i18n CSS](https://developer.chrome.com/blog/css-i18n-features), [ryelle.codes 2025-04](https://ryelle.codes/2025/04/typography-troubles-balancing-in-japanese-korean/)).
- **위계는 3단계까지만**: 소요시간 > 경로 요약(경유 도로·거리·요금) > 메타(신호 수·혼잡 비율). 색은 혼잡도 의미에만 쓰고 장식에는 쓰지 않는다.
- **색 대비**: 혼잡도 색(초록/주황/빨강)만으로 정보를 전달하지 않는다(WCAG 1.4.1). 텍스트 라벨("서행 2.1km")이나 패턴을 함께 표시한다. 주황 `#ffa000` 위의 흰 글자는 대비가 부족하다.

---

## 4. 지도 앱 UX 패턴

| 패턴 | 무엇 | 레퍼런스(2025–2026) | 이 앱 적용 포인트 | 출처 |
|---|---|---|---|---|
| 접이식 좌측 패널(데스크톱) | 패널 + 지도 전체 화면 토글, 패널 폭 조절 | 네이버 지도 웹, Google Maps 웹(패널 접기 버튼) | `#side`에 접기 버튼을 달고 접힌 상태에서는 요약 칩만 띄운다. 접힘 상태는 `:has()`/container query로 처리 | 관찰 기반 **[미검증]** |
| 바텀시트(모바일) | peek/half/full 3단 snap, 지도는 계속 보임 | Google/Apple/네이버/카카오 앱 공통 | `scroll-snap` 기반 시트. **NN/g 주의점**: 시트 위에 시트를 겹치지 말 것, 긴 콘텐츠를 넣지 말 것, "하단이 엄지에 닿기 쉽다"는 통념은 과장이다 | [NN/g Bottom Sheets](https://www.nngroup.com/articles/bottom-sheet/) |
| 경로 비교 카드 + 트레이드오프 설명 | 대안 경로를 "더 길지만 덜 막힘 / 더 빠르지만 유료"로 설명 | **Google Maps Immersive Navigation(2026-03-12)**: 대안 경로의 트레이드오프를 알려줌. 차로·횡단보도·신호를 상황에 따라 강조 | 카드마다 **최적 경로 대비 차이 칩**("+6분", "통행료 0원", "혼잡 1.2km 적음")을 붙인다. 별도의 "비교" 화면에 가기 전에 카드만 보고 판단할 수 있게 한다 | [Google Blog 2026-03-12](https://blog.google/products-and-platforms/products/maps/ask-maps-immersive-navigation/) |
| 지도–목록 동기화 | 카드 hover/focus 시 폴리라인 강조, 폴리라인 클릭 시 카드 선택 | 공통 | 이미 미선택 경로를 `--dim`으로 처리하고 있다. hover와 키보드 focus에도 같은 강조를 적용하고, 폴리라인 hit 영역을 넓힌다(투명한 두꺼운 라인을 겹침) | — |
| 턴바이턴 리스트 | 단계 클릭 시 지도 이동 + 로드뷰 | 네이버·카카오 웹 길찾기 | 현재 구조를 유지하고, 단계 아이콘·거리·도로명을 3열 그리드로 정렬한다. 긴 경로는 "고속도로 구간 23개 단계"처럼 묶어서 접어 둔다(progressive disclosure) | — |
| 점진적 공개 | 기본 = 요약, 펼치면 상세 | 공통 | 1단계 카드(시간·요약·차이 칩) → 2단계 상세(턴바이턴) → 3단계 비교 표/AI 서술 | [NN/g](https://www.nngroup.com/articles/bottom-sheet/) |
| AI 질의형 탐색 | 자연어로 장소·경로 질문 | Google **Ask Maps**(Gemini, 2026-03, 미국·인도), 네이버 지도 AI Search(10년 만의 리브랜딩), 카카오맵 'AI메이트 로컬', 카카오내비 대화형 AI 에이전트(2026-04), TMAP '어디갈까' AI 개편(2026-09-21) | 이 앱의 핵심은 "경로 비교"이므로 **챗 UI를 추가하지 않는다**. AI는 비교 서술과 위험 지점 설명이라는 보조 역할에 둔다 | [Google Blog](https://blog.google/products-and-platforms/products/maps/ask-maps-immersive-navigation/), [이데일리 네이버 지도 개편](https://edaily.co.kr/News/Read?mediaCodeNo=257&newsId=01590806599426912), [카카오 AI메이트 로컬](https://www.kakaocorp.com/page/detail/11619), [네이트 카카오내비 AI](https://m.news.nate.com/view/20260426n02578), [ZDNet 티맵 2026-09-21](https://zdnet.co.kr/view/?no=20260921085646) |
| 웹 지도 서비스 | 브라우저용 경로 탐색 | Apple Maps 웹 정식 버전(2025-04, 모바일 브라우저 지원, Look Around 추가) | 웹에서도 "검색 → 장소 카드 → 경로" 3단계가 표준이다 | [9to5Mac 2025-04-11](https://9to5mac.com/2025/04/11/apple-maps-web-mobile/) |

### 레퍼런스 앱 패턴 정리

- **네이버 지도**(2025 리브랜딩): 하단 탭을 '발견-예약-대중교통-내비게이션-저장'으로 재편하고 AI Search를 추가했다. 실내 AR 내비게이션도 출시. 길찾기 결과는 경로 카드 목록 → 상세 단계 구조이며 혼잡도 색 폴리라인을 쓴다. → 이 앱의 시각 언어(혼잡도 색)는 사용자에게 이미 익숙하므로 **유지**한다. ([디자인 나침반 2025-11](https://designcompass.org/2025/11/12/naver-map-logo-transformed-into-3d-after-10-years/), [이데일리](https://edaily.co.kr/News/Read?mediaCodeNo=257&newsId=01590806599426912))
- **카카오맵**: AI 장소 추천(검색창 아래 'AI맛집' 버튼처럼 **보조 진입점**으로 배치), 미래 운행 정보(출발 시각별 예상 소요). → 이 앱에 "출발 시각 변경" 기능을 넣는다면 카드 상단의 작은 칩으로 둔다. ([카카오](https://www.kakaocorp.com/page/detail/11619), [카카오 미래 운행 정보](https://www.kakaocorp.com/page/detail/8467))
- **Google Maps**: 대안 경로의 트레이드오프를 문장으로 설명하고 위험·공사·사고를 실시간 경고한다. → 이 앱의 "LLM 서술 + 위험 지점"과 같은 방향이다. 다만 Google은 **한 줄 요약을 기본으로 보여준다**.
- **Apple Maps 웹**: 군더더기 없는 패널, 장소 카드 중심. 3D·대중교통 지도는 웹에서 빠졌다. → 최소주의 패널의 참고 사례.
- **TMAP**: 2026-09 AI 장소추천 개편, 2027 상반기 지도 전면 개편(보행자 중심) 예고. 웹 길찾기 개편 정보는 찾지 못함 **[미확인]**.

### 이 앱에 권장하는 화면 구성(동적)

```
[데스크톱 ≥ 960px]
┌ 패널(360px, 접기 가능) ─────────┐┌ 지도 ──────────────────────────┐
│ 출발/경유/도착 (compact 모드 전환) ││  선택 경로 굵게 + 나머지 dim      │
│ ─ 상태 A: 경로 카드 ×3            ││  hover 카드 ↔ 폴리라인 강조       │
│    시간(대) · 차이칩 · 요약        ││  위험 지점 핀(비교 후)            │
│    [비교] (dialog 또는 패널 확장)  ││  로드뷰: 지도 위 floating 카드    │
│ ─ 상태 B: 상세(턴바이턴)  ← VT 전환 ││                                 │
│ ─ 상태 C: 비교(표 → AI 서술 스트림)││                                 │
└─────────────────────────────────┘└─────────────────────────────────┘
[모바일 < 960px] 지도 전체 + 바텀시트(peek: 입력 요약·선택 경로 / half: 카드 / full: 상세·비교)
```

- 화면 상태는 하나의 상태 머신(`search | results | detail | compare`)으로 관리하고 URL(Navigation API)과 동기화한다.
- 입력 영역은 결과가 나온 뒤 **한 줄 요약("판교역 → 강남역 · 경유 1")으로 접어서** 세로 공간을 카드에 준다.

---

## 5. 느린 AI/LLM 콘텐츠 UX

| 기술/패턴 | 무엇 | 현황(2026) | 이 앱 적용 포인트 | 출처 |
|---|---|---|---|---|
| 분리 응답(Split response) | 빠른 결정적 데이터와 느린 생성 데이터를 따로 보낸다 | 일반 원칙 | `/api/compare` → `/api/compare`(표·위험 지점, 즉시) + `/api/compare/narrative`(스트림). 사용자는 표를 즉시 보고, 서술은 뒤따라 채워진다 | [ai-tldr: Designing for LLM latency](https://ai-tldr.dev/learn/building-ai-apps/ai-ux-patterns/designing-for-llm-latency/) |
| SSE / fetch streaming | 토큰 단위 전송 | 모든 브라우저 지원. `EventSource`(GET) 또는 `fetch` + `ReadableStream` + `TextDecoderStream` | `serve.py`(ThreadingHTTPServer)에서 `Content-Type: text/event-stream`, 줄마다 `flush`. 백엔드는 `claude -p --output-format stream-json --verbose --include-partial-messages`의 `text_delta`를 그대로 전달 | [Claude Code headless 문서](https://code.claude.com/docs/en/headless) |
| 구조화 스켈레톤 | 결과의 모양(문단 3개 + 위험 지점 리스트)을 미리 그린다 | 권장 패턴 | 비교 서술 영역에 "경로별 한 줄 평 ×3 + 종합 추천" 모양의 스켈레톤을 둔다. 스켈레톤 높이를 맞춰 **CLS 방지** | [AYDesign streaming patterns 2026](https://www.aydesign.ai/blog/ai-streaming-response-ui-patterns-2026) |
| 단계형 진행 표시 | "위험 데이터 조회 중 → 경로 분석 중 → 작성 중" | 권장 패턴 | 서버가 `event: phase` SSE를 보낸다. 경과 시간(초)도 함께 표시. 수십 초짜리 작업에는 불확정 스피너보다 단계 표시가 낫다 | [UX Tigers: Think-time UX](https://www.uxtigers.com/post/think-time-ux) |
| 중단·재시도·캐시 표시 | 사용자가 멈출 수 있음, 캐시 적중을 알림 | 권장 패턴 | `AbortController`로 "중단"하고 서버에서 subprocess를 종료한다. 이미 있는 `_compare_cache`에 적중하면 "저장된 분석 · 3분 전"이라고 표시 | [ai-tldr: chatbot UX](https://ai-tldr.dev/learn/building-ai-apps/ai-ux-patterns/chatbot-ux-patterns/) |
| 근거 인라인 인용 | 생성 문장에 근거 데이터 연결 | 권장 패턴 | 서술 속 "OO교차로 정체"를 클릭 가능한 칩으로 만들어 지도의 해당 위험 지점/구간으로 이동시킨다. 구현은 LLM 출력에 `[[hazard:3]]` 같은 토큰을 지정하고 클라이언트가 칩으로 치환(이미 `--json-schema`를 쓰므로 스키마에 `refs` 필드를 추가하는 방식도 가능) | — |
| Optimistic UI | 서버 응답 전에 결과를 가정해 표시 | 일반 원칙 | 경로 선택·패널 전환 같은 **로컬 상태에만** 적용. LLM 결과는 가정하지 않는다 | — |
| Generative UI (A2UI, AG-UI, MCP Apps) | LLM이 UI 구성 선언을 생성하면 클라이언트가 렌더링 | A2UI v0.9(2026-07, Google), AG-UI 프로토콜 | **이 앱에는 부적합.** 화면 종류가 적고 고정적이며, LLM 지연(수십 초)이 UI 구성 지연으로 이어진다. 대신 "LLM이 강조할 경로·구간 id를 구조화 출력으로 반환하고 → 기존 컴포넌트가 강조"하는 **제한된 적응형 UI**가 적당하다 | [Google A2UI v0.9](https://developers.googleblog.com/a2ui-v0-9-generative-ui/), [InfoQ 2026-07](https://www.infoq.com/news/2026/07/google-a2ui-genui/) |

---

## 6. 접근성·성능 기준선

| 기준 | 무엇 | 현황 | 이 앱 적용 포인트 | 출처 |
|---|---|---|---|---|
| WCAG 2.2 AA – 2.5.8 Target Size(Min) | 포인터 타깃 24×24 CSS px 이상 | W3C 권고 | 경유지 삭제 ×, 카드 "⋯", 지도 컨트롤. 모바일은 44px 권장 | [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/) |
| WCAG 2.2 – 2.4.11 Focus Not Obscured | 포커스된 요소가 다른 UI에 완전히 가려지지 않을 것 | W3C 권고 | **바텀시트·sticky 헤더가 포커스를 가리지 않게** `scroll-padding` 설정 | [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/), [TetraLogical](https://tetralogical.com/blog/2023/10/05/whats-new-wcag-2.2/) |
| WCAG 2.2 – 2.5.7 Dragging Movements | 드래그 대신 쓸 수 있는 단일 포인터 대안 | W3C 권고 | 바텀시트 드래그 → 핸들 탭/버튼으로 단계 전환. 지도 팬 → 카드 클릭으로 이동 | [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/) |
| WCAG 1.4.1 색 사용 | 색만으로 정보 전달 금지 | — | 혼잡도는 색 + 텍스트 라벨/범례 | — |
| ARIA live region | 동적 결과 안내 | — | "경로 3개를 찾았습니다", 스트리밍 서술은 완료 시 1회만 안내(`aria-busy`로 토큰마다 낭독되는 것 방지) | — |
| `prefers-reduced-motion` | 모션 축소 설정 존중 | 전 브라우저 지원 | View Transition, 지도 `panTo` 애니메이션, 스켈레톤 shimmer를 끈다(`morph:false`/즉시 `setCenter`) | MDN |
| INP ≤ 200ms (p75) | 상호작용 응답성 | Core Web Vitals 안정 지표 | 자동완성 입력은 디바운스 + `AbortController`(이미 있음). 카드 hover 시 폴리라인 3개만 갱신하고, 전체 재렌더링 금지. 긴 경로 폴리라인 재생성은 `scheduler.yield()`/rAF로 분할 | [web.dev Web Vitals](https://web.dev/articles/vitals) |
| CLS | 레이아웃 이동 | — | 스켈레톤 고정 높이, 웹폰트 `font-display: swap` + 동적 서브셋 | — |

---

## 리스크 / 주의점

1. **View Transitions와 라이브 지도**: 전환하는 동안 페이지가 스냅샷으로 렌더링되어 지도 상호작용이 잠깐 멈추고, 지도 캔버스 스냅샷이 어긋나 보일 수 있다. `view-transition-name`은 패널 내부 요소에만 주고, 루트 전환은 `::view-transition-group(root){animation:none}`으로 끄는 것을 권장한다 **[실측 필요]**.
2. **Shadow DOM과 NCP SDK**: Web Components로 감쌀 때 지도를 shadow root 안에 넣으면 SDK의 스타일과 이벤트 처리가 깨질 수 있다 **[미검증]**. 지도 컨테이너는 light DOM에 둔다.
3. **프레임워크 재렌더링과 SDK 오버레이**: 반응형 루프 안에서 `new naver.maps.Polyline`을 반복 생성하면 메모리 누수가 생기고 깜빡인다. 생성/파괴는 id 키 기반으로 diff하고, 스타일은 `setOptions`로만 바꾼다. React StrictMode의 effect 이중 실행에 주의한다.
4. **Baseline 데이터 상충**: anchor positioning과 scroll-driven animations는 블로그 글과 web-features 데이터가 서로 다르다. 적용 전에 대상 브라우저(사용자 본인의 Chrome/Safari)에서 직접 확인하고 `@supports`로 감싼다.
5. **SUIT 글리프 커버리지**(2,350+318자): 희귀 음절이 들어간 지명이 대체 폰트로 표시될 수 있다 → Pretendard 권장.
6. **no-build에서 CDN 의존**: import map으로 Preact 등을 CDN에서 받으면 오프라인 데모가 깨진다. `web/vendor/`에 ESM 파일을 넣어두는 것을 고려한다.
7. **스트리밍과 stdlib 서버**: `http.server`에서 SSE를 쓰려면 `ThreadingHTTPServer`, 응답 버퍼 flush, 클라이언트가 끊었을 때 `claude` subprocess 종료 처리(BrokenPipe)가 필요하다. `--json-schema`(구조화 출력)와 토큰 스트리밍을 동시에 쓸 수 있는지는 **[미검증]**. 서술은 자유 텍스트 스트림, 위험 지점과 강조 id는 별도 구조화 호출이나 후처리로 분리하는 편이 안전하다.
8. **버전 관련 미검증 항목**: Preact 11 정식 출시일, Vue 3.6 일정, shadcn-svelte/Bits UI 버전, 네이버·카카오 **웹** 길찾기 화면 상세(앱 개편 기사 위주로만 확인됨).
9. **과잉 설계 경계**: Generative UI, 챗 UI, 다크 모드, 3D는 "핵심 기능에 집중"이라는 목표와 충돌한다. 1차 개편 범위에서 제외한다.

---

## 주요 출처 목록

- Baseline/브라우저: [web.dev Interop 2026 (2026-02-12)](https://web.dev/blog/interop-2026) · [web.dev 2026-01](https://web.dev/blog/web-platform-01-2026) · [web.dev 2026-06](https://web.dev/blog/web-platform-06-2026) · [web.dev Navigation API Baseline](https://web.dev/blog/baseline-navigation-api?hl=en) · [web-features explorer](https://web-platform-dx.github.io/web-features-explorer/) · [caniuse anchor positioning](https://caniuse.com/css-anchor-positioning) · [WebKit Interop 2026](https://webkit.org/blog/17818/announcing-interop-2026/) · [Mozilla Interop 2026](https://hacks.mozilla.org/2026/02/launching-interop-2026/)
- 프레임워크/툴: [Vite 8](https://vite.dev/blog/announcing-vite8) · [React Compiler 1.0](https://react.dev/blog/2025/10/07/react-compiler-1) · [Svelte attachments](https://svelte.dev/docs/svelte/svelte-attachments) · [Svelte 2026-06](https://svelte.dev/blog/whats-new-in-svelte-june-2026) · [htmx 4 (InfoQ)](https://www.infoq.com/news/2026/09/htmx-4-released/) · [Solid 2.0 (InfoQ)](https://www.infoq.com/news/2026/05/solidjs-2-async/) · [Tailwind v4.3](https://tailwindcss.com/blog/tailwindcss-v4-3) · [shadcn Base UI 기본화](https://ui.shadcn.com/docs/changelog/2026-07-base-ui-default)
- 타이포: [Pretendard](https://github.com/orioncactus/pretendard/blob/main/packages/pretendard/README.md) · [SUIT](https://github.com/sun-typeface/SUIT) · [KRDS](https://www.krds.go.kr/html/site/style/style_01.html) · [Chrome CSS i18n](https://developer.chrome.com/blog/css-i18n-features)
- 지도 UX: [Google Maps Ask Maps/Immersive Nav (2026-03-12)](https://blog.google/products-and-platforms/products/maps/ask-maps-immersive-navigation/) · [NN/g Bottom Sheets](https://www.nngroup.com/articles/bottom-sheet/) · [Apple Maps 웹 (9to5Mac 2025-04)](https://9to5mac.com/2025/04/11/apple-maps-web-mobile/) · [네이버 지도 개편 (이데일리)](https://edaily.co.kr/News/Read?mediaCodeNo=257&newsId=01590806599426912) · [카카오 AI메이트 로컬](https://www.kakaocorp.com/page/detail/11619) · [티맵 (ZDNet 2026-09-21)](https://zdnet.co.kr/view/?no=20260921085646)
- AI UX: [Claude Code headless/stream-json](https://code.claude.com/docs/en/headless) · [A2UI v0.9](https://developers.googleblog.com/a2ui-v0-9-generative-ui/) · [UX Tigers think-time UX](https://www.uxtigers.com/post/think-time-ux) · [ai-tldr latency patterns](https://ai-tldr.dev/learn/building-ai-apps/ai-ux-patterns/designing-for-llm-latency/)
- 접근성/성능: [WCAG 2.2](https://www.w3.org/TR/WCAG22/) · [web.dev Web Vitals](https://web.dev/articles/vitals)
