# API 발급 요청 브리핑 — 장소(POI) 검색

> 다른 Claude Code 세션(브라우저 통제 가능)에 넘기는 작업 지시서.
> 작성: 2026-09-10 / 프로젝트: `route-guide (프로젝트 루트)`

---

## 1. 현재 상태 (실호출로 검증 완료)

NCP Maps 키는 **이미 발급되어 있고 정상 동작**한다. `.env`에
`NCP_MAPS_CLIENT_ID` / `NCP_MAPS_CLIENT_SECRET`로 들어 있다.

| API | 엔드포인트 | 상태 |
|---|---|---|
| Geocoding | `GET https://maps.apigw.ntruss.com/map-geocode/v2/geocode` | ✅ 200 |
| Reverse Geocoding | `GET https://maps.apigw.ntruss.com/map-reversegeocode/v2/gc` | ✅ 200 |
| Directions 5 | `GET https://maps.apigw.ntruss.com/map-direction/v1/driving` | ✅ 200 |
| Directions 15 | `GET https://maps.apigw.ntruss.com/map-direction-15/v1/driving` | ✅ 200 |
| Static Map | `GET https://maps.apigw.ntruss.com/map-static/v2/raster` | ✅ 200 |
| Web Dynamic Map | `oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=…` | ✅ localhost:3000에서 인증 통과 |

**→ NCP 쪽에서 추가로 신청하거나 발급받을 것은 없다.**

## 2. 문제

구현하려는 UX:

```
(1) 사용자가 검색어 입력 → 장소 후보 리스트 → 하나 선택   ← ❌ 막힘
(2) 도착지도 동일                                          ← ❌ 막힘
(3) 선택된 좌표로 Directions 호출                          ← ✅ 이미 됨
```

**막히는 이유**: NCP Maps 상품군에 **장소(POI)·키워드 검색 API가 없다.**
공식 Maps 개요 문서의 상품 목록은 Web/Mobile Dynamic Map, Static Map,
Directions 5/15, Geocoding, Reverse Geocoding, 지도앱 URL Scheme이 전부다.

Geocoding은 **주소 검색이지 장소 검색이 아니다.** 실측:

```
query="죽전역"      → totalCount=0   ❌
query="강남역"      → totalCount=0   ❌
query="중앙로 100"  → totalCount=36  ✅ (후보 리스트 + page/count 페이징 가능)
```

즉 **주소로 검색하는 리스트 UI는 지금 API로 이미 만들 수 있다.**
안 되는 건 "죽전역" 같은 **장소명·상호·랜드마크** 검색뿐이다.

### ⚠️ 함정: NCP 상품 페이지의 `Places` 항목에 속지 말 것

ncloud.com 상품 페이지(`/product/applicationService/maps`)의 '상세 기능' 표에는
**`Places`라는 상품 구분이 존재한다.** 이름만 보면 장소 검색 같지만 **아니다.**

상품 페이지 표 원문:

| 상품 구분 | 상품 설명 | 상품명 |
|---|---|---|
| Maps | 정적/동적 지도 | Dynamic Map, Static Map |
| Directions | 출발지→목적지 최적 경로 | Directions |
| **Places** | **"지번, 도로명을 질의어로 주소의 좌표값과 세부 정보 제공, 네이버 지도에서 좌표를 주소 정보로 변환하는 서비스 가능"** | **Geocoding, Reverse Geocoding** |
| Map Styling | 지도 테마 커스터마이징 | Map Style Editor |

`Places`는 **개별 API가 아니라 카테고리 이름**이고, 그 안에 든 것은
**이미 발급받아 쓰고 있는 Geocoding + Reverse Geocoding 둘뿐**이다
(표에서 `Places` 셀의 `rowSpan`이 정확히 그 2행만 덮는다).
상품 설명 자체가 **"지번, 도로명을 질의어로"** 라고 못박고 있다 — 질의어는 장소명이 아니라 주소다.

**→ 콘솔이나 상품 페이지에서 `Places`를 보고 "장소 검색이 이미 있다"고 판단하지 말 것.
NCP에서 추가로 신청할 상품은 여전히 없다.**

## 3. 발급받은 것 ✅ (2026-09-10 완료)

> **정정**: 최초 브리핑은 developers.naver.com의 검색 오픈API를 지목했으나 **틀렸다.**
> 실제 경로는 **NCP 콘솔 > NAVER API HUB**다. NCP 안에서 해결된다.

| 항목 | 값 |
|---|---|
| 플랫폼 | **NCP 콘솔 > NAVER API HUB** (Maps와 같은 콘솔, 다른 상품) |
| Application | `route-guide` (2026-09-10 15:13:57 등록) |
| 사용 API | **지역 검색 (Local Search)** |
| 엔드포인트 | `GET https://naverapihub.apigw.ntruss.com/search/v1/local` |
| 인증 헤더 | `X-NCP-APIGW-API-KEY-ID`, `X-NCP-APIGW-API-KEY` |
| Client ID | `<NAVER_HUB_CLIENT_ID>` |
| 쿼터 | **일 25,000건 / 월 775,000건, 무료** |
| 콘솔 | https://console.ncloud.com/naver-api-hub/application |

> ⚠️ **Maps 키(`<NCP_MAPS_CLIENT_ID>`)와 다른 키다.** 같은 콘솔·같은 헤더 형식이지만
> Application이 별개라 키도 별개. 섞어 쓰면 인증 실패한다.

`.env` 항목 (Secret은 콘솔 > NAVER API HUB > route-guide > 인증 정보에서 복사):

```
NAVER_HUB_CLIENT_ID=<NAVER_HUB_CLIENT_ID>
NAVER_HUB_CLIENT_SECRET=<콘솔에서 복사>
```

## 4. 스펙 확인 결과 — 실측 완료 (2026-09-10)

**문서 기반 답 중 2개(E, F)가 실측과 달랐다.** 아래가 확정판이다.

| # | 항목 | 실측 결과 |
|---|---|---|
| A | `mapx`/`mapy` 좌표계 | **WGS84 × 10⁷ 정수 문자열.** `float(v)/1e7` 필요<br>예: `"1271073977"` → `127.1073977` |
| B | `display` 상한 | **1~5, 기본 1** (문서와 일치) |
| C | 쿼터 | 일 25,000 / 월 775,000, 무료 (문서) |
| D | 검색 품질 | **양호.** `죽전역`→1위 "죽전역 수인분당선", `강남역`→1·2위가 신분당선/2호선 강남역.<br>단 3~5위는 무관한 상호가 섞인다 |
| E | `title`의 HTML 태그 | ❌ **문서 기반 답이 틀림. `<b>` 태그가 실제로 들어온다.**<br>`"<b>죽전역</b> 수인분당선"` → **스트립 필수** |
| F | `start` 페이징 | ❌ **문서 기반 답이 틀림. 페이징 불가.**<br>`start=3`/`start=6` 모두 무시되고 응답이 `start:1`로 고정 |

### A 좌표 교차 검증 (통과)

`죽전역` 1위 항목 `mapx=1271073977, mapy=373245825` → `127.1073977, 37.3245825`

Reverse Geocoding 결과: **경기도 용인시 수지구 죽전동 1287**
기준 좌표(127.1076, 37.3245)와 **오차 20m** — 동일 건물. 변환식 확정.

### ⚠️ `total`은 총 건수가 아니다

`total` 값이 `display`와 항상 같게 돌아온다 (`display=1`→`total=1`, `display=5`→`total=5`).
**반환 건수일 뿐 전체 검색 결과 수가 아니다.** "N건 중 5건" 같은 UI는 만들 수 없다.

### 결론: 최대 5건, 페이징 없음, 총건수 없음

이게 이 API의 하드 제약이다. B·F·`total`이 전부 같은 방향으로 걸린다.

### 그 외 확인된 필드 동작

- **`telephone`은 항상 빈 문자열** (문서에 "값을 반환하지 않는 요소"로 명시)
- `link`, `description`도 자주 빈 값 — 지하철역 항목은 둘 다 비어 있었다
- `category`는 `"교통,운수>지하철,전철"` 처럼 `>` 로 구분된 계층 문자열.
  **역·터미널만 걸러내려면 `교통,운수>` 접두사로 필터링 가능** (5건 제약 완화에 유용)
- `address`(지번) / `roadAddress`(도로명) 둘 다 채워져 온다
- `sort` = `random`(기본) | `comment`

### 실측 샘플

```
query=강남역, display=5
 1. <b>강남역</b> 신분당선        교통,운수>지하철,전철   127.0283493, 37.4964196
 2. <b>강남역</b> 2호선          교통,운수>지하철,전철   127.0276242, 37.4979526
 3. 치폴레 강남점                음식점>멕시코,남미음식   127.0261135, 37.5003205
 4. 비단구술 강남본점             술집>요리주점          127.0251188, 37.5012732
 5. 준오헤어 <b>강남역</b>스퀘어2호점  미용>미용실           127.0280942, 37.4987099
```

신분당선 강남역과 2호선 강남역이 **좌표가 180m 다르다.** 사용자 선택이 실제로 의미가 있다는
근거이자, Geocoding만으로는 불가능했던 지점이다.

## 5. 발급 완료 후 넘겨줄 것

`.env`에 아래 두 줄 추가 (이 파일은 `.gitignore`에 등록되어 있어 커밋되지 않음):

```
NAVER_SEARCH_CLIENT_ID=...
NAVER_SEARCH_CLIENT_SECRET=...
```

그리고 **4번 표의 A~F 답**을 알려줄 것. 그걸 받으면
`검색어 → 후보 리스트 → 선택 → Directions` 단계를 기존 코드에 붙인다.

## 6. 발급이 안 되거나 조건이 안 맞을 경우

- **지역검색 쿼터·`display=5` 제약이 치명적이면**: 출발/도착이 역·터미널 등
  정해진 범주라면 공공데이터포털의 역 좌표 테이블을 로컬 DB로 두는 편이 낫다.
  외부 API 의존도 쿼터도 없다. 현재 `run_scenario.py`의 `PLACES` 하드코딩이 그 축소판.
- **장소 검색을 포기해도 되면**: Geocoding의 후보 리스트(`count` 최대 100 + `page`)로
  **주소 기반 선택 UI**는 추가 발급 없이 지금 당장 구현 가능하다.
