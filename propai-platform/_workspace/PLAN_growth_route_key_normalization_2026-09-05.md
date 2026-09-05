# 성장루프 라우트 키 정규화 — 한 라우트가 두 어휘로 갈린다

- 세션: development-ai-cd [863fc5] · **sid=79cfa3eb** (이름 이력 8f → 91 → cd)
- 날짜: 2026-09-05 · 브랜치 `fix/growth-route-key-normalization`
- 보드 claim: `growth-route-key-normalization`

## 0. 옵시디언 조회 결과 (§0)

Vault `/mnt/d/옵시디언기록/나의-모든-기록-최적화본` (9p 복구됨 · 748파일).

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | `analyzer.py:98~130` 이 이 route 군의 **임계 변경을 이미 기각**(MAD 스케일 → 실효임계 166초 → 가장 망가진 route 가 발화 불가 = 굿하트). **임계는 건드리지 않는다.** |
| **같은 클래스의 앞선 결함** | `2026-09-02_침묵이_무엇인지_말해주는_것이_침묵과_함께_사라진다.md` — `recurring_verify_error` 포함 3종은 **커버리지 축이 없다** · «`status=open` 을 나이와 무관하게 그려 **낡은 가득 찬 화면**으로 위장한다». `2026-08-24_내가_만든_통로에_읽는_쪽이_없었다.md` — 새 이벤트 타입은 수집되나 **조회되지 않는다** |
| **미결·부채** | 위 두 건 모두 «커버리지 축 부재»를 부채로 남김 |
| **이전 판단의 근거** | `insight_types.py:110~145` 가 `IDENTITY_FIELDS` 를 **선언으로** 두고, 단일 필드가 부족했던 사고(`recurring_verify_error` 를 `service` 하나로 물어 서로를 승계)를 기록 |

★**이 결함(생산자별 키 어휘 분열)을 다룬 기록은 볼트에 없음.** 신규다.

## 1. 전제 표 — 전부 실측 (2026-09-05 16:3x~16:5x KST)

| # | 전제 | 확인 방법 | **결과** |
|---|---|---|---|
| 1 | 서버 미들웨어는 라우트를 정규화한다 | `growth_telemetry.py:50` 원문 (이 PR 이 `normalize_route` 로 **공개 승격**) | **참** — `/api/v\d+` 접두사 보존 + UUID·16자리+·숫자 → `{id}` |
| 2 | 웹 클라이언트는 정규화하지 않는다 | `api-client.ts:12~33` 원문 | **참** — `path.split("?")[0]` **쿼리스트링만** 제거 |
| 3 | 웹 요청은 **항상** `/api/v1` 을 붙인다 | `api-client.ts:208` `getRequestUrl` | **참(구조적)** — `${origin}/api/v1${normalizedPath}`. `trackApiCall` 은 그 **앞의** 상대경로를 받는다(423·430행) |
| 4 | 그 결과 같은 라우트가 두 키로 갈린다 | 라이브 `GET /growth/insights?sort=created_at&limit=500` 전수 | **참 — 9쌍**. `/store/projects` bare 17행(open 7) ↔ `/api/v1/store/projects` 20행(open 7) = **한 라우트 open 14건** |
| 5 | 웹 키는 id 가 원시로 남는다 | 같은 응답의 `metrics_json.key` 전수 | **참** — `/registry/analyze/jobs/0f1f795ca34a42dbb4c73e16ff7ce343` · `/projects/c974ebf3-…` · `/analysis/interpretation/interp_…` |
| 6 | 승계는 `key` 로 판정한다 | `insight_types.py:IDENTITY_FIELDS` | **참** — `"latency_regression": ("key",)`. 접두사가 다르면 **원리적으로 승계 불가** |
| 7 | 표본이 하한에 못 닿는다 | 인사이트 `metrics_json.analysis_coverage` | **참** — `latency_regression: total 464 · judged 32 · withheld 432 · judged_pct 6.9%` (floor 20) |
| 8 | `route` 를 싣는 웹 생산자 전수 | `trackEvent(` 호출 파생 조회 | **3곳** — `api-client.ts:18,25`(`api_error`/`api_call`) · `useGrowthEvents.ts:38`(`page_view`) |
| 9 | ★`page_view` 의 route 는 **다른 네임스페이스**다 | `useGrowthEvents.ts:38` = `route: pathname` | **참** — 브라우저 경로다. 여기에 `/api/v1` 을 붙이면 **거짓 라우트를 만든다** |
| 10 | 지연 분석 모집단 | `analyzer.py:947~952` 주석 | `api_call`·`llm_call` 만 읽는다 (`api_error` 는 error_cluster 쪽) |

### ★기각한 가설 (다음 사람이 다시 가지 않게)

*"분석기가 **개선을 회귀로 신고**한다"* — `/store/projects p95 30637ms (이전 baseline 54333ms)` 를 보고 그렇게 판정할 뻔했다.
**전문을 읽으니 발화 축은 `triggers:["absolute"]` = 평소값(4,770ms) 대비**이고 baseline 은 곁들인 참고값이다.
30.6초 vs 평소 4.8초는 **진짜 회귀**다. ⇒ **기각.** ★잘린 문장으로 판정하지 말 것.

## 2. 변경 내용과 회귀가 아닌 근거

**SSOT 를 한 곳으로 둔다 — 서버 수신부에서 정규화한다.**

- 왜 클라이언트가 아니라 서버인가: 정규화 규칙을 **두 벌로 구현하면 표류**한다(이 저장소가 반복해 데인 형태).
  서버는 이미 정본 구현(이 PR 에서 `normalize_route` 로 공개 승격)을 갖고 있고, 그것을 **재사용**한다 — 새 규칙을 만들지 않는다.
- 적용 범위는 **`api_call`·`api_error` 의 `route` 뿐**이다. `page_view` 는 전제 9 때문에 **건드리지 않는다**.
- 접두사 보정은 전제 3(구조적 보장)에 근거해 *"`/api/v` 로 시작하지 않으면 `/api/v1` 을 앞에 붙인다"* 로 한정한다.
- **과거 행은 고치지 않는다.** 승계는 새 관측이 들어오면 자연히 일어난다(정리 잡이 `key` 로 닫는다).

**회귀가 아닌 근거**: 서버 미들웨어가 만든 route 는 이미 `/api/v1…{id}` 형태라 이 변환의 **고정점**이다(멱등).
즉 서버발 이벤트는 값이 바뀌지 않고, 웹발 이벤트만 서버발과 **같은 어휘로 합류**한다.

## 3. ★검증하지 못한 것

1. **정규화 후 실제로 승계가 일어나는지** — 정리 잡(`insight_retention`)의 실제 실행 주기를 라이브에서 못 봤다. 사유=**장치 부재**(스케줄러 조회 권한 없음).
2. **`judged_pct` 가 얼마나 오르는지** — 두 모집단이 합쳐지면 표본이 늘지만, 하한 20 을 넘길지는 **미측정**. 합류 후 표본 수를 예측하지 않는다.
3. **`llm_call` 이벤트의 route 어휘** — 지연 모집단에 포함되는데(전제 10) 그 생산자를 이번에 조사하지 않았다. **범위 밖으로 명시**한다.
4. **다른 클라이언트(모바일·외부 호출)** 가 `/growth/events` 에 직접 쏘는지 — 미조사.
5. 과거 행을 안 고치므로 **당분간 두 어휘가 공존**한다. 그 기간 동안 open 이 얼마나 남는지 미측정.

## 4. 되돌리기 경로

수신부 정규화 한 함수의 호출을 제거하면 즉시 원복(런타임 데이터 마이그레이션 없음).
과거 행을 건드리지 않으므로 **되돌려도 잃는 데이터가 없다**.

## 5. 잠금 (이 변경을 지키는 검사)

1. **멱등 락** — 서버발 형태(`/api/v1/x/{id}`)를 넣으면 **값이 안 바뀐다**
2. **합류 락** — 웹발(`/x/<uuid>`)과 서버발(`/api/v1/x/{id}`)이 **같은 키로 수렴**한다(두 모집단을 같은 실행에서)
3. **★범위 락** — `page_view` 의 route 는 **변환되지 않는다**(전제 9). 이것이 없으면 브라우저 경로에 `/api/v1` 이 붙는 새 결함을 만든다
4. **음성 대조군** — 이미 `/api/v2` 로 시작하는 route 에 `/api/v1` 을 덧붙이지 않는다
5. **변이 확인** — 위 4종 각각에 변이를 넣어 CAUGHT 를 확인한다(`scripts/mutate_manual.sh`)

★부채: `llm_call` 어휘(§3-3)는 이번 범위 밖 — `it.todo`/`xfail` 로 **초록 안에 보이게** 남긴다.

## 6. 적대 검증(insight-loop) 결과 — 착수 후 자가 공격

| 렌즈 | 판정 | 근거 |
|---|---|---|
| ① 수신부에 삽입점이 있나 | **통과** | `routers/growth.py:ingest_events` 에 `"route": ev.route` **단일 지점** |
| ② ★route 를 바꾸면 `error_cluster` 시그니처가 깨지지 않나 | **적중 · 유계** | `normalize_stack(raw, route, status)` 이 route 를 해시에 넣고 `IDENTITY_FIELDS["error_cluster"]==("signature",)`. **다만 `normalize_stack` 은 분석 시점(`analyzer.py:672`)에 불리고 분석 윈도가 1h/24h** 라 ≤24h 내 수렴. 대가는 현재 open `error_cluster` **3건**(20.5h 낡음·재현 안 됨)의 단절. **이득이 더 크다** — 지금은 웹발 오류가 uuid 마다 다른 시그니처로 파편화된다 |
| ③ 승계 잡이 실제로 도나 | **해소 · 미측정 해제** | `celery_app.py` `cleanup-growth-insights` → `growth_tasks.cleanup_insights` **매일 03:12** 예약 + 라이브에 `superseded 321건` 실재 |
| ④ 대안: 읽기 시점 정규화 | **기각** | 소비처마다 기억해야 해 표류(이 저장소가 반복해 데인 형태). 수집부는 한 곳이고 분석 윈도가 짧아 수렴이 빠르다 |

### ★이 변경이 **하지 못하는 것**(승계 금지)

**이미 쌓인 bare-key 인사이트 행은 영원히 열린 채 남는다.** 승계는 `key` 가 같아야
일어나는데 그 행들의 key 는 옛 어휘다(`/store/projects` open 7건 등). 이 PR 은
**앞으로의 분열을 막을 뿐** 재고를 줄이지 않는다. 재고 정리는 별건이며,
볼트가 이미 «`status=open` 을 나이와 무관하게 그려 낡은 가득 찬 화면으로 위장한다»로
기록한 부채와 같은 자리다.
