# [Web Claude · Research] 최신 UI 기술 조사 프롬프트

claude.ai에서 **Research(웹 검색) 모드를 켜고** 아래 구분선 사이 내용을 붙여넣는다.

---

지도 중심 자동차 길찾기 웹앱의 UI를 전면 개선하려고 한다. 2025~2026년 기준 최신 웹 UI 기술과 UX 패턴을 웹 검색으로 충분히 조사해서 정리해줘. 모든 주장에는 출처 URL과 날짜를 달고, 공식 문서·릴리스 노트·신뢰할 만한 엔지니어링 블로그를 우선해줘. 확인하지 못한 내용은 "미확인"으로 표시해줘.

## 현재 앱
- 1인용 로컬 데모. Python 표준 라이브러리 서버 + **HTML 파일 1개(약 1,500줄, 인라인 CSS, 바닐라 JS, innerHTML 문자열 템플릿, 빌드 도구 없음)**
- 지도: **네이버 클라우드(NCP) Web Dynamic Map JS v3** — 혼잡도별 색 경로선, 로드뷰(파노라마), 교통량 레이어. 지도 SDK는 유지해야 함
- 기능: 장소 자동완성, 출발/경유/도착 입력, 경로 카드 최대 3개, 턴바이턴 상세 경로, 경로 비교(비교표 + LLM이 수십 초 걸려 생성하는 서술 + 위험 지점 목록)
- 개선 목표: 최신 기술로 사용자 경험 개선, 화면을 동적으로 구성, 가독성 향상, 불필요한 요소 제거, 핵심 기능 집중

## 조사 항목
1. **네이티브 웹 플랫폼 기능 (JS를 줄여주는 것)**: View Transitions(같은 문서/문서 간), Popover API, CSS Anchor Positioning, `<dialog>`, Container Queries, `:has()`, Scroll-driven Animations, `@starting-style`, `interpolate-size`/`calc-size()`, 커스터마이즈 가능한 `<select>`(appearance: base-select), CSS Nesting, `@scope`, `light-dark()`, `field-sizing`, Navigation API 등. 각각 2026년 기준 브라우저 지원(Baseline 여부)과 **이 앱에서 쓸 지점**.
2. **프레임워크 선택지와 트레이드오프**: 바닐라 + Web Components/Lit, htmx/Alpine.js, Preact + Signals, Svelte 5(runes)/SvelteKit, SolidJS, React 19 + React Compiler, Vue 3.5/Vapor mode, Astro islands, Vite. 이런 작은 앱에서의 학습 비용, HTML 1개 파일에서 옮기는 난이도, **명령형 지도 SDK와의 궁합**을 기준으로 1~2개 추천.
3. **스타일링·컴포넌트**: Tailwind CSS v4, shadcn/ui와 프레임워크별 대응판, Radix/Ark UI/Base UI/Melt UI, Open Props, 디자인 토큰, 한국어 가변 폰트(Pretendard, SUIT 등), 밀도 높은 한국어 UI의 가독성 가이드(글자 크기, 줄간격, 숫자 표기).
4. **지도 앱 UX 패턴**: 모바일 바텀시트, 접히는 사이드 패널, 경로 비교 카드, 턴바이턴 목록, 지도-목록 연동(hover 하이라이트), 점진적 공개(progressive disclosure). 네이버지도·카카오맵·구글 지도·애플 지도·TMAP의 최근(2025~2026) 웹/앱 리디자인 사례.
5. **느린 AI 생성 콘텐츠의 UX**: 스트리밍 텍스트(SSE, fetch 스트리밍), 스켈레톤, 진행 표시, 근거를 인라인으로 보여주는 방식, AI가 화면을 구성하는 generative UI 패턴과 이 앱에 맞는지 여부.
6. **접근성·성능 기준**: WCAG 2.2 핵심 항목, INP, prefers-reduced-motion.

## 출력 형식 (한국어)
- **TL;DR** 5줄
- **추천 스택 2안**: (A) 최소 변경안 — 빌드 없이 네이티브 기능 위주 / (B) 본격 전환안 — 프레임워크 도입. 각각 예상 작업량·장단점
- 항목별 표: 기술 | 무엇인가 | 지원 현황(2026) | 이 앱 적용 포인트 | 출처
- 레퍼런스 지도 앱 패턴 정리 (가능하면 화면 구성 설명 포함)
- 리스크와 주의점

---

> 결과를 받아오면 이 세션에 붙여넣거나 `docs/ui-review/research-web-claude.md`로 저장해줘. 서브에이전트 결과(`research-subagent.md`)와 비교해서 합치겠다.
