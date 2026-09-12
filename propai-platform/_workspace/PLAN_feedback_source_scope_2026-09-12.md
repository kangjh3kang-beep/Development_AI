# 자가검증 표면의 👎 가 **서술기능을 자동으로 끄는 경로**로 들어가지 않게 한다 (㉠)

작성 sid=68ed1a1d · 2026-09-12 · 브랜치 `fix/feedback-source-excluded-from-quality` · base **30f0dfbc0**

## 0. 옵시디언·보드 조회 결과 (§계획 게이트 §0)

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | ★**있다.** *"`VerificationBadge` 가 `service` 를 넘기게 한다"* — 제가 처음 세운 처방인데 **동료 세션(sid=7af9eaa2)이 반증**했고 제가 원문으로 확인했다. `apps/web/eslint.config.mjs:59-88` 이 그 사고를 **빌드로 막으면서** 선행조건까지 적어 두었다: *「별도 수집면이 필요하면 **출처를 구분해 집계에서 제외하는 봉합이 선행돼야** 합니다」*. ⇒ **이 PR 이 그 선행조건이다.** `service` 전달은 **이 PR 에 없다.** |
| **같은 클래스 앞선 결함** | `#1030`(`blocked_total` 뭉갬 분리) · `#995`(무동작 액션이 유료 경로 경고를 닫던 것) — 둘 다 «같은 신호가 두 사실을 덮는다» |
| **미결·부채** | 보드 2026-09-08 sid=7af9eaa2 조사 — `acted=0` 은 세 겹이고 **임계 자동완화는 `#1007` 이 잠근 기각 경로** |
| **이전 판단의 근거** | ★제가 처음 설계한 ⓑ(«귀속 불가를 `withheld` 로 센다»)를 **철회**했다: `withheld` 는 «표본 하한 미달» 축이라 거기에 «귀속 불가»를 넣으면 **고치려는 뭉갬을 내가 복제**하고, `qua 0/0 → 0/N` 전이가 **동료의 배포 판정축을 오염**시킨다 |

## 1. 전제 표 — 확인 방법과 **실제 값**

| # | 전제 | 확인 방법 | **결과** |
|---|---|---|---|
| 1 | 집계에 **출처 필터가 없다**(eslint 의 주장) | `ai_feedback` 을 `service` 키로 읽는 곳 전수 × `target_type` 언급 | **4곳 전부 0회**(대조군: 같은 파일들이 `service` 를 **42~58회** 언급 ⇒ 조회기 생존) |
| 2 | 소비처 수 | `grep "FROM ai_feedback"`(테스트 제외) | **5곳**, 그중 `service` 키 사용 **4곳** ★제 초판 «2», 동료 «3» — **둘 다 틀렸다**(목록 vs 패턴) |
| 3 | 출처 축이 **이미 저장된다** | `routers/growth.py` | `_FEEDBACK_TARGET_TYPES = {"llm_output","analysis","recommendation"}` · INSERT 가 그대로 저장 |
| 4 | 서버가 `service` 를 **유도하지 않는다** | 같은 파일 | `"svc": fb.service` — 보정 지점 **0건** |
| 5 | `analysis` 를 보내는 렌더 지점 | `grep '<FeedbackWidget'` 파생 | **정확히 1곳** — `components/common/VerificationBadge.tsx:223` |
| 6 | 형제는 **제대로 보낸다** | 파생 | `DesignGenPanel.tsx:797` `service:"design_orchestrator"` ⇒ **불일치이지 기능 부재가 아니다** |
| 7 | **자동 ↔ 사람 게이트** 갈래 | 각 소비 함수의 선언 원문 | 자동: `analyzer._analyze_quality_drop`(→`feature_toggle`) · `feature_flags`(버전 자동 채택) / 사람: `learning_loop.compute_down_rates`(→PR 제안) · `learning_loop`(*"자동 active 절대 금지 = 사람 승인 게이트"*) · `improvement_agent._failure_samples` |
| 8 | `target_type` 이 **NOT NULL** | `schema_guard` DDL 원문 | `target_type text NOT NULL` ⇒ `<> ALL` 이 행을 조용히 버리지 않는다 |
| 9 | 라이브 정합 | `/heal-log` 의 `growth_analysis` | `axes "… qua 0/0"` — 피드백 축에 표본 **0** |

## 2. 변경과 **회귀가 아닌 근거**

| 변경 | 회귀가 아닌 근거 |
|---|---|
| `feedback_scope.py` 신설(SSOT) — `FEEDBACK_TARGET_TYPES` · `AUTO_EFFECTOR_EXCLUDED_TARGETS=("analysis",)` | 순수 상수 모듈(의존 0) |
| **자동 경로 2곳**에 `target_type <> ALL(:excl_targets)` | 라이브 `qua 0/0`(표본 0)이라 **집계 결과 변화 0**. 전제 8 로 NULL 행 유실 없음 |
| **사람 게이트 3곳은 그대로** | ★처방이 결함보다 넓어지지 않게 — 자가검증 👎 는 **사람이 보는 축에는 계속 들어간다** |
| 라우터 손목록을 **정본에 위임** | 같은 값의 두 정의 제거(§29). 값 불변 · `is` 동일성 락 |

★**`service` 전달(㉡)과 eslint 재검토(㉢)는 이 PR 에 없다** — ㉠ 없이 ㉡ 을 하면 사고가 열린다.
★**동료 판정축 비오염**: `qua.total` 등 커버리지 집계 정의 무접촉 ⇒ *「㉠만 배포되면 `qua 0/0` 유지가 정상」* 유효.

## 3. ★검증하지 못한 것

1. **SQL 층을 행위로 못 태웠다** — 제외가 SQL 안에 있어 가짜 db 는 그 층을 **우회**한다.
   락은 `text()` 상수 **AST 추출** + **파라미터 출처** + **리터럴 핀**으로 건다(형제
   `test_healer_fetches_only_handled_types` 가 쓰는 같은 방식). **이 한계를 숨기지 않는다.**
2. `ai_feedback` **실제 행 수·target_type 분포** — DB 직접 조회 **권한 없음**.
3. `target_type="analysis"` ⟺ 자가검증 표면은 **현재 1:1 근사**다(전제 5). 두 번째 `analysis`
   표면이 생기면 근사가 깨진다 — 그때는 **출처 필드를 따로 두는 것**이 옳다(모듈 독스트링에 적었다).

## 4. 되돌리기

단일 revert. 집계 결과가 오늘과 같으므로(전제 9) 사용자 가시 변화 0.

## 5. 잠금 (신규 7)

L1 자동 경로에 제외가 **있다**(공허 방지: 그 질의가 정말 그 집계인가 선단언) ·
L2 **형제 자동 경로**(feature_flags)도 — 형제를 빠뜨리지 않는다 ·
L3 ★**사람 게이트 경로에는 없다** — 「전부 제외」 구현을 배제한다(이게 없으면 신호를 버린다) ·
L4 제외 목록이 **정본을 경유**(AST 파라미터 출처) · L5 **리터럴 핀**(계약 어휘) ·
L6 제외 대상이 **닫힌 어휘 안**(오타면 조용히 무동작) · L7 **NOT NULL 전제**를 DDL 원문으로.

★추가로 `test_pii_mask_diagnostic_keys` 의 **줄번호 면제**를 그 락의 지시대로 갱신했다(137→138) —
임포트 한 줄이 밀어낸 것이고, **느슨하게 바꾸지 않았다**.
