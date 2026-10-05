# 경로 평가·비교 기능 설계

작성 2026-09-11. 프로젝트 `route-guide`. 대상: 검색된 자동차 경로(최대 3개)를 평가·비교해
초보 운전자에게 "운전 경력 많은 아버지가 아들에게 설명하는" 톤으로 서술한다.

## 확정된 결정

| # | 결정 | 근거 |
|---|---|---|
| D1 | **데이터 근거만.** 위험 구간은 실제 데이터셋이 붙기 전까지 비운다 | 검증 불가한 서술로 신뢰를 잃는 게 최대 리스크 |
| D2 | **LLM 서술 + 엄격한 근거 주입.** 모든 문장에 근거 ID | 톤은 살리고 환각은 막는다 |
| D8 | LLM 호출은 **`claude -p` CLI**로, API 키·SDK 미사용 | 사용자 결정(kr-by-claude 방식과 통일) |
| D3 | 위험 데이터 4종: 사고다발지점(TAAS), 단속카메라, 어린이·노인 보호구역, 결빙·안개 취약구간 | 사용자 선택 |
| D4 | "경로 비교" 버튼을 눌렀을 때만 생성 | 비용·지연 통제 |
| D5 | **일반 운전 지식은 허용, 특정 도로·지역 단정은 금지** (D1의 완화선) | "고수가 되게 하는" 부분을 살리면서 지어낸 지역 정보는 차단 |
| D6 | 야간 항목은 v1에서 "근거 없음"으로 비움. (b) 리서치에 야간 소스 조사 추가 | TAAS 분류에 야간이 없음(실측) |
| D7 | 접근안 A — 3단 파이프라인(지표 → 위험 매칭 → 서술) + 로컬 위험 색인 | 숫자와 문장의 물리적 분리, LLM 없이 검증 가능 |

## 범위 분할

- **v1 (이 스펙)** = (a) 지표 엔진 + (c) LLM 서술 + (d) 비교 UI
- **(b) 위험 데이터 파이프라인** = 2026-09-11 구현 완료. `ncp_maps/hazards.py` 참조.
  리서치 프롬프트: `docs/hazard-data-research-prompt.md`

## 알려진 한계 (스펙에 못박음)

- **차선 변경 빈도는 측정 불가.** Directions 응답에 차선 필드가 없다(실측). 합류·분기·출구·고가/지하 진입 횟수를 "합류·분기 횟수"라는 이름으로 대리한다. LLM에게 "차선 변경이 잦다"는 표현을 금지한다.
- **고속화 비율은 하한값.** `section`이 경로의 52~76%만 덮으므로(실측) 비율 분모는 총거리, 분자는 확인된 고속화 구간만이다.
- **`guide.type` 코드표를 전부 갖고 있지 않다.** 확인된 코드는 코드로, 나머지는 문구 정규식으로 분류하고, 분류 불가는 "기타"로 둔다.

## 0단계 — 선행 조건

- 로컬에 **Claude Code CLI(`claude`)가 설치·로그인**되어 있어야 한다. API 키·SDK는 쓰지 않는다
  (사용자 결정 — kr-by-claude 프로젝트와 같은 방식). CLI가 없으면 서술만 비활성, 지표·비교표는 동작해야 한다.

## (a) 지표 엔진 — `ncp_maps/evaluate.py`

입력: `/api/route`가 캐시한 경로 목록(각각 `summary`, `path`, `sections`, `guides`).
출력: 결정적 JSON. LLM 없음.

### 분기점 분류

`guide.type` 확인 코드 우선 → 문구 정규식 폴백. 문구는 `'…' 방면으로`와 `X에서` 접두를 벗겨낸 뒤 끝부분으로 판정한다
(`'판교IC(서울·청계·송파)' 방면으로 좌회전`은 IC가 아니라 **좌회전**이다).

| kind | 라벨 | 코드 | 문구 |
|---|---|---|---|
| `uturn` | 유턴 | 6 | 유턴 |
| `toll` | 톨게이트 | 121~123 | 톨게이트 |
| `hwy_exit` | 고속도로 출구 | 67 | 고속도로 출구 |
| `overpass` | 고가차도 진입 | 55, 62 | 고가차도 |
| `underpass` | 지하차도 진입 | 73 | 지하차도 진입 |
| `sideroad` | 옆길·합류 | 74 | 옆길, 합류 |
| `branch` | 분기(오른쪽·왼쪽 방향) | 42 | 오른쪽/왼쪽 방향, 오른쪽/왼쪽 도로 주행 |
| `left` / `right` | 좌회전 / 우회전 | 2 / 3 | 좌회전 / 우회전 |
| `straight` | 직진 | 1 | 직진 |
| `via` / `goal` | 경유지 / 목적지 | 87 / 88 | 경유지 / 목적지 |
| `other` | 기타 | — | (분류 불가) |

부가 플래그 `at_interchange` = 원문에 `(IC|JC|분기점)에서`가 있음.

### 경로별 지표

- 분기점 총수, kind별 카운트
- **합류·분기 횟수** = `branch + hwy_exit + sideroad + overpass + underpass`
- 평균 분기 간격(km) = 거리 ÷ (goal·via 제외 분기 수), 최장 무분기 구간(km) = max(`guide.distance`)
- 고속화 비율 = Σ(도로명에 고속도로·고속화도로·자동차전용 포함 **또는** 속도 ≥ 60인 section 거리) ÷ 총거리
- 저속 구간 = 속도 < 20인 section 목록과 합계 km
- 복잡 분기 목록 = kind ∈ {uturn, overpass, underpass, branch, hwy_exit, sideroad} → 로드뷰 추천 후보(step 인덱스 포함)

### 편의 점수 (낮을수록 편함)

```
score = Σ(분기점, goal·via 제외) × 1
      + uturn × 3
      + (overpass + underpass) × 2
      + (branch + hwy_exit + sideroad) × 2
      + toll × 1
      + 저속구간_km × 0.5
      − 고속화비율 × 3
```

가중치는 첫 시안. 상수로 노출해 조정 가능. **순위는 엔진이 매기고 LLM은 설명만 한다.**

### 비교

`fastest`(최소 시간), `shortest`(최소 거리), `most_comfortable`(최소 점수), `cheapest`(통행료+연료비 최소).

### 사실 스키마 (엔진 → LLM)

모든 사실에 ID `R{경로번호}.F{순번}`. `kind` ∈ {summary, road, maneuver, complex, comfort, gap, slow}. 복잡 분기는 `step`을 가진다.

```json
{
  "trip": {"origin": "...", "goal": "...", "via": null},
  "routes": [{
    "id": "trafast", "label": "실시간 빠른길",
    "metrics": {...},
    "comfort": {"score": 31.0, "rank": 2},
    "facts": [{"id": "R1.F1", "kind": "summary", "text": "..."}, ...],
    "hazards": []
  }],
  "comparison": {"fastest": "trafast", "shortest": "...", "most_comfortable": "...", "cheapest": "..."}
}
```

## (c) 서술 생성 — `ncp_maps/narrate.py`

- **호출은 `claude -p` CLI subprocess** (kr-by-claude `llm/claude_cli.py` 방식):
  `claude --print --output-format json --model opus --tools StructuredOutput --no-session-persistence
  --append-system-prompt <정적 프롬프트> --exclude-dynamic-system-prompt-sections --json-schema <스키마>`
  - 정적 프롬프트는 `--append-system-prompt`로 올려 캐시 프리픽스가 되게 한다. 호출별 입력(사실 JSON)은 stdin.
  - **`--tools StructuredOutput`** — `--json-schema`는 CLI 내부적으로 StructuredOutput 도구 호출(`num_turns=2`)로
    구현되어 있어, `--tools ""`로 전부 막으면 출력 경로가 사라져 무한 대기한다(실측 300s 타임아웃). 이 도구
    하나만 허용하면 Read/Bash/Web* 은 열리지 않아 입력 JSON만으로 답하게 된다. 소형 입력 기준 45s, $0.075.
  - 모델은 별칭 `opus`로 핀 (`ROUTE_CLAUDE_MODEL`로 오버라이드). 사용자의 `/model` 설정에 흔들리지 않게.
  - 결과는 `{"type":"result","result":…,"usage":…,"modelUsage":…,"total_cost_usd":…}` 봉투에서 추출. 1/3/9초 재시도.
  - 사용량 한도 메시지는 재시도하지 않고 즉시 오류로 반환.
- **`--json-schema`로 섹션별 JSON 강제**:

```
routes[].overview[]      {text, basis[]}   경로 전체 설명, 문장 단위
routes[].verdict         {text, basis[]}   총평
routes[].comfort_note    {text, basis[]}   편의 순위 설명 (순위는 엔진 값 그대로)
routes[].cautions[]      {text, basis[], step?}
routes[].roadview_picks[]{step, reason}    복잡 분기 step 중에서만
comparison.summary       {text, basis[]}
```

- `basis`는 사실 ID 목록. **일반 운전 지식 문장은 `basis: ["GK"]`** — UI가 사실과 구분해 렌더링한다.
- **야간·우천 섹션은 LLM 출력에 없다.** `hazards`가 비면 서버가 고정 문구를 넣는다. LLM에게 맡기면 채우려 든다.

### 시스템 프롬프트 (고정 → `--append-system-prompt`, 캐시 프리픽스)

- 페르소나: 운전 경력 많은 아버지가 아들에게. 다정하고 정확. 과장·겁주기 금지.
- 허용: 입력 사실 전부. 지역 무관 일반 운전 지식(고속도로 진출입·유턴·지하차도·톨게이트·합류 요령).
- 금지: 입력에 없는 수치. 특정 도로·지역·시간대 단정. "차선 변경이 잦다" 표현(→ "합류·분기가 N번 있어 차선을 옮길 일이 생긴다").
- 분기 용어집(kind별 뜻)과 출력 스키마 설명 포함.

### 서버 검증

`basis`의 ID가 사실 목록에 없고 `GK`도 아니면 그 문장에 `unverified: true`. 문장을 삭제하지 않는다 — UI가 회색 처리하고 사용자가 판단한다.
`roadview_picks[].step`이 복잡 분기 목록에 없으면 제외한다.

### 실패 처리

CLI 없음 / 종료코드≠0 / 봉투 누락 / 타임아웃(300s) / 사용량 한도 → `narration: null, narration_error: "<사유>"`.
지표·비교표는 정상 반환. 실패 결과는 캐시하지 않는다.

### 비용

CLI 봉투의 `total_cost_usd`를 그대로 로그·응답(`narration_meta`)에 남긴다. 스모크 테스트에서 기본 시스템
프롬프트 캐시 생성만 9.9k 토큰이 잡혔으므로, 실측 후 필요하면 `--exclude-dynamic-system-prompt-sections`
효과(재호출 시 cache_read 증가)를 확인한다. 서술 결과는 경로 키(start|goal|waypoints)로 서버 캐시.

## API — `serve.py`

`GET /api/compare?start=lon,lat&goal=lon,lat[&waypoints=…]`

1. `backend.route()` 캐시에서 경로 취득(없으면 조회)
2. `evaluate_routes()` → evaluation
3. `claude` CLI가 있으면 `narrate()` → narration (캐시)
4. 응답 `{evaluation, narration, narration_error, narration_meta, hazards_status}`

## (d) UI — `web/app.html`

- `.meta` 줄에 **"경로 비교"** 버튼. 경로 2개 이상일 때 활성.
- 새 슬라이드 패널 `#compare`(사이드바 오른쪽, 폭 420px). `#detail`과 동시에 열리지 않는다.
- 상단 **비교표**: 열 = 경로, 행 = 시간·거리·통행료·연료비·분기점·합류분기·유턴·고속화·편의순위. 각 행 최선값 강조.
- 아래 **경로별 탭**: overview → verdict → comfort_note → cautions → roadview_picks → 위험 구간("데이터 준비 중" 고정).
- 문장 렌더링: 사실 기반 = 기본, `GK` = 이탤릭+"일반 요령" 배지, `unverified` = 회색+"근거 미확인".
- **사실 표**를 접이식으로 병기 — 사용자가 산문과 대조할 수 있게(F6의 마지막 겹).
- `roadview_picks`의 step 클릭 → 해당 경로 선택 + 상세 열기 + `focusStep(step)`.
- 상태: 로딩("비교 중…"), 서술 불가(`narration_error` 사유 표시 — CLI 없음·한도·시간 초과 등), 오류.
  서술이 없어도 비교표·엔진 판정 복잡 분기·근거 사실은 그대로 보인다.

## 테스트

`tests/test_evaluate.py` — `python3 -m unittest`. 실제 응답 픽스처(`tests/fixtures/route_sample.json`)로:
- 분기 분류가 함정 문구(`'판교IC…' 방면으로 좌회전` → left)를 맞히는가
- 지표 합산, 편의 점수, 순위가 손계산과 일치하는가
- 사실 ID가 유일하고 복잡 분기에 `step`이 있는가
- `basis` 검증이 없는 ID를 `unverified`로 표시하는가 (narrate의 검증 함수만, API 호출 없음)

## (b) 위험 데이터 — `ncp_maps/hazards.py` (구현 완료)

### 실측으로 확정한 것 (문서에 없던 내용)

- **시도·시군구 코드 형식**: 행정표준코드 5자리를 `siDo`(앞 2) + `guGun`(뒤 3)으로 쪼갠다.
  `11680`(강남구) → `siDo=11&guGun=680`. 12가지 조합을 시도해 찾았다.
- **동작하는 엔드포인트** `apis.data.go.kr/B552061/{svc}/getRest{Svc}` — 5종:
  `frequentzoneLg` · `frequentzoneChild` · `frequentzoneOldman` · `frequentzoneFreezing` · `frequentzoneBicycle`
- **보행자 사고다발은 B552061에 없다**(HTTP 400). KOROAD 자체 포털이 별도 `authKey`로 제공:
  `opendata.koroad.or.kr/data/rest/frequentzone/pedstrians`. 응답 스키마는 동일하다.
- **`frequentzoneLg`는 구 단위가 아니라 시 단위** top3다. 용인시 수지구·기흥구가 완전히 같은
  결과를 준다. 시 코드(앞 4자리)로 한 번만 호출하고, 결과도 좌표 기준으로 중복 제거한다.
- **응답 `geom_json`은 EPSG:4326 정상 JSON**이라 재투영이 필요 없다. 폴리곤은 선정반경으로 만든
  원의 근사이므로 **중심점 + 유형별 반경**으로 매칭한다(폴리곤 교차 판정 불필요).
- **표준데이터 파일의 폴리곤은 EPSG:5179**이고 `key`에 따옴표가 없어 JSON 파싱이 안 된다.
  그래서 파일에서는 위도/경도(WGS84)만 쓴다.

### 소스 구성

| 소스 | 형태 | 좌표 | 비고 |
|---|---|---|---|
| 사고다발 5종 | data.go.kr API | 4326 | 경로가 지나는 시군구만 조회 |
| 보행자 사고다발 | KOROAD 포털 API | 4326 | 별도 authKey |
| 무인단속카메라 | 파일 43,347행 | WGS84 | **속도 단속만** 11,956행 적재 (주정차·전용차로는 제한속도 0) |
| 어린이보호구역 | 파일 14,652행 | WGS84 | 제한속도 필드 없음 |
| 노인·장애인보호구역 | 파일 4,120행 | WGS84 | 제한속도 있음 |
| 스쿨존어린이 사고다발 | 파일 531행 | WGS84 | API가 못 주는 유형 보완 |

### 매칭

파일 소스는 기동 시 **0.01도 격자 색인**(31,259건 / 12,223셀, 0.3초)으로 올린다. 경로 200점 간격으로
주변 셀만 훑어 후보를 뽑고, 경로선까지 거리가 유형별 반경 이내인 것만 남긴다. 매칭 자체는 0.03초.

API 조회는 **병렬 8**로 던진다(순차 34회 113초 → 병렬 약 20초). 시군구는 경로를 5등분해 역지오코딩으로 얻는다.

### 야간은 비운다 (D6 유지)

지점 단위 야간 교통사고 데이터는 **공개된 것이 없다**(리서치 확인). 리서치가 제안한
"보행자 다발지역 + 일몰 가중치"는 휴리스틱이라 D1과 충돌하므로 **채택하지 않는다.**
서버가 `night_status` 고정 문구를 내려보내고, LLM 프롬프트는 야간 언급을 금지한다.
결빙 사고다발 fact가 있을 때만 겨울·우천 주의로 연결한다.
