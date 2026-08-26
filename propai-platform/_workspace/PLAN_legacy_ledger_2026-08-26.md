# 계획 — 간략 수지분석을 **원본 실무 양식(09_LEGACY)** 구조로 제공

작성 2026-08-26 · SESSION-G · 브랜치 `feat/legacy-ledger`

## 0. 옵시디언 조회 (계획 게이트 0단계)

| 찾은 것 | 결과 |
|---|---|
| 같은 워크북 대조 문서 | **있음** — `wiki/design/2026-08-26_수지분석_자동화_구축계획_외부모델_대조.md`. 그 문서의 **B6「검산층 부재」**가 이 작업의 절반이다 |
| `09_LEGACY` 관련 기록 | **없음**(그 문서에도 언급 0건 — 새 범위) |
| 기각된 접근 | **없음** |
| 같은 클래스의 앞선 결함 | **있음** — *"사유를 버렸다"*(유료·비가역 산출물 규율 §4). 아래 §1-c 가 정확히 그 형태다 |
| 미결·부채 | B6 검산층(P1-1) · B5 부담금 9종 전국단일값(P2-1) |

★신선도 재확인: 위 문서가 인용한 `node-body-builders.ts:259`·`ProvenanceModule` 은 **이미 #859 에서 처리**됐다(B1·B2 = P0-1·P0-2). 이 계획은 그 다음 칸이다.

## 1. 전제 표 — **측정값만** 적는다

| # | 전제 | 확인 방법 | 결과 |
|---|---|---|---|
| a | 09_LEGACY 의 구조 | `openpyxl` 로 전 셀 덤프 후 A/B/C열 계층 **파생형 집계** | **실항목 58 · 소계·합계 14** · 3단 계층 · 수량 53/58(**91%**) · 단가 46/58(**79%**) · **근거 58/58(100%)** · `(추가)` 12건 · 검산 블록 3항목(OK/ERROR) |
| b | 우리 개략수지가 **항목 내역**을 돌려주는가 | `grep -c '"items"'` on `rough_feasibility_orchestrator.py` + 위치 확인 | **3회뿐, 전부 charges 블록**(`:277` `:696` `:703`). `cost_breakdown` 은 스칼라 5개(land/construction/finance/other/charges) |
| c | 부담금 항목이 **수량·단가·사유**를 싣는가 | `_compact` 리스트 컴프리헨션 원문 | **아니오** — `code·name·amount_won·borne_by` 만 남기고 **`base_won`·`rate`·`detail` 을 버린다**(`:692-697`). 엔진(`utility_stage_engine`)은 갖고 있다 |
| d | 수량×단가를 **지어내지 않고** 만들 수 있는 행이 몇 개인가 | 블록 원문에서 짝 확인 | 매출 1(`saleable_area_pyeong`×`sale_price_per_pyeong`) · 택지비 1(`land_area_sqm`×`per_sqm_won`) · 공사비 1(`gfa_sqm`×`unit_per_sqm_won`) · 부담금 **16**(`base_won`×`rate`, ⓒ복원 시) = **19** |
| e | 수량·단가가 **원리적으로 없는** 축 | 동상 | 금융비용·일반사업비 — 엔진이 합계만 낸다 → **null + 사유** |
| f | 구성비 | `grep '(pct|ratio)"'` = 20건이나 전부 `roi_pct`·`irr_pct` 류 | **매출 대비 구성비는 없음** |
| g | 검산 판정 필드 | 반환 최상위 키 전수 | **없음**(계산은 정합하나 OK/ERROR 를 내는 층이 없다) |

## 2. 변경 내용

**신설** `app/services/feasibility/legacy_ledger.py` — **순수 함수** `build_legacy_ledger(scenario) -> dict`.
`build_rough_scenario()` 산출물을 입력으로 받아 3단 계층 원장을 만든다. **I/O 없음 · 계산 엔진 무변경.**

    sections[] : {key,label,groups[],total_won}
      groups[] : {key,label,items[],subtotal_won,share_pct}
       items[] : {key,label,amount_won,qty,qty_unit,unit_price,unit_price_unit,
                  basis,note,added,share_pct}
    checks[]   : {key,label,ledger_won,engine_won,diff_won,verdict:"OK"|"ERROR"}
    coverage   : {items,with_qty,with_unit_price,with_basis,qty_pct,unit_price_pct,basis_pct}

**보강** `rough_feasibility_orchestrator.py` `_compact` — `base_won`·`rate`·`reason` 을 **버리지 않는다**(전제 ⓒ).
★**additive** 다: 기존 키는 그대로 두고 셋을 더한다 → 기존 소비처 무영향.

### 회귀가 아닌 근거

- `legacy_ledger` 는 **신규 파일**이고 기존 경로가 부르지 않는다(엔드포인트는 새로 만든다).
- `_compact` 는 **키 추가만** 한다. 기존 소비처는 `code`·`name`·`amount_won`·`borne_by` 만 읽는다
  (실측으로 확인하고 결과를 여기 적을 것 — **미측정이면 이 줄을 지운다**).

## 3. ★검증하지 못한 것

1. **라이브 종단** — 배포 전이라 실제 주소로 원장을 떠 보지 못한다.
2. **09_LEGACY 의 58항목 중 우리가 못 채우는 39행** — 조합 1/2/3차 분양 분할, 발코니확장, 특화 프리미엄,
   O/T·상가 층별, M/H, 광고홍보, 분양대행, 설계·감리·인입·예술장식·철거 등은 **우리 엔진에 대응 산출이 없다.**
   이 PR 은 **있는 것만** 원장에 싣고, 없는 것은 **행을 만들지 않는다**(빈 행을 만들면 0원으로 읽힌다).
   → 커버리지 수치로 자기신고한다. **"58행을 재현했다"고 주장하지 않는다.**
3. **`(추가)` 표시** — 09_LEGACY 는 원본 대비 신설 항목을 표시하는데, 우리에겐 대조할 "원본"이 없다.
   필드는 두되 **전부 `false`** 로 나간다(향후 사용자 업로드 원장과 대조할 때 쓸 자리).
4. **구성비의 분모** — 09_LEGACY 는 `매출액합계`(부가세 차감 후)를 쓴다. 우리는 부가세 축이 없어
   `revenue.total_won` 을 분모로 쓴다. **같은 이름의 다른 값**이다 — 라벨에 명시한다.
5. **금융비용·일반사업비의 수량·단가** — 엔진이 안 낸다. null 로 두고 사유를 적는다. **미측정이 아니라 부재**다.
6. 프론트 표의 **렌더 검증** — 이 PR 범위에 넣을지 미정(백엔드 우선).

## 4. 되돌리기 경로

`legacy_ledger.py` 삭제 + 엔드포인트 1개 제거 + `_compact` 의 추가 키 3개 제거. **다른 경로에 흔적 없음.**

## 5. 잠금 — 이 변경을 지키는 검사

| 축 | 검사 | 변이로 죽어야 할 것 |
|---|---|---|
| **탐지** | 부분합·총계가 항목 합과 일치 | 항목 하나를 빼면 ERROR |
| **탐지** | `charges.items` 합 == `charges.total_won` (**비자명** — 두 값이 다른 경로에서 온다) | `_compact` 가 항목을 흘리면 ERROR |
| **특이도** | 정상 시나리오에서 **모든 검산 OK** · 자동조치 0건 | *"항상 ERROR"* 가 만점이 되지 않게, 핵심 단언은 **"고치면 OK 로 돌아오는가"** |
| **배선** | 엔드포인트가 실제로 `build_legacy_ledger` 를 태운다 | 호출을 지우면 빨개짐 |
| **두 모집단** | 완전 시나리오 vs **강등 시나리오**(블록 None) 가 **다른 커버리지**를 낸다 | 커버리지가 상수면 배선을 끊어도 통과 |
| **래칫** | 커버리지 하한(`qty_pct` 등)을 **못 박는다** | 수량·단가를 흘리면 빨개짐 |
| **무목업** | 값이 없는 항목은 `qty=None` 이고 **0 이 아니다** | `or 0` 을 넣으면 빨개짐 |

★래칫은 **목록이 아니라 산출에서 파생**시킨다 — #859 에서 목록형 래칫이 **스스로 무장해제**되는 것을
실증했다(계약 목록에서 이름을 지우면 락이 그 필드를 안 본다).
