# 미지값이 「안심 기본값」으로 접힌다 — 경계 정규화 + 행위 락

브랜치 `fix/unknown-value-safe-fallback` · 2026-08-27 · 대상 `apps/web`

동료 세션 `development-ai-0b` 의 범위 검토 요청에서 출발했다. 그쪽이 고친 것은
`RISK_LEVEL_STYLE ?? "낮음"`(`ComprehensiveAnalysisPanel.tsx`)이고, **그쪽이 양보한
나머지 범위**를 내가 판정해 진짜 결함 2건을 잡는다.

---

## 0. 옵시디언·볼트 조회 결과 (계획 게이트 §0)

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | **없음** — 이 결함 클래스(미지값→안심폴백)로 기각된 접근 기록 없음 |
| **같은 클래스의 앞선 결함** | **있음.** ①`feedback_lock_every_display_layer`(08-24): 백엔드 11종 vs 표 7종이라 **3종이 유령·7종이 영문 raw**. ★`\| (string & {})` 유니온은 **tsc 도 안 잡는다** ②`feedback_name_collision_is_not_same_regime`(08-19): 부분일치로 제도 오판 |
| **미결·부채** | **없음** — 이 두 파일에 `it.todo`·부채 메모 0건 |
| **이전 판단의 근거** | 동료 `-0b` 의 §3 「검증 못한 것」. **승계하지 않고 재측정**했고, 그 결과 `SEVERITY_META` 는 **오탐(도달 불가)** 으로 뒤집혔다 |

★신선도 재확인: 인용한 파일·상수·엔드포인트는 전부 `origin/main` `5a79f510` 에서 **직접 실측**했다.

---

## 1. 전제 표 — 확인 방법과 **실제 측정값**

| # | 전제 | 확인 방법 | **결과(실측)** |
|---|---|---|---|
| 1 | `VerificationBadge` 의 `verdict` 가 닫힌 집합이 아니다 | `verifier_service.py` 원문 | **참.** `:187` `verdict = data.get("verdict") or "pass"` — `parse_llm_json` 산출물(LLM 자유 JSON) |
| 2 | 그 값이 어디서도 정규화되지 않는다 | `grep -nE 'verdict' … \| grep -iE 'lower\|strip\|in (\|whitelist\|allowed\|normal'` | **0건.** ★대조군: 같은 파일 `verdict` 라인 **15개** → 조회기 생존 |
| 3 | 프론트 타입이 tsc 로 막지 못한다 | `VerificationBadge.tsx:27` | **참.** `verdict: "pass" \| "warn" \| "fail" \| string` — **열린 유니온**. `VERDICT_META` 도 `Record<string, …>` |
| 4 | 폴백 `warn` 이 `fail` 보다 **약하다** | `VERDICT_META` 정의(`:35~39`) | **참.** fail=`--status-error`+"오류 발견" / warn=`--status-warning`+"주의" |
| 5 | 완충(`if "high" in sev`)이 잠금이 아니다 | `verifier_service.py:189` | **참.** `sev` 는 `issues[].severity` = **LLM 자유 텍스트** |
| 6 | `LandIntelligencePanel` 의 `c.status` 생산자가 무검증이다 | `lib/ai-analyze-client.ts:83` | **참.** `data = JSON.parse(_stripFences(text)) as T` — 스키마 검증 **0** |
| 7 | 그 경로에 **거짓 캐스트**가 있다 | `LandIntelligencePanel.tsx:844` | **참.** `status: c.status as "safe" \| "warning" \| "danger"` |
| 8 | 폴백 `safe` 가 **가장 안심** 쪽이고 `danger` 가 가려진다 | `:265~269` | **참.** safe=`--status-success`(초록) · danger=`red-500`. 표에 danger **실재** |
| 9 | 그 칩에 **상태를 말하는 글자가 없다** | `:1402~1405` 원문 | **참.** 렌더는 `c.label` + `c.value` 뿐 — **신호가 색 단독** |
| 10 | 기존 락이 없다 | `grep -rl … --include=*.test.ts*` | **0건**(`statusColors`·`VERDICT_META`·`SEVERITY_STYLES`). ★대조군: 동료가 고친 `RISK_LEVEL_STYLE` 도 `origin/main` 기준 **0건**(동료 브랜치엔 있음) |
| 11 | `vitest` 수집이 목록형이 아니다 | `vitest.config.ts:37` | **파생형.** `include: ["**/*.test.ts","**/*.test.tsx"]` — 새 테스트가 자동 수집됨 |

### 판정에서 **제외**한 것 (오탐 — 근거 포함)

| 자리 | 왜 오탐인가 |
|---|---|
| `FieldAuditNotice.tsx:45` `SEVERITY_META ?? .P2` | 생산자가 **닫혀 있다**. `field_audit/contracts.py` = pydantic `Severity = Literal["P0","P1","P2"]` + `ConfigDict(extra="forbid")`. 대입 리터럴 전수 P2×4·P1×3·P0×1 — **이탈 0** |
| `AIRecommendationPanel.tsx:42` `SEVERITY_STYLES ?? .info` | `ai_recommendation.py` 가 critical/warning/info **3개 닫힘**, 프론트 표와 정확히 일치 → 도달 불가 |
| `CONFIDENCE_META ?? .low` | `low = { label:"신뢰도 낮음", token:"--status-error" }` — **빨강**. 안심 방향 아님 |
| `LEVEL_CHIP/LEVEL_COLOR ?? .low` | `low` 는 위험도가 아니라 **신호 강도**. high=초록·mid=amber·**low=회색 중립** |
| `APP_STYLE ?? "불가"` · `PRESALE_STATUS_COLORS ?? "미정"` | 보수적·정직 방향 |

---

## 2. 변경 내용과 **회귀가 아닌 근거**

★근본 처방은 **경계에서 정규화하고, 모르면 유효값이 아닌 상태로 접는 것**이다.
동료 `-0b` 가 정확히 짚었듯 내 두 건에는 **SSOT 오라클이 없다**(생산자가 LLM 자유 JSON).
그래서 *백엔드 상수를 파싱해 프론트 표를 강제*하는 그쪽 락 형태는 **여기 안 맞는다.**

`development-ai-cf`(SESSION-H) 가 같은 날 독립으로 도달한 일반화가 이 설계의 근거다:

> **「모름」을 그 타입의 유효값으로 표현하는 순간 결함이 생긴다.**
> `0` 은 유효한 금액이고 `"safe"` 는 유효한 status 다. `unknown` 은 아니다.

1. **`lib/unknown-value.ts` 신설** — `resolveKnown(table, raw)` 가 **판별 유니온**을 돌려준다
   (`{known:true,value,key}` | `{known:false,value:null,key}`). 폴백이 **유효값이 아니라
   「모름」이라는 별도 상태**가 되므로 호출부가 구별을 **강제로** 하게 된다.
   대소문자·공백은 **표의 키에서 파생해** 복원한다(`"FAIL"` → `fail`) — 현실적 LLM 이탈의
   대부분이 표기 흔들림이고, 그건 **강등이 아니라 회복**이 맞다.
2. **`lib/verification-verdict.ts` 신설** — `VERDICT_META` + `resolveVerdictMeta()` 를
   컴포넌트 밖 **순수 함수**로 꺼낸다. 미지 → 중립 회색 + **"판정 불명"** + **원값 노출**.
3. **`lib/land-characteristic-status.ts` 신설** — `statusColors` + `resolveCharacteristicStatus()`.
   미지 → 중립 회색 + **`unknown:true`**. 칩이 색 단독이므로 호출부가 **"확인 불가" 글자**를 낸다.
4. 두 컴포넌트는 그 함수를 **부르기만** 한다.

**회귀가 아닌 근거**: 알려진 키(`pass`/`warn`/`fail`, `safe`/`warning`/`danger`)의 렌더는
**바이트 단위로 종전과 같다** — 락의 대조군 모집단이 그것을 같은 실행에서 단언한다(§5).
바뀌는 것은 **종전에 안심값으로 접히던 미지 입력뿐**이다.

---

## 3. ★검증하지 못한 것

- **라이브에서 실제로 이탈값이 나오는 빈도는 미측정.** LLM 이 `"FAIL"`·`"위험"` 을 뱉는
  비율을 재려면 `llm_usage_log`/성장이벤트 조회가 필요한데 **하지 않았다.** 즉 이 수정은
  *"이탈이 가능하다"* 는 **구조적 실측**에 근거하며, *"지금 몇 % 가 이탈 중"* 은 **미측정**이다.
- **`LandIntelligencePanel` 을 렌더해서 확인하지 않았다.** 1,400줄 + 네트워크 훅이라
  vitest 렌더 비용이 크다. 대신 **판단을 순수 함수로 꺼내 행위를 태우고**, 호출부는
  **배선 락**으로 잡았다(§5). ★따라서 *"화면에서 실제로 회색으로 보인다"* 는 **미검증**이다.
- **`VerificationBadge` 도 렌더 테스트가 아니다.** 같은 이유(apiClient·react-query 의존).
- 다른 6개 축 스윕에서 나온 **오탐 판정들은 재현 가능하나 라이브 확증은 없다.**

## 4. 되돌리기 경로

세 신규 파일은 **순수 추가**다. `git revert <머지커밋>` 이면 컴포넌트 2개가 종전 표현식으로
돌아가고 신규 모듈·테스트가 사라진다. 마이그레이션·스키마·영속 상태 변경 **없음**.

## 5. 잠금 — 이 변경을 지키는 검사

`apps/web/__tests__/unknown-value-safe-fallback.contract.test.ts`

1. **행위 락(본선) — 두 모집단을 같은 실행에서 가른다**
   · 미지 입력 → `known:false`, 클래스가 **`safe`/`pass` 의 것이 아니다**
   · **★대조군**: 정상 `safe`/`fail` 입력 → **종전과 동일한 클래스·라벨**
   (대조군이 없으면 *"전부 unknown 으로 만드는"* 구현도 통과한다 — `cf` 지적)
2. **회복 락**: `"FAIL"`·`" fail "` → `fail` 로 **복원**된다(강등도 미지도 아니다)
3. **배선 락**: 두 컴포넌트가 그 함수를 경유하고, **원래 결함 표현식**
   (`|| statusColors.safe` · `|| VERDICT_META.warn`)이 **실행 라인에 없다**.
   주석·문자열은 `lib/source-invariant.ts` 의 간극 전수 주사로 걷어낸다.
4. **특이도**: 정상 코드를 위반으로 신고하지 않는다.
5. **조회기 생존**: 스캔이 대상 파일을 **실제로 읽었는지** 단언(0바이트·경로 오타로 인한
   공허한 초록 차단). 추출 실패는 **위반과 다른 예외**로 죽인다.

★변이 검증은 **`scripts/mutate_manual.sh`** 로 하고, 기계적 변이는
`scripts/mutate_changed.py --base $(git merge-base origin/main HEAD)` 로 base 를 **명시**해
돌린다(`development-ai-cf` 실측: 기본 base 가 움직이는 `origin/main` 이라 **남이 머지한
파일까지** 변이 대상이 된다).
