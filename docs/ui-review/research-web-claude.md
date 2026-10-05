# 지도 길찾기 웹앱 UI 개선 — 최신 웹 기술·UX 조사 (2025\~2026)

Oct 2, 2026

## TL;DR

1. **프레임워크보다 브라우저 기본 기능이 먼저입니다.** Popover, `<dialog>`, Invoker Commands, Container Queries, `:has()`, `@starting-style`, `@scope`, 같은 문서 View Transitions가 2026년 기준 모든 주요 브라우저에서 동작해, 패널·드롭다운·전환 JS 상당 부분을 지울 수 있습니다.
2. **빌드 없이 시작하는 (A)안을 먼저, 상태 관리가 버거워지면 Preact + Signals로 옮기는 순서**를 권합니다. Preact는 빌드 없이도 쓸 수 있어 (A)→(B)가 끊기지 않습니다.
3. **화면은 "지도 전체 + 접이식 패널(데스크톱) / 3단 바텀시트(모바일)"**, 카드엔 시간·거리·요금만 두고 나머지는 펼칠 때 보여줍니다. 카드 hover ↔ 폴리라인 강조로 목록과 지도를 묶습니다.
4. **느린 AI 서술은 나눠서 보여줍니다.** 비교표·위험 지점은 즉시, 서술만 fetch 스트리밍으로 흘리고, 수치는 모델이 아니라 API 값을 근거 칩으로 붙입니다. AI가 UI를 만드는 generative UI는 더 느리고 불안정해 이 앱엔 맞지 않습니다.
5. **기준선은 WCAG 2.2 AA + INP 200ms**, 한글 본문 16\~17px·행간 150% 이상·`keep-all`·숫자 고정폭입니다.

## 추천 스택 2안

1인 데모라는 점을 고려하면 **(A)로 시작하고, 상태가 얽히기 시작하면 (B)로 넘어가는 것**이 가장 균형 잡힌 길입니다. 작업량은 지금 기능(약 1,500줄)을 1인이 옮긴다는 가정의 대략적 추정이며, 출처가 있는 수치가 아닙니다.

|  | (A) 최소 변경안 — 빌드 없음 | (B) 본격 전환안 — 프레임워크 도입 |
| --- | --- | --- |
| 구성 | 바닐라 JS를 ES 모듈 몇 개로 분리(`map.js`, `routes.js`, `compare.js`) + 네이티브 기능(Popover, `<dialog>`, Invoker Commands, Container Queries, `:has()`, `@starting-style`, `@scope`, View Transitions) + Open Props 또는 직접 만든 CSS 변수 + Pretendard 동적 서브셋 + fetch 스트리밍 | Vite 8 + Preact(10.x 고정 권장) + @preact/signals + 스타일은 CSS Modules 또는 Tailwind v4. 대안: Svelte 5(지도 궁합 최고, 대신 학습 비용) |
| Python 서버 | 그대로 + 스트리밍 엔드포인트 1개 추가 | 그대로(API 서버 역할). 개발 중엔 Vite 프록시 |
| 예상 작업량(추정) | 3\~5일 | 1.5\~3주 |
| 좋은 점 | 빌드·의존성 0, 지금 코드 대부분 재사용, 브라우저가 접근성(Esc·포커스 복귀·바깥 클릭) 상당 부분 처리 | 상태(입력값·선택 경로·AI 진행)가 한곳에 모여 화면 갱신 버그가 줄어듦, 컴포넌트 재사용, 타입스크립트·테스트 도입 쉬움 |
| 나쁜 점 | innerHTML 문자열 템플릿이 남으면 상태 동기화 버그는 그대로, XSS 주의 필요 | 빌드 파이프라인 관리, 학습 비용, 지도 인스턴스 생명주기(만들기·정리)를 프레임워크 규칙에 맞춰야 함 |
| 중간 단계 | Preact + htm을 import map으로 불러와 경로 카드 하나만 먼저 옮겨보기 → 이게 (B)로 가는 다리 | — |

**넘어갈 신호.** 한 사용자 동작(예: 경유지 추가)이 카드·지도·비교표 세 곳을 손으로 갱신하게 만들고, 그 갱신 순서 때문에 버그가 생기기 시작하면 (B)로 갈 때입니다.

## 1. 네이티브 웹 플랫폼 기능

지금 바로 쓸 수 있는 것은 Popover, `<dialog>`, Invoker Commands, Container Queries, `:has()`, `@starting-style`, Nesting, `@scope`, `light-dark()`, 같은 문서 View Transitions입니다. 이것만으로 패널 열고 닫기·자동완성 드롭다운·카드 전환 JS 상당 부분을 지울 수 있습니다. Firefox나 Safari가 빠진 기능(Limited)은 "있으면 더 좋은" 장식으로만 쓰고, 핵심 동작을 맡기지 마세요.

기준 브라우저: Chrome 154, Firefox 157, Safari 27 (2026년 9월 말). 지원 값은 공식 Baseline 데이터셋 [web-features v3.40.1](https://www.npmjs.com/package/web-features) (2026-10-01)과 [MDN browser-compat-data v8.1.4](https://www.npmjs.com/package/@mdn/browser-compat-data) (2026-10-01)에서 조회했습니다. 아래 webstatus.dev 링크는 같은 데이터를 보여주는 공식 페이지이며, 조사 중 프록시 때문에 페이지 자체는 직접 열지 못했습니다.

라벨: **Widely** = 2.5년 이상 모든 주요 브라우저 지원 · **Newly** = 모든 주요 브라우저가 막 지원(괄호 = 그 날짜) · **Limited** = 아직 일부만.

| 기술 | 무엇인가 | 지원 현황(2026) | 이 앱 적용 포인트 | 출처 |
| --- | --- | --- | --- | --- |
| View Transitions (같은 문서) | 화면 상태가 바뀔 때 자동 전환 애니메이션 | Chrome 111 / FF 144 / Safari 18 — **Newly (2025-10-14)** | 경로 카드 선택 → 상세 턴바이턴으로 펼칠 때, 비교 화면 전환. 미지원 시 그냥 즉시 바뀜(안전) | [webstatus.dev](https://webstatus.dev/features/view-transitions) (2026-10-01) |
| View Transitions (문서 간) | 페이지 이동(MPA) 전환 | Chrome 126 / Safari 18.2 / FF 미지원 — **Limited** | 단일 페이지 앱이라 불필요 | [webstatus.dev](https://webstatus.dev/features/cross-document-view-transitions) (2026-10-01) |
| Popover API | `popover` 속성만으로 위에 뜨는 레이어, 바깥 클릭·Esc 닫기 내장 | Chrome 116 / FF 125 / Safari 17 — **Newly (2025-01-27)** | 장소 자동완성 목록, 경로 옵션 메뉴, 지도 레이어 토글 메뉴 | [webstatus.dev](https://webstatus.dev/features/popover) (2026-10-01) |
| `popover="hint"` | 다른 팝오버를 닫지 않는 툴팁 | Chrome 151 / FF 153 / Safari 미출시 — **Limited** | 위험 지점 아이콘 툴팁. 지금은 `auto`로 대체 | [webstatus.dev](https://webstatus.dev/features/popover-hint) (2026-10-01) |
| CSS Anchor Positioning | 다른 요소 옆에 붙여 배치 | 핵심: Chrome 125 / FF 147 / Safari 26. 세부 속성 일부가 Safari만 있어 전체는 **Limited** | 자동완성 목록을 입력칸 바로 아래, 툴팁을 버튼 옆에 — 위치 계산 JS 제거. `position-try` 폴백은 실기기 확인 필요 | [webstatus.dev](https://webstatus.dev/features/anchor-positioning) (2026-10-01) |
| `<dialog>` | 기본 모달 | Chrome 37 / FF 98 / Safari 15.4 — **Widely (2024-09-14)** | 설정, 경로 비교 전체 보기, 오류 알림 | [webstatus.dev](https://webstatus.dev/features/dialog) (2026-10-01) |
| `closedby` | 바깥 클릭 등 닫기 방식 지정 | Chrome 134 / FF 141 / Safari 미출시 — **Limited** | 써도 되지만 Safari용 닫기 버튼은 필수 | [webstatus.dev](https://webstatus.dev/features/dialog-closedby) (2026-10-01) |
| Invoker Commands (`command`/`commandfor`) | JS 없이 버튼이 dialog·popover를 열고 닫음 | Chrome 135 / FF 144 / Safari 26.2 — **Newly (2025-12-12)** | 패널 열기·닫기 버튼의 onclick 제거 | [webstatus.dev](https://webstatus.dev/features/invoker-commands) (2026-10-01) |
| Container Queries (크기) | 부모 박스 크기에 따라 스타일 변경 | Chrome 105 / FF 110 / Safari 16 — **Widely (2025-08-14)** | 사이드 패널 폭이 좁을 때 경로 카드를 한 줄 요약으로 접기. 바텀시트·사이드패널에서 같은 카드 재사용 | [webstatus.dev](https://webstatus.dev/features/container-queries) (2026-10-01) |
| Container style queries | 부모의 CSS 변수 값으로 스타일 분기 | Chrome 111 / FF 151 / Safari 18 — **Newly (2026-05-19)** | `--congestion: heavy` 같은 값으로 카드 강조색 바꾸기 | [webstatus.dev](https://webstatus.dev/features/container-style-queries) (2026-10-01) |
| Scroll-state queries | 붙음(stuck)·스냅 상태로 스타일 변경 | Chrome 133만 — **Limited** | 쓰지 않기 | [webstatus.dev](https://webstatus.dev/features/container-scroll-state-queries) (2026-10-01) |
| `:has()` | 자식 상태로 부모 선택 | Chrome 105 / FF 121 / Safari 15.4 — **Widely (2026-06-19)** | `.panel:has(.route-card[aria-selected=true])`로 선택 상태 레이아웃, 경유지 입력이 있을 때만 순서 버튼 표시 | [webstatus.dev](https://webstatus.dev/features/has) (2026-10-01) |
| Scroll-driven Animations | 스크롤 위치로 애니메이션 진행 | Chrome 115 / Safari 26 / FF 미출시 — **Limited** | 바텀시트 드래그 시 헤더 그림자 정도의 장식만 | [webstatus.dev](https://webstatus.dev/features/scroll-driven-animations) (2026-10-01) |
| `@starting-style` + `allow-discrete` | 등장·퇴장 애니메이션(`display` 전환 포함) | Chrome 117 / FF 129 / Safari 17.4\~17.5 — **Newly (2024-08-06)** | 팝오버·dialog·토스트가 부드럽게 나타나고 사라지게 | [webstatus.dev](https://webstatus.dev/features/starting-style) (2026-10-01) |
| `interpolate-size` / `calc-size()` | `height: auto`까지 애니메이션 | Chrome 129만 — **Limited** | 턴바이턴 펼침에 써도 되지만 다른 브라우저는 즉시 펼쳐짐. 대안: `grid-template-rows: 0fr → 1fr` | [webstatus.dev](https://webstatus.dev/features/interpolate-size) (2026-10-01) |
| 커스터마이즈 `<select>` (`appearance: base-select`) | select를 CSS로 자유롭게 | Chrome 135 / Safari 27 / FF 플래그 — **Limited** | 경로 옵션(최단·무료·고속도로 회피) 선택. FF에선 기본 select로 보여도 동작은 같음 → 점진적 향상으로 사용 가능 | [webstatus.dev](https://webstatus.dev/features/customizable-select) (2026-10-01) |
| CSS Nesting | CSS 중첩 | Chrome 120 / FF 117 / Safari 17.2 — **Widely (2026-06-11)** | 인라인 CSS를 컴포넌트별로 묶어 정리 | [webstatus.dev](https://webstatus.dev/features/nesting) (2026-10-01) |
| `@scope` | 스타일 적용 범위를 DOM 일부로 제한 | Chrome 143 / FF 146 / Safari 26.4 — **Newly (2026-03-24)** | 빌드 없이 카드·패널 스타일 충돌 방지(CSS Modules 대용) | [webstatus.dev](https://webstatus.dev/features/scope) (2026-10-01) |
| `light-dark()` | 라이트/다크 색을 한 줄로 | Chrome 123 / FF 120 / Safari 17.5 — **Newly (2024-05-13)** | 다크 모드 패널. 지도 타일 자체는 NCP 스타일에 따름(별도 확인) | [webstatus.dev](https://webstatus.dev/features/light-dark) (2026-10-01) |
| `field-sizing: content` | 입력칸이 내용 길이에 맞춰 늘어남 | Chrome 123 / FF 152 / Safari 26.2 — **Newly (2026-06-16)** | 긴 장소명 입력칸 | [webstatus.dev](https://webstatus.dev/features/field-sizing) (2026-10-01) |
| Navigation API | SPA 라우팅용 탐색 API | Chrome 102 / FF 147 / Safari 26.2 — **Newly (2026-01-13)** | 뒤로 가기로 "상세 → 목록 → 검색" 단계 되돌리기, URL에 출발·도착 상태 저장 | [webstatus.dev](https://webstatus.dev/features/navigation) (2026-10-01) |
| `text-wrap: balance` | 제목 줄 길이 고르게 | Chrome 114 / FF 121 / Safari 17.5 — **Newly (2024-05-13)** | 카드 제목, 경고 문구 | [webstatus.dev](https://webstatus.dev/features/text-wrap-balance) (2026-10-01) |
| `content-visibility` | 화면 밖 렌더링 지연 | Chrome 108 / FF 130 / Safari 26 — **Newly (2025-09-15)** | 수백 줄 턴바이턴 목록 렌더링 비용 절감 | [webstatus.dev](https://webstatus.dev/features/content-visibility) (2026-10-01) |
| `@property` | 타입 있는 CSS 변수(애니메이션 가능) | Chrome 85 / FF 128 / Safari 16.4 — **Newly (2024-07-09)** | 진행 표시 링, 혼잡도 색 전환 | [webstatus.dev](https://webstatus.dev/features/registered-custom-properties) (2026-10-01) |
| CSS `if()` | CSS 값 안 조건 분기 | Chrome 137만 — **Limited** | 쓰지 않기 | [webstatus.dev](https://webstatus.dev/features/if) (2026-10-01) |

## 2. 프레임워크 선택지

추천은 **Preact + Signals**(1순위)와 **Vue 3.5**(2순위)입니다. 둘 다 빌드 없이 `<script type="importmap">`으로 시작할 수 있고, 나중에 Vite를 붙여도 코드를 거의 그대로 가져갈 수 있습니다. 지도처럼 명령형 SDK는 "한 번 만들고, 이후엔 메서드만 호출"하는 패턴이 공식 문서에 나와 있어 궁합도 좋습니다.

버전·날짜는 npm 레지스트리(dist-tags, time) 조회 기준이고, 크기는 npm 패키지를 직접 gzip해서 잰 근사치입니다.

| 선택지 | 최신 버전(날짜) | 빌드 없이 | 런타임(gz) | 학습 비용 | 단일 HTML에서 옮기기 | 지도 SDK 궁합 | 출처 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Preact + @preact/signals** | preact 11.0.0 (2026-09-30, 6년 만의 메이저) / signals 2.11.3 (2026-09-30) | 가능 — 공식 무빌드 가이드(import map + htm) | 약 8.7KB | 낮음\~중간(React 문법) | 중간 — htm 템플릿이 지금의 문자열 템플릿과 비슷 | 좋음 — ref + effect, React 공식 MapWidget 예제와 동일 패턴 | [Preact 11 블로그](https://preactjs.com/blog/preact-11) (2026-09-30), [No-Build Workflows](https://preactjs.com/guide/v10/no-build-workflows) |
| **Vue 3.5 / 3.6** | 3.5.43 (2026-09-17). 3.6(Vapor mode 포함)은 rc.10 (2026-09-30), 안정판 미출시 | 가능 — 공식 Quick Start에 CDN·import map 방식. SFC는 불가 | 약 61KB(템플릿 컴파일러 포함) / 41KB(런타임만) | 낮음\~중간 | 쉬움\~중간 — 기존 HTML을 템플릿으로 거의 그대로 | 좋음 — 템플릿 ref + `onMounted`, 문서가 서드파티 라이브러리 초기화 용도로 명시 | [Quick Start](https://vuejs.org/guide/quick-start.html), [Template Refs](https://vuejs.org/guide/essentials/template-refs.html), [릴리스](https://github.com/vuejs/core/releases) |
| **Svelte 5 / SvelteKit** | svelte 5.57.1 (2026-09-18) / SvelteKit 3.0.0 (2026-10-01) | 불가(컴파일러 필수) | 컴포넌트별로 다름, 공식 수치 미확인 | 중간(runes) | 높음 — 빌드 + 컴포넌트 분리 | 매우 좋음 — `{@attach}`(5.29+)가 마운트·정리·재실행을 한 곳에서 처리 | [SvelteKit 3](https://svelte.dev/blog/sveltekit-3-is-here) (2026-10-01), [@attach](https://svelte.dev/docs/svelte/@attach) |
| **Lit** | 3.3.3 (2026-05-14) | CDN ESM으로 동작은 함. 공식 문서는 bare import 해석 도구 필요라고 안내 | 약 6.2KB | 낮음\~중간 | 중간 | 좋음 — `firstUpdated()`에서 지도 1회 생성 | [Lifecycle](https://lit.dev/docs/components/lifecycle/), [Requirements](https://lit.dev/docs/tools/requirements/) |
| **Alpine.js** | 3.17.4 (2026-09-21) | 가능 | 약 19.9KB | 매우 낮음 | 쉬움 — 속성만 추가 | 보통 — 지도 영역에 `x-ignore` | [x-ignore](https://alpinejs.dev/directives/ignore) |
| **htmx** | 2.0.11 (2026-09-22). 4.0.0 출시(2026-08-28, npm `next` 태그) | 가능 | 약 13\~17KB | 낮음 | 부적합 — 서버가 HTML 조각을 돌려주도록 Python 서버를 다시 짜야 함 | 보통 — 지도는 htmx 바깥 | [InfoQ](https://www.infoq.com/news/2026/09/htmx-4-released/) (2026-09) |
| **SolidJS** | 1.9.15 (2026-08-17). 2.0은 RC(rc.13, 2026-09-30), 안정판 날짜 미확인 | 부분 — `solid-js/html`은 공식 README가 JSX보다 비효율이라고 명시 | 약 12.3KB | 중간 | 중간\~높음 | 좋음 | [InfoQ](https://www.infoq.com/news/2026/05/solidjs-2-async/) (2026-05) |
| **React 19 + Compiler** | react 19.3.0 (2026-09-09). Compiler 1.0 안정판 2025-10-07 | 사실상 불가(JSX·Compiler 모두 빌드, UMD 빌드 없음) | 약 115KB(react + react-dom, gzip만) | 높음 | 높음 | 좋음 — 공식 "non-React widget" 지도 예제 | [React Compiler 1.0](https://react.dev/blog/2025/10/07/react-compiler-1) (2025-10-07), [useEffect](https://react.dev/reference/react/useEffect) |
| **Astro** | 7.3.5 (2026-09-24). 7.0 출시 2026-06-22 | 불가 | 기본 0KB + island 프레임워크 | 중간 | 높음 — 콘텐츠 사이트용, 단일 인터랙티브 화면엔 부적합 | island 안에서 처리 | [Astro 7](https://astro.build/blog/astro-7/) (2026-06-22) |
| **Vite** | 8.3.2 (2026-10-01). 8.0 출시 2026-03-12, Rolldown 단일 번들러, Node 20.19+ | 빌드 도구 자체 | — | 낮음 | 빌드 도입 비용 | — | [Vite 8](https://vite.dev/blog/announcing-vite8) (2026-03-12) |

**왜 Preact가 1순위인가.** 빌드 없는 구조를 유지하면서 경로 카드·턴바이턴 목록부터 한 화면씩 옮길 수 있습니다. "LLM 서술 생성 중/완료", "선택된 경로" 같은 상태를 signal로 두면 바뀐 부분만 다시 그려집니다. 단, 11.0은 이틀 전에 나왔으니 처음엔 10.x에 고정하는 편이 안전합니다.

**뺀 것.** htmx는 서버 구조를 바꿔야 하고, Astro·SvelteKit·React는 이 규모에 빌드 부담이 큽니다. Svelte 5는 지도 궁합이 가장 좋아 빌드를 도입한다면 다시 볼 만합니다.

## 3. 스타일링·컴포넌트·한국어 타이포그래피

빌드 없는 지금 구조에는 \*\*Pretendard 동적 서브셋 + Open Props(또는 직접 정의한 CSS 변수)\*\*가 가장 잘 맞습니다. Tailwind v4는 브라우저 버전이 있지만 공식 문서가 프로덕션용이 아니라고 명시하고, shadcn/ui·Radix·Base UI는 React + 빌드가 전제입니다. 버전·날짜는 npm 레지스트리 조회 기준입니다.

| 기술 | 무엇인가 | 현황(2026) | 이 앱 적용 포인트 | 출처 |
| --- | --- | --- | --- | --- |
| Tailwind CSS v4 | 유틸리티 클래스 CSS. 설정을 CSS 안 `@theme`으로 | v4.0 2025-01-22 → 최신 4.3.3 (2026-07-16) | 무빌드: `@tailwindcss/browser@4` 스크립트로 시제품만. 운영은 Tailwind CLI 단독 바이너리로 CSS 한 파일 미리 생성 | [Play CDN 문서](https://tailwindcss.com/docs/installation/play-cdn), [블로그](https://tailwindcss.com/blog) |
| shadcn/ui | 컴포넌트 코드를 프로젝트에 복사해 쓰는 React 모음 | React 19·Tailwind v4 지원(2025-02), Radix 대신 Base UI 선택 가능(2026-01). CLI 4.21.1 (2026-10-01) | (B)안에서 React 계열을 고를 때만. (A)안에선 색·radius 토큰만 참고 | [Changelog](https://ui.shadcn.com/docs/changelog), [Base UI 지원](https://ui.shadcn.com/docs/changelog/2026-01-base-ui) |
| shadcn 포트 | 프레임워크별 비공식판 | shadcn-svelte 1.7.0 (2026-09-16, Bits UI 기반), shadcn-vue 2.8.2 (2026-08-08, Reka UI 기반), solid-ui (Kobalte 기반, 버전 미확인) | 프레임워크 전환 시 후보. Preact는 shadcn React 코드를 `preact/compat`로 쓸 수 있으나 호환성은 미확인 | [shadcn-svelte](https://shadcn-svelte.com), [shadcn-vue](https://www.shadcn-vue.com) |
| Radix UI | 스타일 없는 접근성 React 컴포넌트 | `radix-ui` 1.6.7 (2026-07-24) | React 전용 | [Releases](https://www.radix-ui.com/primitives/docs/overview/releases) |
| Base UI | Radix·MUI 제작진의 headless React | 1.0.0 (2025-12-11), 최신 1.8.0 (2026-09-04) | React 전용 | [Releases](https://base-ui.com/react/overview/releases) |
| Ark UI / Zag.js | 상태머신 기반 headless, React·Vue·Solid·Svelte | @ark-ui 5.39.2, @zag-js/core 1.44.0 (2026-09-13) | 프레임워크를 오갈 가능성이 있으면 가장 유연. 바닐라 무빌드 사용 경로는 미확인 | [ark-ui.com](https://ark-ui.com) |
| Bits UI / Melt UI | Svelte용 headless | Bits UI 2.19.4 (2026-10-01). 차세대 Melt(`melt`) 0.44.0, 아직 0.x | Svelte 선택 시만 | [bits-ui.com](https://bits-ui.com), [next.melt-ui.com](https://next.melt-ui.com) |
| Open Props | 미리 만든 CSS 변수(간격·그림자·easing 등) 500개+ | 1.7.23 (2026-01-31), brotli 약 4KB | **(A)안에 최적.** `<link>` 한 줄로 토큰 사용, 필요한 것만 골라 써도 됨 | [open-props.style](https://open-props.style) |
| W3C 디자인 토큰 포맷(DTCG) | 토큰을 담는 JSON 표준 | 첫 안정판 v2025.10 (2025-10-28). 라이트·다크 테마, OKLCH 지원 | 지금은 선택. 색·간격을 JSON으로 정리해두면 나중에 CSS 변수나 Tailwind `@theme`으로 변환 | [W3C 발표](https://www.w3.org/community/design-tokens/2025/10/28/design-tokens-specification-reaches-first-stable-version/) (2025-10-28) |
| Pretendard | Inter + 본고딕 기반 한글 UI 폰트, 가변 폰트 | v1.3.9 (2023-11-05) 이후 새 릴리스 없음. OFL | 동적 서브셋 CSS(jsDelivr)로 쓰인 글자 조각만 내려받음 | [GitHub](https://github.com/orioncactus/pretendard) |
| SUIT | 본고딕 기반 한글 본문 폰트, 가변 | v2.0.5 (2024-07-24). OFL | Pretendard 대안 | [GitHub](https://github.com/sun-typeface/SUIT) |
| Wanted Sans | 기하학적 산세리프, 가변 | v1.0.3 (2024-03-05). OFL-1.1 | 대안 후보. 고정폭 숫자 지원 여부 미확인 | [GitHub](https://github.com/wanteddev/wanted-sans) |
| KRDS | 범정부 UI/UX 디자인 시스템 | 기본 서체 Pretendard GOV | 한글 크기·행간 수치의 공식 근거 | [KRDS 타이포그래피](https://www.krds.go.kr/html/site/style/style_03.html) |
| W3C klreq | 한국어 텍스트 레이아웃 요구사항 | Group Note Draft (2026-03-21) | 줄바꿈 단위(글자/어절), 한글 자간 기본 0 | [w3.org/TR/klreq](https://www.w3.org/TR/klreq/) (2026-03-21) |

**밀도 높은 한국어 UI 수치**

- 본문 17px, 최소 16px. 크기 단계 19/17/15/13px — [KRDS](https://www.krds.go.kr/html/site/style/style_03.html). 경로 카드 보조 정보(요금·거리)는 15px, 13px은 라벨에만.
- 행간 150% 이상 — KRDS. klreq는 160%를 예시로 듦. 토스 TDS 본문은 17/25.5px(1.5배) — [TDS Typography](https://tossmini-docs.toss.im/tds-react-native/foundation/typography/).
- 자간: 본문 0, 큰 제목만 조정 — KRDS, klreq.
- 굵기: 본문 400, 강조 700, 3\~4종 이내 — KRDS.
- 명도 대비: 일반 4.5:1, 큰 텍스트 3:1(AA) — KRDS, WCAG.
- 줄바꿈 `word-break: keep-all`로 단어 중간 끊김 방지. `auto-phrase`는 실험 단계 — [MDN word-break](https://developer.mozilla.org/en-US/docs/Web/CSS/word-break).
- 숫자: `Intl.NumberFormat('ko-KR', {style:'unit', unit:'kilometer'})` → `12.3km`, `minute` → `35분`, `hour` → `1시간` (Node 실행으로 확인) — [MDN Intl.NumberFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat).
- 시간·거리 열은 `font-variant-numeric: tabular-nums`로 숫자 폭 맞춤. Pretendard의 tnum 지원은 공식 문구 미확인 → 실제 렌더링으로 확인 필요.
- 네이버·카카오의 공개 타이포 가이드 수치: 미확인.

## 4. 지도 앱 UX 패턴과 레퍼런스

최근 지도 앱의 공통 흐름은 네 가지입니다. 지도는 항상 뒤에 깔고 정보는 높이를 바꿀 수 있는 시트에 띄운다, 행동 버튼은 아래에 고정한다, 경로의 장단점을 말로 설명한다, AI 진입점은 검색창 옆 버튼에 둔다. 다만 네이버·카카오·TMAP의 **길찾기 화면 자체** 개편과 구글 지도 웹 전면 개편은 공식 출처로 확인하지 못했습니다(미확인).

**최근 개편 사례**

| 앱 | 시기 | 화면에서 바뀐 것 | 출처 |
| --- | --- | --- | --- |
| 네이버지도 | 2026-09 | 검색창 오른쪽에 AI 버튼(플레이스 에이전트). 별도 대화창, 주제 3개 × 장소 3\~5곳 카드. 결과 없을 때 "AI 에이전트에게 묻기" 버튼. 길찾기 UI 변경은 미확인 | [다음 뉴스](https://v.daum.net/v/20260908170045667) (2026-09-08), [EBN](https://www.ebn.co.kr/news/articleView.html?idxno=1724629) |
| Google Maps | 2026-03-12 | Immersive Navigation(3D 차선·신호등). **대안 경로의 장단점을 문장으로 설명**(더 오래 걸리지만 덜 막힘 등). 도착 전 Street View 미리보기, 주차 추천. Ask Maps(대화형 검색) | [TechCrunch](https://www.techcrunch.com/2026/03/12/google-maps-is-getting-an-ai-ask-maps-feature-and-upgraded-immersive-navigation/) (2026-03-12) |
| Google Maps | 2025-11-05 | 주행 중 Gemini 음성 질의, 랜드마크 기반 안내(가까워지면 지도에 강조) | [Google 블로그](https://blog.google/products-and-platforms/products/maps/gemini-navigation-features-landmark-lens/) (2025-11-05) |
| Google Maps (Android 베타) | 2025-09-17 | Material 3 Expressive: 길찾기·출발·저장 버튼 줄을 아래에 고정, 정보를 구분선 대신 컨테이너로 묶음, 알약형 버튼 | [9to5Google](https://9to5google.com/2025/09/17/google-maps-m3-expressive/) (2025-09-17) |
| Google Maps (Android) | 2025-04-24 | 앱 전체를 시트 하나로 통일. 시트를 내리면 아래 지도를 그대로 조작 | [9to5Google](https://9to5google.com/2025/04/24/google-maps-sheet-redesign-android/) (2025-04-24) |
| Apple Maps (iOS 26) | 2025-06 발표 / 09 배포 | Liquid Glass: 조작 버튼이 지도 위에 떠 있는 별도 층, 스크롤 시 탭 바 축소. 자주 다니는 경로 학습(Preferred Routes) | [Apple Newsroom](https://www.apple.com/newsroom/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/) (2025-06-09), [9to5Mac](https://9to5mac.com/2025/09/18/heres-everything-new-for-apple-maps-in-ios-26/) (2025-09-18) |
| Apple Maps (웹) | 2024-07 베타 → 2025-04 정식 | maps.apple.com에서 운전·도보 길찾기, 장소 카드. 모바일 브라우저 지원 | [Apple Newsroom](https://www.apple.com/newsroom/2024/07/apple-maps-on-the-web-launches-in-beta/) (2024-07-24) |
| TMAP | 2025-10-16 | TMAP Auto에 AI 에이전트(경유지 여러 개를 한 번에 말하기, 대화형 검색). 모바일 앱 화면 개편은 미확인 | [전자신문](https://www.etnews.com/20251016000210) (2025-10-16) |
| 카카오맵 | 2025-07-02 | 검색창 아래 "AI맛집" 버튼(대화형 추천). 전면 레이아웃 개편은 미확인 | [카카오 공식](https://www.kakaocorp.com/page/detail/11619) (2025-07-02) |

**패턴 가이드**

| 패턴 | 핵심 원칙 | 이 앱 적용 | 출처 |
| --- | --- | --- | --- |
| 모바일 바텀시트 | standard(뒤 화면과 동시 조작)와 modal(뒤를 막음). 뒤로가기로 닫히게, 닫기 버튼 별도, 시트를 겹쳐 쌓지 않기 | 경로 카드 목록은 지도를 계속 움직일 수 있는 non-modal 시트. 설정·필터만 modal(`<dialog>`) | [NN/g Bottom Sheets](https://www.nngroup.com/articles/bottom-sheet/) (날짜 미확인), [M3 Bottom sheets](https://m3.material.io/components/bottom-sheets/guidelines) (세부 미확인) |
| 시트 높이 단계(detents) | 중간·전체 높이에 멈춤. 손잡이(grabber)는 탭으로도 높이 전환 | 3단계: 요약(시간·거리) / 중간(경로 카드 비교) / 전체(턴바이턴) | [Apple HIG Sheets](https://developer.apple.com/design/human-interface-guidelines/sheets) (날짜 미확인) |
| 데스크톱 사이드 시트 | standard는 본문과 함께 보며 조작. 좁은 화면에선 비권장 | 왼쪽 접이식 패널(약 360\~400px) + 나머지 전부 지도. 접으면 지도 확장 | [M3 Side sheet (Android 문서)](https://github.com/material-components/material-components-android/blob/master/docs/components/SideSheet.md) |
| 점진적 공개 | 처음엔 중요한 것 몇 개만, 원할 때 더 | 카드엔 시간·거리·요금만. 구간 상세·위험 지점·AI 서술은 펼칠 때 | [NN/g](https://www.nngroup.com/articles/progressive-disclosure/) (2006-12-03) |
| 목록-지도 동기화 | 같은 대상을 가리키는 요소는 hover 때 함께 강조해 "누르면 무엇이 되는지" 예측하게 | 카드 hover → 해당 폴리라인 두껍게 + 앞으로. 폴리라인 hover → 카드 강조 | [Baymard](https://baymard.com/blog/list-items-hover-and-hit-area) (2016-08-16, 상품 목록 연구를 응용) |
| 모바일 지도 vs 목록 | 지도 드래그와 페이지 스크롤이 헷갈림, 핀이 작음 | 시트 영역과 지도 제스처 구역을 명확히 분리, 핀·탭 영역 크게 | [NN/g](https://www.nngroup.com/articles/mobile-maps-locations/) (2014-01, 오래된 연구) |
| 턴바이턴 목록 | 권위 있는 가이드는 미확인. 구글은 거리 대신 랜드마크로 말하고 지도에 강조 | 항목 클릭 → 지도가 그 회전 지점으로 이동. 아이콘·안내문·거리 순 | 위 Google 블로그 (2025-11-05) |

**NCP 지도 SDK에서 되는 것** — [Polyline 문서](https://navermaps.github.io/maps.js.ncp/docs/naver.maps.Polyline.html), [Panorama 문서](https://navermaps.github.io/maps.js.ncp/docs/naver.maps.Panorama.html)

- 폴리라인 hover 동기화 가능: `mouseover`/`mouseout` 이벤트가 있지만 **`clickable: true`일 때만 발생(기본 false)**. hover 때 `strokeWeight`·`zIndex`를 올리면 됨.
- 파노라마는 서브모듈을 따로 불러오고 `position` 또는 `panoId`가 필수. 도착지 미리보기(구글 Immersive Navigation과 같은 패턴)에 활용.
- 인증 파라미터가 `ncpKeyId`로 통합됨(이전 `ncpClientId` 대체) — [Getting Started](https://navermaps.github.io/maps.js.ncp/docs/tutorial-2-Getting-Started.html).

**이 앱에 권하는 화면 구성**

- 데스크톱: 왼쪽 접이식 패널 + 오른쪽 전체 지도. 패널 맨 위에 출발·경유·도착 입력(한 덩어리), 그 아래 경로 카드 3개(시간이 가장 크게), 카드를 선택하면 같은 패널 안에서 턴바이턴으로 전환(View Transition). "비교"는 패널 아래 고정 버튼 → 넓은 `<dialog>` 또는 패널 폭 확장.
- 모바일: 지도 전체 화면 + 3단 바텀시트. 맨 위 입력창은 접힌 한 줄 요약("강남역 → 판교역")으로 축약.
- 지도 위 떠 있는 버튼은 교통량·로드뷰·내 위치 3개로 최소화.

## 5. 느린 AI 생성 콘텐츠의 UX

수십 초 걸리는 경로 비교 서술은 **기다리게 하지 말고 나눠 보여주기**가 답입니다. 비교표·위험 지점처럼 API 데이터로 바로 만들 수 있는 것은 즉시 띄우고, AI 서술만 아래에서 스트리밍합니다. AI가 화면 자체를 만드는 generative UI는 이 앱에 맞지 않습니다.

| 패턴/기술 | 핵심 | 이 앱 적용 | 출처 |
| --- | --- | --- | --- |
| 응답 시간 한계 | 0.1초 즉각 / 1초 흐름 유지 / 10초 주의 유지 한계. 10초 넘으면 "언제 끝나는지" 피드백 필수 | 서술 생성은 10초 초과 구간 → 스트리밍 + 단계 표시 | [NN/g](https://www.nngroup.com/articles/response-times-3-important-limits/) (1993) |
| 스켈레톤·스피너·진행바 | 10초 미만은 스켈레톤(페이지)·스피너(모듈). 10초 넘으면 진행바 강력 권장 | 경로 카드는 실제 크기의 스켈레톤. AI 서술은 "경로 분석 중 → 비교 작성 중" 단계 표시, 첫 글자가 오면 텍스트로 교체 | [NN/g Skeleton Screens](https://www.nngroup.com/articles/skeleton-screens/) (2023-06-04, 재검토 2026-09-02) |
| SSE (EventSource) | 서버→클라이언트 단방향 스트림, 자동 재연결. **GET만 가능**. HTTP/1.1에선 도메인당 연결 6개 제한 | 경로 데이터가 커서 POST가 필요하면 fetch 스트리밍 쪽이 맞음 | [MDN SSE](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) |
| fetch + `TextDecoderStream` | `res.body.pipeThrough(new TextDecoderStream())`로 조각 단위 읽기. Baseline(2022-09\~) | **권장.** POST로 경로 2\~3개를 보내고 `delta`(텍스트 조각) / `done`(최종 JSON) / `error`로 나눠 받음 | [MDN TextDecoderStream](https://developer.mozilla.org/en-US/docs/Web/API/TextDecoderStream) |
| Python `http.server` | 스트리밍 전용 API 없음, 기본 HTTP/1.0. `ThreadingHTTPServer` 권장, "운영 비권장" | `ThreadingHTTPServer` + `Content-Type: text/event-stream` + 조각마다 `wfile.write()` 뒤 `wfile.flush()`. HTTP/1.0이라 연결 종료로 응답 끝을 알림. chunked 예제는 공식 문서에 없음(미확인) | [Python 문서](https://docs.python.org/3/library/http.server.html) |
| 근거 인라인 표시 | 인용은 주장 바로 옆에, 의미 있는 라벨로. 사용자는 인용을 잘 안 눌러 과신하기 쉽고, 단계별 추론은 사후 합리화일 수 있음 | 서술 속 수치(시간·거리·요금)마다 경로 데이터 칩을 붙이고, 칩 hover → 지도 해당 구간 강조. 수치는 모델이 쓰지 않고 API 값만 끼워 넣음 | [NN/g Explainable AI](https://www.nngroup.com/articles/explainable-ai/) (2025-12-12) |
| Google PAIR | 적절한 신뢰(calibrated trust). 신뢰도는 %보다 높음/보통/낮음 같은 범주나 대안 제시 | "추천 1개"보다 두 경로의 장단점을 나란히 | [PAIR Guidebook](https://pair.withgoogle.com/chapter/explainability-trust/) (날짜 미표기) |
| Shape of AI | Citations, Disclosure(AI 생성 표시), Caveat(한계 고지) 등 패턴 모음 | AI 배지 + 한계 한 줄 + 근거 칩 + 다시 생성 버튼 | [shapeof.ai](https://www.shapeof.ai/) |
| Vercel AI SDK | AI SDK 6 출시(2025-12-22). RSC `streamUI`는 실험 단계, 운영엔 "tool 결과를 고정 컴포넌트로 렌더링" 방식 권장 | 프레임워크를 쓰더라도 이 방식만 참고 | [AI SDK 6](https://vercel.com/blog/ai-sdk-6) (2025-12-22), [Generative UI 문서](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces) |
| Google Generative UI | Gemini가 응답마다 UI를 생성. 생성에 때로 1분 이상, 가끔 부정확하다고 스스로 밝힘 | 부적합 — 이미 느린 응답이 더 느려짐 | [Google Research](https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/) (2025-11-18) |
| CopilotKit 분류 | Static(미리 만든 컴포넌트에 데이터만) / Declarative(JSON 스키마) / Open-ended(HTML·iframe, 위험) | **Static이 정답** | [CopilotKit](https://www.copilotkit.ai/blog/the-developer-s-guide-to-generative-ui-in-2026) (2026) |
| MCP Apps | 규격 Final(2025-11-21). 호스트(ChatGPT·Claude) 안에 UI를 띄우는 방식 | 독립 웹앱엔 해당 없음 | [MCP 블로그](https://blog.modelcontextprotocol.io/posts/2025-11-21-mcp-apps/) (2025-11-21) |

**권장 구조.** LLM에게 화면이 아니라 데이터를 받습니다.

```json
{"summary": "…", "pros": ["…"], "cons": ["…"], "recommendation": "routeA", "confidence": "보통", "citations": [{"routeId": "A", "segment": 3, "metric": "duration"}]}
```

서술 텍스트만 스트리밍하고 구조화 부분은 `done`에서 한 번에 받아, 기존 비교표·카드·지도 컴포넌트가 그립니다. 화면 순서는 ① 비교표·위험 지점 즉시 → ② 단계 표시 → ③ 서술 스트리밍 → ④ 근거 칩 활성화입니다.

## 6. 접근성·성능 기준

목표는 **WCAG 2.2 AA + INP 200ms 이하**입니다. 지도 앱에서 특히 걸리는 항목은 드래그 대체 수단(바텀시트·지도), 24px 타깃, 시트가 포커스를 가리지 않기, 스트리밍 텍스트의 스크린리더 소음입니다.

| 기준 | 요구사항 | 이 앱 체크포인트 | 출처 |
| --- | --- | --- | --- |
| WCAG 2.2 | W3C 권고, 현재 판 2024-12-12 | 목표 AA | [WCAG 2.2](https://www.w3.org/TR/WCAG22/) (2024-12-12) |
| 2.4.11 Focus Not Obscured (AA) | 포커스된 요소가 고정 콘텐츠에 완전히 가려지면 안 됨 | 바텀시트·고정 헤더가 포커스 요소를 덮지 않게 `scroll-padding` | 위와 같음 |
| 2.5.7 Dragging Movements (AA) | 드래그 기능은 탭·클릭으로도 가능해야 | 시트에 펼치기/접기 버튼, 지도에 +/− 줌 버튼 | 위와 같음 |
| 2.5.8 Target Size Minimum (AA) | 24×24 CSS px 이상(예외 있음) | 마커, 칩, 닫기 버튼, 경유지 삭제 버튼 | 위와 같음 |
| 3.3.7 Redundant Entry (A) | 이미 입력한 정보 재입력 강요 금지 | 최근 검색, 출발↔도착 뒤바꾸기 | 위와 같음 |
| 3.2.6 Consistent Help (A) | 도움말 위치 일관 | 도움말·피드백 링크 고정 | 위와 같음 |
| 4.1.3 Status Messages (AA) | 상태 메시지를 포커스 이동 없이 전달 | "분석 중", "완료"를 `role="status"`로 | 위와 같음 |
| WCAG 3.0 | 아직 Working Draft (2026-09-10판) | 대응은 2.2 AA 기준으로 | [WCAG 3.0](https://www.w3.org/TR/wcag-3.0/) (2026-09-10) |
| ARIA Combobox | input에 `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-activedescendant`. 포커스는 input에, ↓↑ 이동, Enter 선택, Esc 닫기 | 장소 자동완성에 적용(Popover와 함께 써도 role은 직접 지정). 결과 개수를 status로 알림 | [APG Combobox](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/) |
| Live region (스트리밍) | 라이브 리전은 내용이 바뀌기 전에 DOM에 있어야 함. 기본은 `polite` | 토큰마다 읽히면 소음 → 스트리밍 중엔 시각적으로만, 완료 시 요약 한 줄을 status로 알림. `aria-busy` 세부 동작은 MDN에서 직접 확인 못함(미확인) | [MDN Live regions](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions) |
| INP | 2024-03-12 FID 대체. 좋음 ≤200ms, 나쁨 >500ms (p75) | 스트리밍 텍스트는 `requestAnimationFrame` 단위로 묶어서 DOM 갱신. 폴리라인 좌표 파싱 같은 긴 작업은 쪼개기 | [web.dev INP](https://web.dev/articles/inp), [발표](https://web.dev/blog/inp-cwv-march-12) |
| `scheduler.yield()` | Chrome 129+, Firefox 142+, **Safari 미지원** | `scheduler.yield?.() ?? new Promise(r => setTimeout(r))` 폴백 | [Chrome 블로그](https://developer.chrome.com/blog/use-scheduler-yield) (2025-03-06) |
| LCP / CLS | LCP ≤2.5초, CLS ≤0.1 (p75) | 스켈레톤 크기를 실제 카드와 같게. 지도 컨테이너 높이를 미리 고정 | [web.dev Vitals](https://web.dev/articles/vitals) |
| `prefers-reduced-motion` | `reduce` / `no-preference`. Baseline(2020-01\~) | 지도 부드러운 이동, 스켈레톤 반짝임, 시트 전환을 줄이거나 끔 | [MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion) |
| View Transitions + 감소 모션 | 감소 모션이 "모션 0"은 아니니 더 은은한 전환으로 대체 권장 | `::view-transition-*`를 짧은 크로스페이드로 | [Chrome 문서](https://developer.chrome.com/docs/web-platform/view-transitions/same-document) |

## 리스크와 주의점

가장 큰 위험은 "최신"이라는 이유로 Limited 기능에 핵심 동작을 맡기는 것과, 막 나온 메이저 버전을 바로 쓰는 것입니다.

- **Limited 기능은 장식으로만.** `interpolate-size`, 스크롤 기반 애니메이션, 문서 간 View Transitions, `closedby`, `popover="hint"`, `if()`는 한두 브라우저만 지원합니다. 없어도 동작이 같아야 합니다(`@supports`로 감싸기).
- **Anchor Positioning은 실기기 확인.** 핵심은 세 브라우저 모두 지원하지만 세부 속성과 기본값이 최근(Chrome·Firefox 151, Safari 27)에야 맞춰졌습니다. 자동완성 위치가 어긋나면 JS 폴백이 필요할 수 있습니다.
- **막 나온 버전.** Preact 11(2026-09-30), SvelteKit 3(2026-10-01), htmx 4, Vue 3.6 RC, Solid 2.0 RC는 생태계가 따라오기 전입니다. 처음엔 Preact 10.x, Vue 3.5처럼 직전 안정 라인에 고정하세요.
- **지도 SDK와 프레임워크의 충돌.** 프레임워크가 지도 DOM을 다시 그리면 지도가 사라지거나 두 번 생성됩니다. 지도 컨테이너는 한 번만 만들고, 이후엔 폴리라인·마커 메서드만 호출하세요. NCP 폴리라인 hover는 `clickable: true`가 필요합니다.
- **Popover·`<dialog>` 위의 지도 이벤트.** 상단 레이어(top layer)에 뜬 요소와 지도 드래그·휠 이벤트가 겹치는지 확인이 필요합니다(NCP와의 조합은 미확인).
- **AI 서술의 수치 오류.** 모델이 시간·요금을 다시 쓰면 틀릴 수 있습니다. 숫자는 API 값을 끼워 넣고, 모델에겐 해석만 맡기세요. 실패·타임아웃 시 비교표만으로도 화면이 완결돼야 합니다.
- **Python 표준 서버의 스트리밍.** 동시 요청을 위해 `ThreadingHTTPServer`가 필요하고, 응답 버퍼링 때문에 조각마다 `flush()`가 필요합니다. 공식 문서도 운영 용도는 권하지 않습니다(1인 로컬 데모라 문제는 작음).
- **innerHTML과 XSS.** 장소명·AI 출력을 문자열 템플릿에 그대로 넣으면 스크립트 삽입 위험이 있습니다. (A)안에서도 `textContent`나 이스케이프 함수를 쓰세요.
- **Tailwind 브라우저 버전은 시제품용.** 공식 문서가 프로덕션용이 아니라고 명시합니다.
- **확인하지 못한 것.** 국내 지도 앱 길찾기 화면 개편 상세, Material 3·Apple HIG 일부 본문(JS 렌더링 페이지), Pretendard 고정폭 숫자 지원, Svelte 런타임 공식 크기, Solid 2.0 출시일. 표의 webstatus.dev 링크는 같은 공식 데이터셋으로 값을 확인했지만 페이지 자체는 직접 열지 못했습니다.
