# 내 도메인으로 폰에서 접속하기 — Cloudflare Tunnel + Access 가이드

> 목표: `https://route.<내도메인>` 을 폰 브라우저로 열면 **내 이메일 인증을 통과한 나만** 맥에서 돌고 있는
> 길찾기 서비스(`localhost:3000`)를 쓸 수 있게 한다. 앱 설치 없음, 공유기 포트 개방 없음.
>
> 작성 2026-10-05. 대시보드 메뉴 이름은 Cloudflare 공식 문서(2026-10 확인) 기준이다. 화면이 조금 다르면
> 같은 이름의 메뉴를 찾으면 된다.

---

## 0. 먼저 전체 그림

```
폰 브라우저
   │  https://route.<내도메인>
   ▼
Cloudflare 관문 ──[Access] 내 이메일 인증 통과? ── 아니면 여기서 끝 (맥까지 아무것도 안 감)
   │ 통과
   ▼
Tunnel (맥이 Cloudflare 쪽으로 먼저 맺어 둔 연결)
   ▼
맥의 cloudflared → http://localhost:3000 (serve.py)
```

| 구성 | 누가 | 어디서 |
|---|---|---|
| 도메인 DNS | Cloudflare | 대시보드 |
| 인증(누가 들어오나) | **Access** | Zero Trust 대시보드 — 코드 작업 없음 |
| 연결(통로) | **Tunnel / cloudflared** | Networking 대시보드 + 맥에 설치 |
| 서비스 | serve.py | 맥 (지금 그대로) |

**가장 중요한 원칙: Access(잠금)를 먼저 만들고, 그다음에 Tunnel 주소를 연다.**
Tunnel 만 있고 Access 가 없으면 그 주소는 누구나 들어오는 공개 사이트가 된다.
이 서비스는 요청마다 Claude 사용량·NCP 요금·크롬 실행이 생기므로 잠금 없이 열면 안 된다.

### 준비물
- [ ] Cloudflare 계정 (무료) — https://dash.cloudflare.com
- [ ] 내 도메인 1개 (없으면 1단계 참고)
- [ ] 이 맥에 Homebrew (`brew --version` 으로 확인)
- [ ] 로그인 코드를 받을 내 이메일 주소
- [ ] NCP 콘솔 로그인 (지도 키에 새 주소 등록용)

예상 시간: 도메인이 이미 Cloudflare 에 있으면 30분. 네임서버를 옮겨야 하면 반영 대기 시간이 더해진다(보통 수십 분~몇 시간, 길면 하루).

---

## 1단계. 도메인을 Cloudflare 에 연결

> 이미 Cloudflare 에서 관리 중인 도메인이면 건너뛴다.
> 도메인이 없다면 Cloudflare 대시보드의 **Domain Registration** 에서 사서 바로 쓰는 것이 가장 간단하다(이 단계 자동 완료).

1. Cloudflare 대시보드 → **Onboard a domain** → 내 도메인(예: `example.com`, 앞에 `www` 없이) 입력 → **Free** 요금제 선택.
2. DNS 레코드 목록이 나오면 기존 레코드(홈페이지, 메일 등)가 빠짐없이 들어왔는지 확인한다. 자동 스캔이 일부를 놓칠 수 있다.
3. Cloudflare 가 알려 주는 **네임서버 2개**를 복사한다.
4. 도메인을 산 곳(가비아, 후이즈, Namecheap 등)의 관리 화면에서 네임서버를 그 2개로 바꾼다.
   - ⚠️ 그 도메인에 **DNSSEC 이 켜져 있으면 먼저 끈다.** 켠 채로 바꾸면 도메인이 먹통이 될 수 있다(나중에 Cloudflare 에서 다시 켤 수 있음).
5. Cloudflare 대시보드에서 도메인 상태가 **Active** 가 될 때까지 기다린다(메일로도 알려 줌).

✅ 확인: 도메인 개요 화면에 Active 표시.

---

## 2단계. 잠금(Access) 먼저 만들기

### 2-1. 로그인 방법: 이메일 일회용 코드 켜기
1. **Zero Trust** → **Integrations** → **Identity providers**
2. **Add new identity provider** → **One-time PIN** 선택 → 저장.

> 구글 계정으로 로그인하고 싶으면 여기서 Google 도 추가할 수 있다. 처음엔 One-time PIN 하나로 충분하다.

### 2-2. 보호할 주소(애플리케이션) 만들기
1. **Zero Trust** → **Access controls** → **Applications** → **Create new application**
2. **Self-hosted and private** 선택 → **Add public hostname**
   - Subdomain: `route` (원하는 이름)
   - Domain: 1단계에서 연결한 내 도메인 선택
   - → 이 주소(`route.<내도메인>`)가 앞으로 폰에서 열 주소다.
3. **Access policies** 에서 새 정책 만들기:
   - Policy name: `나만`
   - Action: **Allow**
   - Include → Selector: **Emails** → 값: `내이메일@example.com` (정확히 이 주소만 허용)
   - ⚠️ `Emails ending in` 이나 `Everyone` 을 고르지 말 것.
4. 로그인 방법(identity providers)에서 **One-time PIN** 이 선택돼 있는지 확인.
5. **Session Duration**: 폰에서 다시 로그인하는 주기. 목록에서 `1 month` 정도를 고르면 한 달에 한 번만 코드를 넣으면 된다.
   (분실한 폰이 걱정되면 `1 week` 처럼 짧게)
6. **Create**.

✅ 확인: Applications 목록에 `route.<내도메인>` 이 보인다.
(아직 Tunnel 이 없으므로 접속하면 로그인 후 오류 화면이 나오는 게 정상이다.)

---

## 3단계. 통로(Tunnel) 만들고 맥에 커넥터 설치

1. Cloudflare 대시보드 → **Networking** → **Tunnels** → **Create a tunnel**
2. 이름: `route-guide-mac` → **Create Tunnel**
3. 운영체제로 **macOS** 선택 → 화면에 나오는 설치 명령을 복사한다. 보통 이런 모양이다:
   ```bash
   brew install cloudflared
   sudo cloudflared service install <긴 토큰 문자열>
   ```
   - `sudo ... service install` 은 맥이 켜질 때 cloudflared 가 자동으로 실행되게 등록한다
     (`/Library/LaunchDaemons/com.cloudflare.cloudflared.plist`).
   - ⚠️ **토큰은 비밀번호와 같다.** 메모·채팅·깃 저장소 어디에도 붙여 두지 말 것. 유출되면 대시보드에서 토큰을 재발급한다.
4. 맥 터미널에 붙여 넣고 실행(맥 비밀번호 입력).
5. 대시보드 화면에 커넥터가 **Connected / Healthy** 로 뜨면 **Continue**.

✅ 확인: Tunnels 목록에서 `route-guide-mac` 상태가 Healthy.
문제 시 로그: `/Library/Logs/com.cloudflare.cloudflared.err.log`

---

## 4단계. 주소를 맥의 서비스로 연결

1. **Networking** → **Tunnels** → `route-guide-mac` 선택 → **Routes** 탭
2. **Add route** → **Published application**
   - Subdomain: `route` (2단계와 **같은** 이름)
   - Domain: 내 도메인
   - Service URL: `http://localhost:3000`
3. **Add route**.

> serve.py 는 지금처럼 `127.0.0.1:3000` 에서만 듣게 둔다. **`0.0.0.0` 으로 바꾸거나 공유기 포트를 열지 않는다.**
> cloudflared 가 같은 맥 안에서 localhost 로 전달하므로 그럴 필요가 없다.

✅ 확인: 4단계가 끝난 순간부터 주소가 살아난다. 2단계 Access 가 이미 걸려 있으므로 잠긴 상태로 열린다.

---

## 5단계. NCP 지도 키에 새 주소 등록

지도 인증 키(ncpKeyId)는 등록된 주소에서만 통과한다. 안 하면 **로그인은 되는데 지도만 안 뜬다.**

1. NCP 콘솔 → Maps → Application → 이 서비스의 Application **변경**
2. **서비스 환경 → Web 서비스 URL** 에 `https://route.<내도메인>` 추가 (기존 `http://localhost:3000` 은 그대로 둔다 — 로드뷰 캡처가 localhost 를 쓴다)
3. 저장.

---

## 6단계. 맥을 항상 켜 두기

밖에서 접속하려면 맥과 serve.py 가 계속 살아 있어야 한다.

### 6-1. 잠자기 방지
- **시스템 설정 → 에너지(또는 배터리) → 전원 어댑터** 에서 "디스플레이가 꺼져 있을 때 자동으로 잠자기 방지"를 켠다.
- 맥북이면 **전원 연결 상태**로 둔다. 덮개를 닫으면 잠들 수 있다(외부 모니터 없이 덮개를 닫는 구성은 피하는 게 안전).

### 6-2. serve.py 자동 실행
지금은 터미널에서 직접 켜야 한다. 재부팅 후에도 자동으로 켜지게 하려면 **사용자 로그인 시 실행(LaunchAgent)** 으로 등록한다.
(Claude Code 로그인 정보와 크롬이 내 사용자 계정에 있으므로 `sudo`/root 로 돌리지 않는다.)

→ 이 설정 파일은 제가 만들어 드릴 수 있다(아래 8단계 ①).

---

## 7단계. 확인 테스트 (순서대로)

| # | 하는 일 | 기대 결과 |
|---|---|---|
| 1 | 폰을 **와이파이 끄고 LTE** 로 `https://route.<내도메인>` 접속 | Cloudflare 로그인 화면(이메일 입력) |
| 2 | **다른 이메일** 입력 → Send login code | "코드를 보냈다"고 나오지만 **메일이 오지 않음** (정상: 차단됨) |
| 3 | 내 이메일 입력 → 메일로 온 6자리 코드 입력 (10분 유효, 1회용) | 길찾기 화면 |
| 4 | 지도·경로 카드가 뜨는지 | 지도 안 뜨면 5단계 확인 |
| 5 | 경로 비교 → AI 설명이 끝까지 나오는지 (1~2분) | 중간에 끊기면 8단계 ② |
| 6 | 출발 전 브리핑 → ⬇ 저장 | 로드뷰 사진 담긴 파일 저장 |
| 7 | 폰을 껐다 켜고 다시 접속 | 로그인 없이 바로 열림 (세션 유지) |
| 8 | 맥 재부팅 후 다시 접속 | 열림 (6단계 자동 실행 확인) |

---

## 8단계. 서비스 쪽 보완 (제가 할 수 있는 작업)

계정 작업(1~5단계)은 직접 하셔야 하고, 아래는 코드·설정이라 제가 만들 수 있다.

| # | 작업 | 왜 |
|---|---|---|
| ① | **serve.py 자동 실행 설정**(LaunchAgent plist + 설치/해제 명령) | 재부팅해도 서비스가 켜지게 |
| ② | **AI 설명 스트림에 15초마다 '살아 있음' 신호** | Cloudflare 는 서버가 **100초 동안 아무것도 안 보내면 연결을 끊는다(524 오류)**. AI 가 오래 생각하거나 재시도 대기 중이면 걸릴 수 있다 |
| ③ | **Access 토큰 확인(이중 잠금)** | Access 를 통과한 요청에는 Cloudflare 가 서명한 `Cf-Access-Jwt-Assertion` 헤더가 붙는다. serve.py 가 이 서명을 확인해서 없으면 거절 → 설정 실수로 Access 가 빠져도 뚫리지 않음. localhost 직접 접속(로드뷰 캡처)은 예외 |
| ④ | **하루 사용량 상한** (AI 설명 N회, 로드뷰 캡처 N장) | 만약 뚫려도 비용이 무한정 나가지 않게 |

추천: ①② 는 필수에 가깝고, ③④ 는 안전장치.

---

## 문제 해결

| 증상 | 원인·조치 |
|---|---|
| 주소가 아예 안 열림 (DNS 오류) | 1단계 도메인이 Active 인지, 4단계 route 가 만들어졌는지 |
| Cloudflare 오류 **1033** / 502 | 맥의 cloudflared 가 꺼짐 → Tunnels 상태 확인, `sudo launchctl start com.cloudflare.cloudflared` |
| **502 Bad Gateway** (Tunnel 은 Healthy) | serve.py 가 꺼짐 → 맥에서 `python3 serve.py` 또는 6-2 자동 실행 확인 |
| 로그인 코드 메일이 안 옴 | 스팸함 확인 / 2단계 정책의 이메일 철자 / 다른 메일이면 정상 차단 |
| 코드가 "이미 사용됨" | 메일 보안 프로그램이 링크를 먼저 열어 본 경우 → Request new code |
| 로그인 후 지도만 안 뜸 | 5단계 NCP Web 서비스 URL 에 `https://route.<내도메인>` 등록 |
| AI 설명이 1~2분 뒤 끊김 (524) | 8단계 ② 적용 |
| 접속은 되는데 아무 동작이 느림 | 맥이 잠들었다 깨는 중 → 6-1 확인 |

## 하지 말 것
- ❌ Access 없이 Tunnel route 만 만들기 (주소가 누구에게나 열린다)
- ❌ 정책에 `Everyone` / `Emails ending in @gmail.com` 사용
- ❌ serve.py 를 `0.0.0.0` 으로 바꾸거나 공유기 포트 포워딩
- ❌ Tunnel 토큰을 저장소·메모에 저장 (이 문서에도 적지 않는다)
- ❌ `trycloudflare.com` 임시 주소(Quick Tunnel) 사용 — Access 를 붙일 수 없다

## 참고 (공식 문서)
- 원격 관리 Tunnel 만들기: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/
- Self-hosted 애플리케이션: https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-public-app/
- One-time PIN: https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/
- Access 정책: https://developers.cloudflare.com/cloudflare-one/access-controls/policies/
- 도메인 연결: https://developers.cloudflare.com/fundamentals/manage-domains/add-site/
- macOS 서비스 실행: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/as-a-service/macos/
- SSE 와 524(100초) 제한: https://community.cloudflare.com/t/are-server-sent-events-sse-supported-or-will-they-trigger-http-524-timeouts/499621
