# 계기판이 「판정 불가」를 찍는 동안, 답은 **이미 API 에 있었다**

sid=7af9eaa2 (development-ai-a4) · 2026-09-12 · 통합자 레인

## 0. 옵시디언 조회 — ★**조회 불가**(「없음」이 아니다)

    ls /mnt/d/옵시디언기록/...   → No such device        (대조군 ls /mnt/c/Users → 정상)
    mount | grep /mnt/d          → 9p 마운트는 **살아 있다** (전송만 끊김)

처방(`wsl --shutdown`)은 **사용자 결정**이라 세션이 돌리지 않는다. 동료 2세션이 같은 증상을
독립 보고했다. ⇒ 이 항목은 **미수행**이다. 볼트 복구 후 대조가 필요하다.

## 1. ★이 계획서의 1차 판이 **틀렸다** — 그 기록이 본문보다 값지다

처음 쓴 계획은 *「분석 배치의 실행 기록이 없으니 `platform_events` 에 `analyze_run` 을 남기자」*
였다. 코드까지 썼다. **전제가 통째로 거짓이었다.**

| 내가 한 조회 | 왜 0건이 나왔나 |
|---|---|
| `grep -rn "INSERT INTO platform_events" app/services/growth/` | ★**매체로 찾았다.** 생산자는 `platform_settings` 에 쓴다 |
| `grep -n '@router\.(get\|post)' app/routers/growth.py` | 전용 엔드포인트가 아니라 **`/heal-log` 의 `active_flags`** 로 나간다 |
| 위 둘을 **공유 메인 워크트리**에서 돌림 | 그 트리는 **origin/main 보다 39커밋 뒤**였다 |

**실제로 이미 있는 것**(라이브 실측 2026-09-12 08:25Z · `GET /growth/heal-log`):

    growth_analysis        {"at":"2026-09-12T08:05:05Z","axes":"fal 0/0 lat 0/19 pay 0/1 qua 0/0",
                            "state":"starved","insights":0}     ttl=11:05:05Z
    growth_last_run.analyze "2026-09-12T08:02:22Z"              ttl=None

`analyzer.py:656-700` 에 `ANALYSIS_STATUS_SETTING_KEY` · `analysis_status_payload()`(순수 함수) ·
`publish_analysis_status()` 가 **전부 있고**, 세 상태(`judged`/`starved`/`idle`)와
TTL 산수(주기 60분 · TTL 180분 ⇒ **행 부재 = 3회 연속 미실행 = 고장**)까지 주석에 박혀 있다.
프론트 소비처도 있다(`GrowthDashboard.tsx`).

> ★**교훈**: *「없다」는 결론이 아니라 조회 결과다.* 나는 **목적**(*"분석 배치가 자기 실행을
> 어디에 남기는가"*)이 아니라 **매체**(`INSERT INTO platform_events`)로 찾았다.
> 그리고 `capture_service.py:447` 에는 ***「★새 표면을 만들지 않는다 — `growth_last_run.*`
> 워터마크가 이미 쓰는 통로」***라고 **저장소가 미리 적어 두었다.**
> ★내 전제를 깬 것은 소스가 아니라 **라이브 응답**이었다.

## 2. 그래서 **진짜 결함은 하나만 남는다** — 소비처

계기판 ③ 은 인사이트 24h 창이 0 이면 이렇게 찍는다:

    ★판정 불가 — 술어는 살아 있는데 24h 창이 0 이다 = **시스템 유휴**
    (exit 4)

**정직하지만 답이 아니다.** 답은 인증된 GET 하나 거리에 있었다 — `state="starved"` ·
`axes="fal 0/0 lat 0/19 pay 0/1 qua 0/0"` · `at=08:05Z`. 즉 **배치는 돌았고, 모든 축이
표본 하한 미달**이다. 이것은 「고장」이 아니라 **정상 유휴**이고, 그 판정은 사람이
SSH 로 로그를 캐지 않아도 된다.

### 전제 표

| # | 전제 | 확인 방법 | 결과(실측) |
|---|---|---|---|
| P1 | 계기판·프로브가 이 값을 **안 읽는다** | `grep -e growth_analysis -e starved scripts/monitor/` | **0건**. ★대조군 `platform_insights` = 프로브에 **5건**(조회기 생존) |
| P2 | 프론트는 읽는다(즉 «소비처 0» 이 아니다) | 같은 패턴을 `apps/web` 에 | `GrowthDashboard.tsx` **있음** |
| P3 | 지금 라이브 상태 | `GET /growth/heal-log` | `state=starved` · `insights=0` · `at=08:05:05Z` · 워터마크 08:02:22Z |
| P4 | 인사이트가 실제로 끊겼나 | `GET /growth/insights?sort=created_at&limit=500` | 최신 09-11T17:30Z · **09-12 0건**. ★정렬 방향을 `limit=5` 로 **먼저** 확인(desc) — 안 했으면 LIMIT 절단을 부재로 읽을 뻔 |
| P5 | 트래픽이 0이라 유휴인가 | 계기판 ③-2 `scanned_buckets` | **96버킷/6h** — 트래픽 있음. ★`worst_p95_ms=0` 은 「무트래픽」이 아니라 「버스트 없음」 |
| P6 | 치유가 캡에 막힌 건가 | `GET /growth/heal-log` | `blocked_total=0` · 마지막 액션 09-04 ⇒ **막힌 게 아니라 대상이 없다** |

## 3. 변경 내용과 회귀가 아닌 근거

1. `scripts/monitor/growth_stale_producer_probe.py` — **기존 프로브를 확장**한다(새 도구 금지).
   `platform_settings` 에서 `growth_analysis` 와 `growth_last_run.analyze` 를 읽어
   `astate=… aat=… aaxes=… ains=… alast=…` 를 같은 `PROBE` 줄에 덧붙인다.
2. 순수 함수 `analysis_verdict(astate, ains24h)` — 계기판의 **가름 규칙**을 셸이 아니라
   파이썬 순수 함수가 정한다(형제 `is_stale_stack`·`classify_buckets` 와 같은 구조).
3. `integrator_dashboard.sh ③` — 「판정 불가」 자리를 **네 갈래**로 가른다:
   `starved`(정상 유휴·설명 있음) / `judged`(판정했는데 창이 비었다 → 이상) /
   `idle`(축 자체가 없다 → 이상) / **행 부재**(3회 연속 미실행 → 이상).

**회귀가 아닌 근거**: 프로브는 **읽기 전용 SELECT** 만 추가한다. 기존 `PROBE` 필드는
이름·순서를 **바꾸지 않는다**(계기판이 `sed -n 's/.*overlap=//p'` 처럼 이름으로 뽑으므로
덧붙이기만 안전하다). 계기판은 **옛 프로브 사본이 돌면 새 필드가 비는데**, 그때는
`overlap` 과 같은 규율로 **DEAD 가 아니라 「필드 없음」을 명시**한다(§27 침묵 금지).

## 4. ★검증하지 못한 것

- **왜 09-09 이후 인사이트가 급감했는가** — 이 PR 은 답하지 않는다. `starved` 는 「표본 하한
  미달」을 말할 뿐 **트래픽이 왜 줄었는지**는 다른 축이다. **미측정**으로 남긴다.
- **`state=judged` 인데 창이 0** 인 모집단을 라이브에서 본 적이 없다(오늘은 `starved` 뿐).
  락은 **합성 입력**으로 태운다 — 라이브 관측은 **미수행**.
- 라이브 DB 직접 조회는 이 세션 권한에서 **SSH 차단**이라 못 했다. 전부 **API 경유 관측**이다.
- 폐기한 1차 구현은 `git stash` 에 남겨 뒀다(사유 포함) — **지우지 않았다.**

## 5. 되돌리기 경로

`git revert <머지커밋>` 한 번. **런타임 코드 0** — `scripts/monitor/` 와 테스트뿐이라
배포가 필요 없다(api·web 델타 모두 0). 계기판은 저장소 파일이라 머지 즉시 유효하다.

## 6. 잠금

| 잠글 것 | 검사 |
|---|---|
| 네 모집단(`starved`/`judged`/`idle`/행 부재)이 **서로 다른 판정** | `tests/test_dashboard_analysis_axis.py` — 4입력 **상호 판별** 단언 |
| 「행 부재」를 **정상 유휴로 읽지 않는다** | 같은 파일 — 부재 → 이상(`obs`) |
| 프로브가 옛 사본이면 **0 으로 읽지 않는다** | 같은 파일 — 필드 없음 → `unknown`(≠ 정상) |
| 계기판이 그 함수를 **실제로 태운다** | `--verdict-lib` 경유 셸 락(기존 `test_dashboard_delta_axis.py` 와 같은 방식) |

★변이: `scripts/mutate_changed.py --tests <경로>` + **첨가 축**은 손수
(`analysis_verdict` 가 무조건 `ok` 를 반환 · 네 상태를 한 값으로 접기) — 기계 변이는
**삭제 축만** 만든다.
