# 계획 — **보류 사유가 사용자에게 도달하지 않는다** (개발방식 시뮬레이터 용도지역 + 실거래 단가)

**작성** `development-ai-09` · 2026-09-04 (절대형 서명) · 브랜치 `fix/scenario-zone-withheld-reason-ui`
**인계** `development-ai-88` 의 인계서 §2 ① (`propai-platform/_workspace/HANDOFF_2026-09-04_scenario_simulator_88.md`)

---

## §0 옵시디언 조회 결과 (계획 게이트 §0 — 네 항목)

Vault `/mnt/d/옵시디언기록/나의-모든-기록-최적화본` · 조회기 생존 대조군 `PropAI` **500건**.
주제어별: `전제감사` 7 · `보류값` 7 · `심의엔진` 20 · `permit_gate` 7 · `보류` 87 · `mixed_review` 15.

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | **있다** — `design/2026-08-25_보류값_계약_부재의_사유를_코드로.md` §2 가 *"「판정 보류」 문구가 있는 16파일 일괄 개조"* 를 **기각**했다(생산자 6 · 주석 6 · 소비자 5 가 섞여 절반이 churn). ★**문구로 모집단을 뽑지 않는다** — 이 계획은 **생산자 코드에서 파생**시켜 모집단을 잡는다. |
| **같은 클래스의 앞선 결함** | **있다** — 같은 문서 §5 가 *"★센티널 금지 · 값 자리에 `mixed_review_required` 를 넣지 않는다"* 를 확립했고, `errors/2026-08-28_법은_수치를_주는데_코드는_단일상수_6m를_쓴다.md` §7 이 *"형제가 이미 옳게 한다"*(`/zoning/integrated-analysis` 는 `dominant_zone: None` + 사유로 거부)를 적었다. 스윕 범위를 여기서 얻었다. |
| **미결·부채** | **있다** — 같은 설계문서 §7: *"배선 5 / 알려진 생산자 7 — 미배선 2는 사유와 함께 초록 안에 남긴다"* 그리고 *"★미배선이 0 이 되면 그 테스트가 실패한다 — 목록형을 파생형 전수 락으로 승격하라는 신호"*. |
| **이전 판단의 근거** | 설계문서 §5 가 **`_absent` 코드 하나만 강제**하고 `_basis`/`_reason` 문구 키는 **국소 관용을 존중**한다고 명시(고유키 실측 62 vs 32). 이 계획은 그 결정을 **승계**한다 — 새 문구 키를 만들지 않는다. |

★**신선도 재확인**: 위 문서가 인용한 `app/utils/withheld.py`·`ABSENT_REASONS`(7종)·`SENTINEL_VALUES` 는
**현재도 실재**한다(아래 §1 전제 P1 에서 실측).

---

## §1 전제 표 (★결과 칸은 **실측값** — 예상값 금지)

측정 기준: 워크트리 `Development_AI_zonewithheld` @ `f9ad839f`(= `origin/main`),
백엔드 `apps/api/.venv/bin/python` **3.12.3**.

| # | 전제 | 확인 방법 | **실측 결과** |
|---|---|---|---|
| **P1** | 닫힌 어휘가 실재하고 7종이다 | `app/utils/withheld.py` 원문 | ◎ `insufficient_coverage` `single_source` `source_unavailable` `masked_by_source` `ambiguous` `not_applicable` `awaiting_input` — **7종** |
| **P2** | 프론트가 `primary_zone_absent`·`_basis` 를 안 읽는다 | `grep -rn` on `apps/web` (`__tests__` 제외) | ◎ **0건**. 대조군 `primary_zone` 자체는 **5건**(조회기 생존) |
| **P3** | ★**「센티널이 화면에 나간다」는 현재 상태가 아니다** | `origin/main` 함수를 **직접 태움** | ◎ **인계서 전제가 틀렸다.** `dominant_zone_by_area([일반상업 1200, 제2종일반주거 800])` → `('일반상업지역','area_weighted')` · `([제3종 1000, 제2종 1020])` → `('제2종일반주거지역','area_weighted')` · 대조군 단일 → `('제2종일반주거지역','single_zone')` · 빈 입력 → `('','none')`(값이 갈리므로 조회기 생존) · `inspect.getsource` 에 `mixed_review_required` **없음**. → main 은 **임의 단일화**하고 센티널을 **한 번도 안 낸다** |
| **P4** | 따라서 `#972` 단독 배포는 **회귀가 아니다** | P3 에서 파생 | ◎ 전이는 `"일반상업지역"`(**거짓 확신**) → `None`→`"용도미상"`(**정직한 보류**). ★내가 보드에 퍼뜨린 **§E21 「묶어서 배포」는 거짓**이었고 **정정을 보드에 고정**했다 |
| **P5** | 그럼에도 ① 이 필요하다 | `DevelopmentScenarioCard.tsx:211` 원문 | ◎ `{site.primary_zone \|\| "용도미상"}` — **왜** 보류인지 말하지 못한다. `#972` 가 싣는 `primary_zone_absent="ambiguous"`(=「판정이 갈려 단일화하지 않았습니다」)가 **사용자에게 도달하지 않는다** |
| **P6** | 형제 모듈이 이미 있다 | `apps/web/lib/zoning/dominant-zone.ts` | ◎ 실재. **단 센티널 계약만** 다룬다 — `_absent` **코드를 받는 인자가 없다**. 새로 만들지 않고 **확장**한다 |
| **P7** | ★**프론트에 `_absent` 소비처가 정말 0인가**(§29 형제 훑기) | `grep -rn "_absent"` on `apps/web` | ✘ **0이 아니다 — 3곳 있다.** 인계서의 「0건」은 `primary_zone_absent` **한정**이었다 |
| **P8** | 그 3곳이 결함인가 (★위양성 점검) | 각 파일 원문 + 렌더 경로 | **2곳은 결함 아님** — `DeveloperProjection.tsx:314` 는 `balanced_basis` **문구를 렌더**하고 코드는 기계축으로 선언만 한다(계약이 지시하는 그대로) · `ApiKeyManagementPanel.tsx` 도 `r.message` 를 렌더. **1곳은 진짜 결함**(P9) |
| **P9** | ★**진짜 결함** — 생산자 어휘 ⊄ 소비자 어휘 | 생산자·소비자 원문 대조 | ◎ 생산자 `realtx_report_service.py:241·260·266` 이 내는 코드는 **`not_applicable` · `insufficient_coverage` · `masked_by_source`**. 소비자는 **화면** `RealtxReportPanel.tsx:62-69` 와 **PDF** `realtx_adapter.py:59-62` 가 **둘 다** `not_applicable` · `masked_by_source` · **`source_unavailable`**. → **`insufficient_coverage` 가 양쪽에서 `"—"` 로 떨어져 사유가 소실**되고, **`source_unavailable` 은 이 필드에서 죽은 라벨**이다 |
| **P10** | ★**이미 막고 있는 것이 있나**(인계서 §4-5) | `tests/test_withheld_value_contract.py` | **부분적으로만.** 그 락은 **생산자 축**을 파생형으로 잠근다(`ast` 로 `withheld()` 호출을 훑어 코드 ∈ `ABSENT_REASONS`). **소비자가 그 코드를 이름 붙일 수 있는가는 안 잠근다** — **한쪽만 건 단언**이다(§D19) |
| **P11** | 프론트 테스트가 파생형으로 수집된다 | `vitest.config.ts` | ◎ `include: ["**/*.test.ts","**/*.test.tsx"]` — 새 테스트가 자동 수집된다 |
| **P12** | `ZONE_BASIS_MIXED_REVIEW` 는 **죽은 상수** | `grep` on `services/development/` | ◎ main 에 **0건**, `#972` 브랜치에 선언만 있고 사용처 0. ★**내가 이 이름을 보고 P3 을 오독했다** — 88 도 같은 것을 확인하고 `#972` 에서 정리하기로 했다 |

### ★내가 틀렸던 것 (승계 방지 — 다음 사람을 위해)

- **선언을 동작의 증거로 읽었다.** `#972` 에 `ZONE_BASIS_MIXED_REVIEW = "mixed_review_required"` 가
  **선언되어 있는 것**을 보고 그 경로가 센티널을 쓴다고 결론냈다. 갈라 준 것은 grep 이 아니라
  **함수를 태운 것**이다(P3). ★**죽은 상수는 다음 사람에게 「이 경로가 그것을 쓴다」로 읽힌다.**
- **인계서의 「소비처 0건」을 어휘 전체로 확장해 읽을 뻔했다.** §29 형제 훑기가 **3곳**을 찾았고,
  그중 **2곳은 정상**이고 **1곳이 진짜 결함**이었다(P7~P9). **없는 것을 새로 만드는 것과
  있는 것을 안 쓴 것은 처방이 다르다.**

---

## §2 변경 내용과 **회귀가 아닌 근거**

### A. ① 본체 — 보류 사유를 화면에 (인계서 지시)

1. **신설** `apps/web/lib/withheld/absent-reasons.ts` — 백엔드 `ABSENT_REASONS` 7종의
   **프론트 거울**(코드 → 한국어). `resolveAbsentLabel(code, overrides?)` 는 열별 짧은 문구를
   **덮어쓸 수 있게** 하되, **덮어쓰지 않은 코드는 공용 문구로 떨어진다**(→ `"—"` 가 안 나온다).
2. **확장**(신설 아님) `apps/web/lib/zoning/dominant-zone.ts` — `formatDominantZone` 이
   `absent` 코드를 받아 **왜 보류인지** 를 label 에 싣는다. **기존 시그니처·기존 반환은 불변**
   (센티널·빈값 경로는 그대로) → **기존 락 6종이 그대로 통과해야 한다**(회귀 아님의 근거).
3. **배선** `DevelopmentScenarioCard.tsx` — `primary_zone_absent`·`primary_zone_basis` 를 타입에
   더하고, 칩이 `formatDominantZone` 을 경유한다. 값이 있을 때는 **지금과 글자까지 동일**
   (특이도 락으로 고정).

### B. ★전역 전파방지 (CLAUDE.md 「버그수정 기본정책」 §2 — 단발 국소 패치 금지)

P9 의 진짜 오점을 **같은 PR 에서** 고친다. 패턴은 *"소비자가 자기 목록으로 `_absent` 를 해석해
생산자가 내는 코드를 못 덮는다"* 이고, **화면·PDF 두 미러**에 동시에 있다.

4. **백엔드 SSOT 보강** `app/utils/withheld.py` — `ABSENT_SHORT`(표 칸용 짧은 라벨) 추가.
   **키 집합은 `ABSENT_REASONS` 와 같아야 한다**(락으로 강제).
5. `realtx_adapter.py`(PDF) — 미등재 코드는 `"—"` 가 아니라 `ABSENT_SHORT` 로 떨어진다.
6. `RealtxReportPanel.tsx`(화면) — 같은 처방. **열별 짧은 문구 3종은 그대로 유지**
   (그 문구를 고르는 이유가 주석에 적혀 있다 — 「상태 열이 이미 해제를 말한다」).
   바뀌는 것은 **덮지 않은 코드의 폴백**뿐이다 → 기존 4개 테스트 케이스 불변.

★**회귀가 아닌 근거**: A2·A3·B5·B6 은 전부 **기존에 값이 나오던 입력에서 바이트 동일**하고,
**기존에 `"—"` 로 떨어지던 입력에서만** 결과가 바뀐다. 두 모집단을 같은 락에서 갈라 단언한다.

### C. 하지 않는 것 (범위 밖 — 명시)

- `#972` 는 **손대지 않는다**(`development-ai-88` 이 계속 잡는다 — 본인 확인).
- `primary_zone_basis` 가 `first_parcel_no_area`(값은 있으나 근거가 약함)일 때의 **경고 칩**은
  이 PR 에 넣지 않는다 → **`it.todo` 로 초록 안에 부채를 드러낸다**(§B13). 사유: 「보류」와
  「근거 약함」은 다른 축이고, 후자는 이미 `primary_zone_is_inferred` 칩과 겹칠 수 있어
  **겹침을 재기 전에 칩을 늘리면 모순 칩이 나란히 선다**(그 파일 주석이 경고하는 형태).

---

## §3 ★검증하지 못한 것 (비워 두지 않는다 · **이유를 구분한다**)

| 미측정 | **이유의 종류** | 반증/측정 방법 |
|---|---|---|
| 라이브 응답에 `primary_zone_absent` 가 실린다 | **사건 미발생** — `#972` 미머지·미배포 | 인계서 §1 프로브(`/development-methods/scenarios` 의 `site.primary_zone_absent`) |
| 화면에서 사유가 실제로 읽힌다(브라우저) | **사건 미발생** — 이 PR 미배포 | 배포 후 해당 부지로 시나리오 실행 |
| `insufficient_coverage` 가 **라이브 실거래에서 실제로 발생하는 빈도** | **장치 부재** — 코드별 발생 계수기가 없다 | 생산자 분기는 `price·area 둘 다 있는데 단가 산정 불가`(0 이하·비정상). ★**빈도는 모르지만 계약 위반은 빈도와 무관**하다 |
| `single_source`·`awaiting_input` 등 나머지 4종의 화면 문구가 사용자에게 적절한가 | **장치 부재** — UX 검토를 안 받았다 | 공용 문구는 백엔드 `ABSENT_REASONS` 원문을 그대로 쓴다(내가 지어내지 않는다) |

---

## §4 되돌리기 경로

단일 PR · `git revert <머지커밋>`. A 와 B 는 파일이 갈리므로 부분 되돌리기도 가능:
A = `lib/withheld/` + `lib/zoning/dominant-zone.ts` + `DevelopmentScenarioCard.tsx` ·
B = `app/utils/withheld.py` + `realtx_adapter.py` + `RealtxReportPanel.tsx`.
★**계약 상수는 추가만 하고 기존 값을 바꾸지 않으므로**, 되돌려도 다른 소비처가 깨지지 않는다.

---

## §5 잠금 (★이 계획서가 선언한 것을 **무엇이 강제하는가**)

| 무엇을 잠그나 | 어디서 | 축 |
|---|---|---|
| **소비자 축 — 생산자가 내는 코드를 소비자가 전부 이름 붙일 수 있는가** (P10 이 못 잡던 것) | `apps/api/tests/test_absent_reason_consumer_coverage.py` (신설) | **파생형** — `ast` 로 `withheld()` 호출부에서 **필드별 코드 집합**을 뽑고, 그 필드의 소비자 맵(파이썬 `ABSENT_SHORT`·TS 맵)이 그 집합을 **덮는지** 단언 |
| `ABSENT_SHORT` 키 ≡ `ABSENT_REASONS` 키 | 같은 파일 | **양방향** — 어느 쪽에 더해도 실패 |
| 프론트 거울 ≡ 백엔드 `ABSENT_REASONS` | 같은 파일(파이썬이 `.ts` 를 읽는다) | **양방향** + ★**파일을 못 읽으면 판정 거부**(공허 진리 방지) |
| `formatDominantZone` 의 **두 모집단** — 값 있는 입력은 **바이트 동일**, 보류 입력만 사유가 붙는다 | `apps/web/lib/zoning/__tests__/dominant-zone.test.ts` (기존 확장) | 회귀 + 신기능을 **같은 실행**에서 |
| 화면이 raw 코드를 절대 안 내보낸다 | 같은 파일 + `DevelopmentScenarioCard` 락 | 부정형 + **양성 대조군** |
| 부채(`first_parcel_no_area` 칩 미구현) | `it.todo` | 초록 안에 보이게 |

★**변이로 확인한다** — `scripts/mutate_manual.sh` 로 ①폴백을 `"—"` 로 되돌림 ②`ABSENT_SHORT`
한 키 삭제 ③`absent` 인자를 무시하도록 배선 절단 ④키 집합 단언을 부분집합으로 약화.
**각각 CAUGHT 를 확인하고, 설명 가능한 생존은 이유를 코드에 적는다.**
