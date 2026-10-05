# NCP Maps API 테스트 — 죽전역 → 강남역

네이버 클라우드 플랫폼(NCP) Maps API를 REST로 호출해 자동차 경로를 뽑고,
결과를 Web Dynamic Map으로 브라우저에서 확인하는 테스트 스크립트.

## 확인된 스펙 (2026-09 기준, 실호출 검증 완료)

공식 문서 페이지마다 호스트가 엇갈려 있어서 **실제로 호출해 확인**했다.

| 항목 | 값 |
|---|---|
| API 호스트 | `https://maps.apigw.ntruss.com` |
| 구 호스트 | `naveropenapi.apigw.ntruss.com` → **401** `{"errorCode":"210","message":"Permission Denied"}` |
| 인증 헤더 | `x-ncp-apigw-api-key-id`, `x-ncp-apigw-api-key` |
| Geocoding | `GET /map-geocode/v2/geocode` |
| Reverse Geocoding | `GET /map-reversegeocode/v2/gc` |
| Directions 5 | `GET /map-direction/v1/driving` |
| Directions 15 | `GET /map-direction-15/v1/driving` |
| Static Map | `GET /map-static/v2/raster` |
| Web Dynamic Map | `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=...` (구 `ncpClientId` 아님) |
| 지역 검색(POI) | `GET https://naverapihub.apigw.ntruss.com/search/v1/local` — **NAVER API HUB, Maps 와 별개 상품·별개 키** |

> 영문 문서의 Directions / Reverse Geocoding 페이지에는 아직 구 호스트가 남아 있다.
> 문서를 그대로 믿고 짜면 401이 난다.

좌표는 **모든 API에서 `경도,위도` 순서**다. Geocoding 응답의 `addresses[0].x`가 경도,
`y`가 위도이며 둘 다 문자열로 온다.

## 준비

```bash
pip3 install -r requirements.txt        # requests 만 필요
cp .env.example .env                    # 그리고 발급받은 키를 채운다
```

> macOS + Homebrew Python은 PEP 668로 전역 설치가 막혀 있다. 가상환경을 쓰지 않으려면
> `pip3 install --user --break-system-packages -r requirements.txt` 로 사용자 영역에 설치한다.

`.env` (커밋 금지, `.gitignore`에 등록되어 있음):

```
NCP_MAPS_CLIENT_ID=...
NCP_MAPS_CLIENT_SECRET=...

# 장소명 검색용 (NAVER API HUB). 없으면 주소 기반으로만 동작한다.
NAVER_HUB_CLIENT_ID=...
NAVER_HUB_CLIENT_SECRET=...
```

**지역 검색 키는 Maps 키와 다른 값이다.** NCP 콘솔 > NAVER API HUB 에서
Application 을 따로 등록하고 '지역 검색'을 선택해 발급받는다
(일 25,000건 / 월 775,000건 무료).

NCP 콘솔에서 해당 Application에 **Geocoding / Reverse Geocoding / Directions 5 /
Directions 15 / Static Map / Web Dynamic Map**을 모두 신청하고,
**서비스 환경 > Web 서비스 URL에 `http://localhost:3000`** 을 등록해야 한다.

## 실행

```bash
python3 run_scenario.py
```

5단계가 순서대로 돌고 마지막에 요약 리포트가 나온다.

1. **장소 해석** — 검색어 → 후보 목록 → 선택 → 좌표. 3단 폴백:
   ① 지역 검색(장소명) → ② Geocoding(주소) → ③ 하드코딩 좌표
2. **Directions 5** — `trafast` / `tracomfort` / `traoptimal` 비교표 (거리·시간·택시요금·통행료)
3. **Directions 15** — 판교역 경유로 재요청, Directions 5 결과와 Δ거리·Δ시간·Δ통행료 비교
4. **Reverse Geocoding** — 도착 좌표 → 주소 (`orders=roadaddr,addr`).
   1단계가 확정한 주소와 **도로명·지번 두 축으로** 대조한다
5. **Static Map** — 경로 중간 지점 중심 지도 → `out/static-map.png`

### 옵션

```bash
python3 run_scenario.py --from 죽전역 --to 강남역 --via 판교역
python3 run_scenario.py --interactive      # 후보 목록에서 직접 번호 선택
python3 run_scenario.py --transit-only     # '교통,운수' 카테고리만 (역·터미널)
python3 run_scenario.py --no-search        # 지역 검색 건너뛰고 Geocoding 부터
```

`--transit-only` 는 5건 제한 아래서 특히 유용하다. `강남역` 검색 시
치폴레·미용실 같은 상호가 후보 5칸을 잡아먹는데, 이 필터를 켜면
`강남역 신분당선` / `강남역 2호선` 둘만 남는다.

### 산출물

```
out/
├── raw/                  # API별 원본 응답 (01_geocode_origin.json … 07_staticmap.png)
├── report.json           # 요약 리포트 (path 제외)
├── route.json            # Dynamic Map이 읽는 경로 좌표
├── static-map.png        # 5단계 결과
└── index.html            # Dynamic Map 페이지 (템플릿 + 클라이언트 ID 주입)
```

## Dynamic Map 확인

Web JS는 REST가 아니라 브라우저에서 확인해야 하고, **콘솔에 등록된 URL에서만 인증이 통과**한다.
`file://`로 열면 실패하므로 반드시 3000 포트로 서빙한다.

```bash
python3 -m http.server 3000 -d out
# 브라우저에서 http://localhost:3000 열기
```

Directions 5의 3개 옵션과 Directions 15 경유 경로를 색깔별 Polyline으로 겹쳐 그리고,
출발/경유/도착에 Marker를 찍는다. 우측 패널에서 경로별로 켜고 끌 수 있다.

## 경로 비교 — "아버지가 설명해주는" 평가

길찾기 결과 위의 **⚖ 경로 비교** 버튼을 누르면 세 경로를 평가·비교한다.
설계 문서: `docs/superpowers/specs/2026-09-11-route-compare-design.md`

```
/api/evaluate  (수 초, 바로 그린다)
  ├ ncp_maps/evaluate.py   경로 → 지표·편의 점수·사실 목록 (결정적, LLM 없음)
  └ ncp_maps/hazards.py    사고다발·단속카메라·보호구역·결빙
/api/narrate   (SSE 스트림, 수십 초~2분)
  └ ncp_maps/narrate.py    사실 목록 → claude -p CLI(stream-json) → 문장 단위 JSON (근거 ID 필수)
                           event: stage · partial(완성된 문장까지) · retry · done · fail
/api/compare   (호환용: 위 둘을 한 번에)
```

- 화면은 비교표·위험 지점을 먼저 보여주고, AI 설명은 **결론 한 줄(`comparison.headline`)부터** 문장이 완성될
  때마다 채운다. 실측: 결론 도착 ≈ 13~28초, 전체 ≈ 110초. 탭을 닫거나 '중지'를 누르면 CLI 생성도 멈춘다.
- `--output-format stream-json --verbose --include-partial-messages` 에서 구조화 출력은 `input_json_delta`
  조각으로 온다(실측). 서버가 부분 JSON 을 '닫힌 객체'까지만 잘라(`parse_partial`) 검증 후 내보낸다.
- 같은 경로로 나온 옵션(예: 실시간 빠른길 = 실시간 최적)은 서버에서 한 장으로 합친다(`merge_identical`).

- **LLM 호출은 로컬 `claude` CLI(`-p`)로 한다.** API 키·SDK를 쓰지 않는다. Claude Code가 설치·로그인되어
  있으면 그대로 동작하고, 없으면 비교표·엔진 판정까지만 나오고 설명글 자리에 사유가 표시된다.
- 모든 문장에 근거 사실 ID(`R1.F3`)가 붙고 서버가 실재 여부를 검증한다. 일반 운전 지식은 `GK`로 표시되어
  UI에서 이탤릭+"일반 요령" 배지로 구분된다. 근거가 안 맞는 문장은 회색 "근거 미확인".
- 실측: 3경로 서술 1회 ≈ **100초, $0.28** (`claude-opus-5`). 두 번째 호출부터 시스템 프롬프트 캐시 적중.
- `--json-schema`는 CLI 내부적으로 `StructuredOutput` 도구 호출로 구현되어 있어 **`--tools StructuredOutput`**
  으로 그 도구만 열어야 한다. `--tools ""`로 전부 막으면 무한 대기한다(실측).
- 모델은 `ROUTE_CLAUDE_MODEL`(기본 `opus`)로 핀 — `/model` 설정에 흔들리지 않는다.

### 위험 구간 (`ncp_maps/hazards.py`)

공공데이터로 확인된 지점만 붙인다. 사고다발 6종(보행자·지자체별·보행어린이·보행노인·결빙·자전거) +
무인단속카메라 + 어린이/노인보호구역. 죽전역→강남역 기준 경로당 17~20건이 잡힌다.

- 인증키 2개가 필요하다: `DATA_GO_KR_KEY`(공공데이터포털) + `KOROAD_AUTH_KEY`(KOROAD 개방포털).
  **보행자 사고다발만 KOROAD 포털에 있다** — data.go.kr B552061에는 없다(실측 400).
- 시도·시군구 코드는 행정표준코드 5자리를 `siDo`(앞2) + `guGun`(뒤3)으로 쪼갠다. 문서에 없어 실측으로 찾았다.
- 표준데이터 파일 4종은 `data/`에 두면 기동 시 격자 색인으로 적재된다(gitignore 대상).
- **야간 위험은 표시하지 않는다.** 지점 단위 공개 데이터가 없다. 추정으로 채우지 않는다.

한계는 스펙에 못박아 두었다: 차선 수는 응답에 없어 **"합류·분기 횟수"로 대리**한다.
위험 데이터 조사 기록: `docs/hazard-data-research-prompt.md`

테스트: `python3 -m unittest tests.test_evaluate` (LLM 호출 없음, 23개)

## 호출량 관리

무료 이용량은 **계정 단위**이고 Directions 15는 월 3,000건(초과 시 건당 20원)뿐이라
루프를 돌지 않고 **1회 실행에 총 7회**만 호출한다.

| API | 호출 |
|---|---|
| 지역 검색 | 3 (출발·도착·경유) |
| Directions 5 | 1 |
| Directions 15 | 1 |
| Reverse Geocoding | 1 |
| Static Map | 1 |
| Geocoding | 0 — 지역 검색이 실패한 지점에서만 추가로 호출된다 |

Directions는 `option`을 `:`로 묶어 **한 번의 호출로 3개 옵션을 모두** 받는다
(`option=trafast:tracomfort:traoptimal`). 옵션마다 따로 부르면 호출이 3배가 된다.
실패해도 자동 재시도하지 않는다 — 재시도 루프가 곧 요금이다.

## 구조

```
ncp_maps/
├── client.py      # HTTP 호출, 로깅, 원본 응답 저장, 에러 힌트, .env 로딩
└── api.py         # API별 요청 래퍼 + 응답 파싱 (좌표/요약/레벨 계산)
run_scenario.py    # 시나리오 실행 + 콘솔 리포트
web/index.template.html   # Dynamic Map 템플릿 (__NCP_KEY_ID__ 치환)
```

## 알아둘 것

- **역 이름으로는 지오코딩이 안 된다.** Geocoding은 POI 검색이 아니라 주소 검색이다.
  `죽전역`은 물론이고 지하철역 도로명주소인 `포은대로 지하 464`처럼 '지하'가 붙은 주소도
  `status=OK, totalCount=0`으로 빈 결과가 온다. **그래서 지역 검색(NAVER API HUB)을 앞에 둔다.**
- **지역 검색의 제약 (실측)**: `display` 최대 5, **`start` 무시되어 페이징 불가**,
  `total`은 총건수가 아니라 반환 건수(= display). 즉 **최대 5건이 전부다.**
  `--transit-only` 로 노이즈를 걷어내는 게 사실상의 대응책.
- **`title`에 `<b>` 태그가 섞여 온다** (`"<b>죽전역</b> 수인분당선"`). 스트립 필수.
- **`mapx`/`mapy`는 WGS84 × 10⁷ 정수 문자열**이다. `int(v)/1e7` 로 나눠야 경도/위도가 된다.
  검증: 죽전역 `1271073977, 373245825` → `127.1073977, 37.3245825`, 실제 위치와 오차 20m.
- **`telephone`은 항상 빈 값**이다 (문서에 "값을 반환하지 않는 요소"로 명시). `link`,
  `description`도 지하철역 항목에서는 비어 있었다.
- **POI 좌표는 등록 주소와 역지오코딩 결과가 어긋날 수 있다.** `강남역 신분당선`의 좌표를
  역지오코딩하면 도로명은 `강남대로 374-2`(등록 주소는 `강남대로 396`)로 다르지만
  지번은 `역삼동 858`로 같다. 대표 지점(출입구 등) 좌표라서 그렇고, 좌표가 틀린 것은 아니다.
  그래서 4단계 검증은 도로명·지번 두 축으로 본다.
- **Directions의 `duration`은 밀리초**, `distance`는 미터다.
- **Reverse Geocoding은 `output=json`을 안 주면 XML**이 온다.
- **`naver.maps.Map`은 컨테이너의 `position`을 `relative`로 덮어쓴다.**
  `position:absolute; inset:0`으로 크기를 주면 높이가 0으로 무너져 지도가 안 보인다.
  컨테이너에 실제 `width`/`height`를 줄 것.
- 401/403이 나면 ① 키 오타 ② 콘솔에서 해당 API 미신청 ③ 구 호스트 사용
  ④ 서비스 환경(Web 서비스 URL) 미등록 순서로 확인한다. 스크립트가 이 힌트를 같이 출력한다.
