# PropAI 잔여 항목 통합 실행계획 (2026-06-12 · v2 재검증판)

> **작성 근거**: ① 사전존재 테스트 실패 12건 격리 재실행 실측(WSL 정본, git HEAD **57d5c44**, `.venv/bin/python -m pytest` — 11건 실패 재현 + 1건(mlops) 환경 skip 확인, 대상 코드 8개 파일 직접 열람) ② 혁신 로드맵 R1–R5 실코드 검증 분석(모든 판정에 코드 라인 근거 인용).
> 전판(HEAD 463dbbc) 결론과 정합 — 본 v2에서 2건 정밀화: **#10 mlops 실패 메커니즘**(목 오염+의존성 미설치 이중 문제), **#11 부수 결함**(parse_large_ifc `str()` 저장).
> **원칙**: 기존 자산 재사용 · additive(하위호환) · 계산 정확성 우선. 모든 수정은 정답값 회귀 테스트 동반, 가짜값 대신 정직한 "데이터 없음".

---

## ① 우선순위 매트릭스 (필수성 × 난이도 — 전 항목)

| 필수성 \ 난이도 | **소** | **중** | **대** |
|---|---|---|---|
| **필수** | **T1** 테스트 12건 일괄수정 — 11/12건 소 (제품버그 2건 #8·#9 + 부수버그 A3 포함) | **T1-#10** mlops 환경+테스트 (pandas/xgboost 설치 = R5 선행조건 겸용) · **R1** 세후 IRR 통합 현금흐름 · **R5-코드** AVM 학습 파이프라인+수지 결선 | **R5-데이터·운영** 수집 배치·재학습 주기 (R5-코드의 후속 운영 트랙) |
| **차별화** | — | **R2** 법령 시행일 버전드 룰엔진 · **R3-1** 결정론 유닛플랜 MVP (LH/SH 표준평면 템플릿) | **R3-2** ML 유닛플랜 (K-RPLAN 5만 장 수집 의존 — **보류**) |
| **선택** | **R4′** IFC 품질 보강(Pset/QTO+적산 배선, 소~중) — 원안 대체 스코프 | — | **R4 원안** web-ifc 클라이언트 도입 — **보류** (서버 IFC4 생성·export 기달성으로 원안 전제 소멸) |

**판정 요지**
- **T1이 전 항목 선행**: 12건 중 9건은 "코드가 옳은 방향(보안·정직성·아키텍처)으로 진화했는데 테스트가 못 따라온" 스펙 드리프트(삭제 대상 0건), **2건은 실제 제품 코드 버그**. 특히 **#9 AVM `UnboundLocalError`는 주소→법정동코드 미해석 시 항상 크래시하는 운영 버그** — 시세 신뢰 인프라(분양가 입력 최상류)의 폴백 경로 손상으로 12건 중 최우선.
- **R1·R5 = 필수**: 둘 다 "새 엔진"이 아니라 **기존 엔진(세금 38종·MLflow 인프라)의 배선 작업**. R1은 국내 경쟁 8개사 전부 ×인 세후 IRR 셀 선점(38종 엔진 자산이 현재 IRR에 미반영 = 차별화 가치 미실현), R5는 기획 Ph04 MAPE<7% 계약 + 수지 최대 민감변수(분양가 ±10%)의 입력 품질.
- **R2 = R1과 한 묶음**: 세후 IRR을 전면에 내세우는 순간 세율의 시점 정합성이 신뢰의 전제. legal_reference_registry 기보유로 규모 중.
- **R3 = 2단 분리 필수**: 결정론 MVP(3-1)는 기존 LLM→스펙→결정론 커널→검증기 소켓에 꽂기만 하면 됨(중). ML 풀스코프(3-2)는 데이터 수집 선결 — 보류.
- **R4 = 원안 폐기, 스코프 재정의**: 서버측 ifcopenshell IFC4 생성·`export-ifc` 엔드포인트·glTF 뷰잉이 **이미 실동작** — "국내 최초 IFC" 전제는 충족됨. 동일 공수면 IFC 품질 보강(Pset·BaseQuantities)이 우월: 감사 갭 D2(IFC 물량→공사비 단절, `bim_quantities` INSERT 전무)까지 풀어줌.

---

## ② 테스트 12건 트리아지 표 + 일괄수정 계획

**실측**: 12건 전부 격리 재실행 → 11건 실패 재현 + 1건(#10 mlops) 환경 skip(`.venv`에 pandas/xgboost 미설치 확인). 원인은 대상 코드 8개 파일 직접 Read로 확정.

### 트리아지 표

| # | 테스트 | (a) 실측 원인 | (b) 기능 필수성 | (c) 수정 방식 | (d) 난이도 |
|---|---|---|---|---|---|
| 1 | `test_v2_feasibility_router.py::TestVCSEndpoints::test_commit_and_log` | `401 != 200` — VCS 4종 엔드포인트에 `Depends(get_current_user)` 추가(`v2_feasibility.py:861~913`, Phase1 보안강화 = **의도된 변경**). 테스트는 라우터 단독 경량앱이라 인증 미주입 | **핵심**(수지분석 버전관리·롤백) — 기능 정상, 테스트만 구식 | 테스트 교정 — `dependency_overrides[get_current_user]` 주입 (기존 패턴 `test_design_v61_router.py:98-101` 재사용) | 소 |
| 2 | `〃::test_rollback` | #1과 동일 뿌리 (401 본문에 `sha` 없음 → `KeyError`) | 〃 | 〃 (픽스처 공유) | 소 |
| 3 | `test_celery_tasks.py::test_beat_schedule_count` | `4 != 3` — `celery_app.py:62`에 `sync-onbid-auctions-daily` 신규 추가 → 카운트 드리프트(카운트 단언 안티패턴) | 주변부 | 테스트 교정 — 카운트 → **이름 집합 동등 단언**으로 교체 | 소 |
| 4 | `〃::test_task_names_count` | `5 != 4` — #3과 동일(`auction_sync_task.sync_onbid_auctions` 추가) | 〃 | 〃 | 소 |
| 5 | `test_billing_metering.py::test_balance_margin_and_coins` | `KeyError: 'markup_pct'` — `billing_service.py:384` "마진율은 내부 정책이라 응답 미포함" = **의도된 스펙 변경**. 금액 키들은 그대로 유효 | **핵심**(과금) — 코드가 정답, 테스트가 구스펙 | 테스트 교정 — `"markup_pct" not in bal` 부재 단언으로 반전, 금액 단언 유지 | 소 |
| 6 | `test_80_percent_push.py::TestKakaoHandler::test_get_or_create_user_existing` | `TypeError: unexpected kwarg 'tenant_id'` — 정본 시그니처 `get_or_create_user(db, profile)`(`kakao_handler.py:149`), 개인 테넌트 내부 자동생성으로 변경 | 주변부 | 테스트 교정 — `tenant_id` 인자 제거 + 테넌트 자동생성 단언 추가 | 소 |
| 7 | `test_heavy_services.py::test_detect_defects_no_api_key` | dict ≠ `[]` — `_detect_defects`가 키 미설정 시 정직한 `service_not_configured` 상태 dict 반환으로 개선(`drone_iot_service.py:43-50`, 가짜 빈값 금지 원칙) | 주변부 | 테스트 교정 — `status`/`service_available=False` 단언으로 교체 | 소 |
| 8 | `test_deep_coverage.py::TestDroneInspect::test_inspect_no_api_key` | **제품 코드 버그** — `inspect()`가 `_detect_defects`의 dict 반환을 무조건 list로 순회(`drone_iot_service.py:107-109`) → `TypeError`. 운영에서 ROBOFLOW_API_KEY 미설정이면 inspect API 500 | 주변부 기능이나 **실결함** | **코드 수정** — `isinstance(detections, dict)` 가드 + 미설정 상태를 응답에 정직 전파 | 소 |
| 9 | `test_coverage_80_final.py::TestAVMFetchComparables::test_예외_처리` | **제품 코드 버그** — `apps/api/services/avm_service.py:101`: lawd_cd 미도출 조기반환 분기에서 `molit = MolitClient()` **생성(104행) 이전에** `await molit.close()` 호출 → `UnboundLocalError`. 주소→법정동코드 미해석 시 **항상** 크래시 | **핵심**(AVM 비교사례 = 시세 신뢰 인프라, 분양가 입력 최상류) — **12건 중 최우선** | **코드 수정** — 101행 `await molit.close()` 한 줄 삭제 + 분기 회귀 테스트 고정 | 소 |
| 10 | `test_workers/test_mlops.py::test_retrain_avm_success` | **환경+테스트 이중 문제** — 격리 실행 시 pandas/xgboost 미설치로 **skip**. 기록된 실패(`'>' MagicMock vs int`, mlops.py:72)는 전체수트 실행 시 conftest 세션픽스처가 주입한 pandas MagicMock이 DataFrame 필터로 유입된 목 오염. **`run_retrain_avm` 코드 자체는 건전**(수집→피처→XGBoost→MAPE→MLflow 등록) | **핵심** — AVM 재학습 = MAPE<7% 신뢰 게이트(R5 직결). 진짜 리스크: 운영 워커에 pandas/xgboost 없으면 재학습 태스크 전체 ImportError | **환경(의존성 설치)+테스트 교정** — ① `.venv`에 pandas/xgboost/scikit-learn 설치(R5 선행조건 겸용) ② skipif 가드 강화 + 목 재작성 | **중** |
| 11 | `test_workers/test_parse_large_ifc.py::test_parse_large_ifc_success` | `RuntimeError: db_factory 미주입`(parse_large_ifc.py:41) — 태스크가 `ctx['db']`→`ctx['db_factory']` 주입으로 변경(`apps/worker/main.py:36` startup 주입 = 의도된 개선). `worker_ctx` 픽스처(`test_workers/conftest.py:85-94`) 미갱신 | **핵심**(BIM 적산 사슬의 워커) — 기능 경로 정상, 픽스처 드리프트 | 테스트 교정(픽스처) — `worker_ctx`에 `db_factory`(목 세션 팩토리, `close()` 포함) 추가 — 11·12 동시 해소 | 소 |
| 12 | `〃::test_parse_large_ifc_empty_file` | #11과 동일 | 〃 | 〃 | 소 |

**분류 합계**: 제품 코드 버그 **2건**(#8, #9) · 테스트 교정 **9건** · 환경+테스트 **1건**(#10). 난이도: 소 11 / 중 1. "낡은 테스트" 9건은 전부 코드가 옳은 방향으로 진화한 스펙 드리프트 — **삭제 대상 0건**.

### 신뢰 인프라 직결성 판단 (정밀화 2건)

- **BIM 적산(#11·#12)**: 적산 신뢰 사슬 자체는 무손상 — 실패는 100% 픽스처 드리프트. **단, 부수 발견**: `parse_large_ifc.py:113`이 `bim_data`에 `str(result_json)`(파이썬 repr, 작은따옴표)을 저장 — JSON 직렬화가 아니어서 jsonb면 운영 INSERT 실패, text여도 다운스트림 `json.loads` 불가. 일괄수정 시 `json.dumps`로 교체(+1줄, 그룹 A3).
- **AVM 재학습(#10)**: 신뢰 인프라 직결 맞음(MAPE 게이트·R5). 그러나 코드 결함이 아니라 **환경 결함** — 테스트보다 먼저 "운영 워커 이미지에 pandas/xgboost/sklearn이 있는가"를 점검. 12건 중 유일하게 R5와 선행조건을 공유하므로 **의존성 설치를 R5 착수와 묶는 것이 효율적**.
- 진짜 신뢰 인프라 손상은 **#9(AVM UnboundLocalError)** — 운영 버그로 12건 중 최우선.

### 일괄수정 실행 프롬프트 (복사용)

```
PropAI(WSL ~/My_Projects/Development_AI/propai-platform) 사전존재 테스트 실패 12건을 일괄 수정하라.
SSOT: docs/REMAINING_ITEMS_PLAN_2026-06-12.md ②절 트리아지 표 (본 프롬프트가 우선).

[그룹 A — 제품 코드 버그 (최우선, 실패 재현→수정→정답값 고정)]
A1. apps/api/services/avm_service.py:101 — lawd_cd 미도출 조기반환 분기에서 molit 생성 전
    `await molit.close()` 호출을 삭제하라(클라이언트 미생성 상태). 회귀: _fetch_comparables("서울",84.0)
    → [] 반환 단언.
A2. apps/api/services/drone_iot_service.py inspect() — _detect_defects가 dict(service_not_configured)를
    반환하면 isinstance 가드로 순회를 건너뛰고 service_available=False 상태를 응답에 정직하게 전파하라.
A3. (부수) apps/worker/tasks/parse_large_ifc.py:113 — bim_data 저장을 str(result_json) → json.dumps로 교체.

[그룹 B — 의도된 스펙 반영 (테스트 교정)]
B1. test_billing_metering.py::test_balance_margin_and_coins — markup_pct 단언을 `"markup_pct" not in bal`
    부재 단언으로 반전, 금액 단언(monthly_base_remaining=7000 등)은 유지.
B2. test_heavy_services.py::test_detect_defects_no_api_key — `== []`를 status/service_available=False
    dict 단언으로 교체.
B3. test_80_percent_push.py::TestKakaoHandler — get_or_create_user(db, profile) 정본 시그니처로
    tenant_id 인자 제거, 개인 테넌트 자동생성 동작 단언 추가.

[그룹 C — 인증·카운트 드리프트 (테스트 교정)]
C1. test_v2_feasibility_router.py — 모듈 경량앱에 dependency_overrides로 get_current_user 가짜 사용자
    주입(test_design_v61_router.py:98-101 패턴 재사용). TestVCSEndpoints 2건 해소.
C2. test_celery_tasks.py — beat/task 카운트 단언을 전부 이름 집합 동등 단언으로 교체
    (sync-onbid-auctions-daily / app.tasks.auction_sync_task.sync_onbid_auctions 포함).

[그룹 D — 워커 픽스처·환경]
D1. apps/api/tests/test_workers/conftest.py worker_ctx — ctx["db_factory"]=lambda: mock_db 추가
    (mock_db에 close 포함). parse_large_ifc 2건의 commit 단언을 팩토리 산출 세션으로 조정.
D2. test_mlops.py::test_retrain_avm_success — ① .venv에 pandas/xgboost/scikit-learn 설치(운영 워커
    requirements에도 반영 — R5 선행조건) ② skipif 가드에 sklearn 추가 + sys.modules에 주입된
    MagicMock을 실설치로 오인하지 않도록 find_spec 평가를 강화 ③ 목을 현행 get_transactions
    호출 계약(5개 lawd × 2개월, 합계 ≥50건)에 맞춰 재작성.

각 건 절차: ①실패 재현 ②수정 ③정답값 고정 단언. 완료 기준: 위 12개 노드 + 관련 파일 전체가
.venv/bin/python -m pytest 로 0 failed (D2는 의존성 설치 후 skip 아닌 passed 확인).
```

> **이월 점검(전판 T2)**: collection 오류 2파일(`test_molit_client.py` ImportError `_BASE_PATH` / `test_auction_demock_court.py` ImportError `parse_detail_html`)은 본 v2 재검증 범위 밖 — 일괄수정 마무리 시 현 HEAD에서 재확인 후 현행 공개 API 기준으로 repoint(내부 상수 직접 import 금지).

---

## ③ R1–R5 구현계획 (실태 근거 → 방안 → 규모 → 실행 프롬프트)

### R1. 세후 IRR 통합 현금흐름 — **필수 (1순위)**

**실태 근거 (실코드 확인)**
- `app/services/feasibility/cashflow_generator.py`(383행): `generate_monthly_cashflow()` 파라미터·월별 items 어디에도 세금 항목 **0건**(items는 토지매입비/설계비/공사비/이자/분양수입/PF상환뿐, 98~208행). IRR(`_irr_from_netflows`)은 무차입·세전 기준(217~238행) — **세금 38종 미주입 확정**.
- 세금은 `modules/common/cost_blocks.py:83~102 compute_taxes()`가 **일시불 총액(grand_total_won)** 으로만 원가 계상 — 시점 분해 없음. 호출 2곳(`project_pipeline.py:1759~1784`, `v2_feasibility.py:1034~1059 /cashflow`) 모두 세금 인자 없이 호출.
- **재사용 자산**: `tax/integrated_tax_engine.py`가 이미 4단계(acquisition/construction/sale/disposal) **시점 구분된 스테이지별 total_won + items** 반환(173~186행) — 배선만 부재.

**방안 (additive, 새 엔진 0)**
1. `generate_monthly_cashflow()`에 `tax_schedule: dict | None = None` 추가(기본 None=기존 동작·하위호환).
2. 주입 매핑: **A(취득)→month 0**(토지매입 동월) / **B(공사 부담금)→착공월** / **C(분양 제세·HUG·VAT)→분양수입 월별 비례 배분** / **D01·D03(양도·지소세)→정산월(construction_end+1)** / **D06(종부세)→매년 6월 도래 월**(연차 루프, `calc_land_comprehensive_property_tax`의 annual_won 재사용).
3. summary에 `after_tax_irr_annual_pct`·`total_tax_won` 가산 — 기존 `_irr_from_netflows`에 세금 차감 netflow 그대로 통과.
4. 호출 2곳 배선 + 선결 정리: `tax/*` vs `tax_ai_service.py` 세율 이원화 — 정본을 `integrated_tax_engine`으로 고정.

**규모·의존성**: **중**(생성기 ~80행 + 라우터 2곳 + 회귀테스트). 외부 의존 없음 — 독립 착수 가능. 경쟁 근거: 세후 IRR 행은 국내 8개사 전부 ×, ARGUS만 ◎(해외 세제) — 최소 공수로 경쟁 0 셀 선점.

**실행 프롬프트**
```
propai-platform에서 R1 세후 IRR을 구현하라.
1) apps/api/app/services/feasibility/cashflow_generator.py의 generate_monthly_cashflow에
   tax_schedule(None 기본, additive) 파라미터를 추가하고 A=month0/B=착공월/C=분양수입 비례/
   D01·D03=정산월/D06=보유 연차별로 outflow 주입, summary에 after_tax_irr_annual_pct·total_tax_won 추가.
2) integrated_tax_engine.calculate_all_taxes의 stage별 total_won을 tax_schedule로 변환하는
   어댑터 함수를 같은 파일에 작성(새 엔진 금지).
3) project_pipeline._run_feasibility(1759행대)와 v2_feasibility /cashflow에 배선.
4) 정답값 회귀테스트: 세금 0이면 기존 결과와 완전 동일(하위호환), 세금 주입 시 IRR 감소 방향성·
   D06 연차 합계 = annual×년수 검증. 기존 테스트 무파손.
```

### R2. 법령 시행일 버전드 룰엔진 — **차별화 (경쟁 해자, R1 직후)**

**실태 근거**
- `tax/regional_tax_data.py`(325행): `ACQUISITION_TAX_MATRIX`·`CAPITAL_GAINS_BRACKETS`·`LAND_COMPREHENSIVE_TAX_BRACKETS` 등 전부 **파이썬 상수 하드코딩**. 시행일 메타 0건 — 연도가 주석으로만 존재(289행). tax 서비스 전체에 `effective/거래일/as_of` 그렙 0건.
- **재사용 자산**: `legal/legal_reference_registry.py`(검증된 law.go.kr 딥링크 + `inject_urls()`) + `integrated_tax_engine._TAX_CODE_LEGAL_KEYS`(22~29행) 세목→법령 매핑 기결합 — 버전 메타를 얹을 자리 완비.

**방안**
1. `apps/api/config_data/tax_rules.v1.json` 신설(기존 `carbon_factors_ifc.default.json` 패턴 재사용): 각 룰에 `{rule_id, effective_from, effective_to, payload, legal_ref_key}`.
2. `regional_tax_data.py`에 로더: `get_rates(..., as_of: date | None = None)` — None이면 현행 상수 그대로(하위호환). 기존 상수는 JSON "현행" 레코드로 1:1 이전.
3. `legal_ref_key`로 레지스트리 결합 → 응답에 "적용 세율 + 시행 기간 + 법령 링크" 3종 세트.
4. 고정 케이스: 2026-05-09 양도세 중과배제 한시조항 종료 전/후 `as_of` 두 날짜로 다른 세율 선택.

**규모·의존성**: **중**(데이터 이전이 대부분, 로직 ~150행). R1과 독립이나 동시 출시 시 시너지 — R1으로 세후 IRR을 내세우는 순간 세율 시점 정합성이 신뢰의 전제. 경쟁사 전무(랜드북도 미보유).

**실행 프롬프트**
```
propai-platform에서 R2 버전드 세율 룰엔진을 구현하라.
1) apps/api/app/services/tax/regional_tax_data.py의 상수들(ACQUISITION_TAX_MATRIX,
   CAPITAL_GAINS_BRACKETS, LAND_COMPREHENSIVE_* 등)을 apps/api/config_data/tax_rules.v1.json으로
   외부화 — 각 레코드에 (effective_from, effective_to, legal_ref_key) 메타.
2) get_acquisition_tax_rates 등 공개 함수에 as_of: date|None 파라미터 additive 추가.
   None이면 기존 동작 완전 동일(회귀테스트로 고정).
3) legal_reference_registry.get_legal_refs와 결합해 응답에 시행기간+법령 URL 부착.
4) 테스트: as_of 경계일(시행 전일/당일/종료 익일) 3점 케이스 + 2026-05-09 중과배제 종료 시나리오.
```

### R3. K-RPLAN 유닛플랜 생성 — **차별화 (2단 분리: 결정론 MVP 즉시 가능 / ML은 보류)**

**실태 근거**
- `cad/auto_design_engine.py`: `compute_unit_layout`(358~412행)은 세대 **개수 배분까지만** — `to_design_payload`에서 세대 구분선(udiv, 490~523행)만 긋고 끝. 단위세대 내부(침실·거실·주방·욕실) 전무.
- `bim/ifc_generator_service.py`(179~227행): 세대 칸막이·발코니·현관문까지 IFC 압출하나 세대 내부 평면 없음. `cad/design_spec.py`: 베이수·코어타입·발코니 확장 문법 부재. **단, LLM→스펙→결정론 커널→ConstraintValidator 검증 루프 아키텍처가 이미 구현** — 유닛플랜 생성기를 꽂을 소켓 완성.
- K-RPLAN 수집 파이프라인 흔적 0건.

**방안 (2단)**
- **R3-1 (결정론 MVP)**: DesignSpec에 `unit_grammar {bays: 2|3|4, core_type, balcony_extension}` 추가 → 평형×베이수→실 클러스터(LDK/침실/욕실) 사각 분할 룰 테이블 → ConstraintValidator에 채광(거실 외기면)·최소실면적 룰 → 기존 DXF/IFC 변환기에 내벽 추가. **LH/SH 표준평면 수십 장만 치수 룰로 코드화**(대규모 수집 불요) — 이것만으로 "국내 유일 단위세대까지 내려가는" 주장 성립(단위세대 평면 = 국내 상용 공백, Maket↔랜드북 사이 ◎ 셀).
- **R3-2 (ML, 선택적 후속)**: 분양공시 평면 수집 + HouseDiffusion/MaskPLAN 파인튜닝. 3-1의 검증기를 생성 루프 게이트로 재사용. **3-2는 3-1의 스키마·검증기 선행 필수**.

**규모·의존성**: 3-1 **중** / 3-2 **대**(데이터 수집 의존). R4′(IFC 품질)와 시너지. 핵심가치(수지 정확도)와 간접 연결 — R1·R5보다 후순위.

**실행 프롬프트 (R3-1)**
```
propai-platform에서 R3 1단계(결정론 유닛플랜)를 구현하라.
1) apps/api/app/services/cad/design_spec.py DesignSpec에 unit_grammar(베이수·코어타입·발코니확장)
   필드를 additive 추가, validate_spec에 문법 유효성 룰 추가.
2) apps/api/app/services/cad/auto_design_engine.py에 compute_unit_floorplan 단계 신설:
   LH/SH 표준평면 치수 룰(59/74/84형 × 2~4베이)을 상수 테이블로 코드화해 세대 내부
   실 분할(LDK·침실·욕실·발코니) 좌표를 결정론 산출. LLM은 의도 파싱만(기존 철학 유지).
3) to_design_payload와 ifc_generator_service에 내벽·실 라벨 추가(기존 _extrude_rect 재사용).
4) ConstraintValidator에 거실 외기면 접촉·최소 실면적 검증 추가, 위반 시 Violation 반환.
5) 테스트: 84형 3베이 정답 좌표 고정 + 전 평형 법규 검증 통과.
```

### R4. IFC 내보내기 — **선택 (재평가: web-ifc 원안 보류 → R4′ 'IFC 품질 보강'으로 방향 전환)**

**실태 근거**
- 서버측 IFC4 생성 **이미 실동작**: `bim/ifc_generator_service.py`(343행, ifcopenshell 0.8.0 — IfcProject→Site→Building→Storey→Slab/Wall/Column/Stair/Window/Door/발코니 절차 생성), 다운로드 엔드포인트 `design_v61.py:1052 POST /{project_id}/bim/export-ifc` 실재, `ifc_to_gltf_service.py`로 3D 뷰잉 연결.
- 프론트 `apps/web/package.json`: `@thatopen`/`web-ifc` 의존성 **0건** — 로드맵 R4의 전제("국내 최초 IFC")는 서버 경로로 이미 충족(HANDOFF §4 R4는 서버 생성기 완성 전 작성으로 보임).
- web-ifc 잔여 가치(브라우저 오프라인 내보내기·대형 IFC 스트리밍·실시간 편집 반영)는 전부 nice-to-have. 동일 공수면 **Pset·BaseQuantities 보강이 우월** — 감사 갭 D2(IFC 물량→공사비 단절, `bim_quantities` INSERT 전무)와 직결.

**방안 (R4′)**
① `ifc_generator_service`에 IfcElementQuantity(BaseQuantities)·Pset_WallCommon 부착(ifcopenshell.api `pset` 재사용) → 자사 `analyze_ifc` 파서(IfcElementQuantity 의존)가 자기 생성 IFC를 그대로 적산 가능 → `bim_quantities` INSERT 배선(감사 D2)과 연결. ② 편집 좌표→IFC 반영은 design_v61 저장본을 mass 보정값으로 서버 변환. web-ifc는 대형 IFC 뷰잉 수요가 실측될 때 재검토.

**규모·의존성**: **소~중**(Pset/QTO 부착 ~100행 + 배선). 적산-수지 트랙(감사 D2)과 한 묶음. R3 유닛플랜 진입 시 IfcSpace 단위로 자연 확장.

**실행 프롬프트 (R4′)**
```
propai-platform에서 R4를 'IFC 품질 보강'으로 수행하라(web-ifc 클라이언트 도입 보류).
1) apps/api/app/services/bim/ifc_generator_service.py의 각 Slab/Wall 생성부에
   ifcopenshell.api pset.add_qto로 IfcElementQuantity(면적·부피)를 부착.
2) apps/api/services/bim_ifc_service.py(analyze_ifc)가 이 IFC를 파싱해 물량을 산출하는
   왕복 테스트(생성→파싱→물량 정답값) 작성.
3) analyze_ifc 결과→app/services/cost/ifc_work_map.py 공종 매핑→bim_quantities INSERT
   배선(테이블·매핑·계산기 기존재, 연결 코드만 작성 — PLATFORM_FEATURE_AUDIT D2 항목).
4) 기존 export-ifc 엔드포인트·glb 변환 무파손 확인.
```

### R5. AVM 실모델 — **필수 (2순위, R1과 결합 시 가치 극대화)**

**실태 근거**
- **AVM 2벌 병존**: ① 레거시 `apps/api/services/avm_service.py`(735행) — **실제 마운트본**(`apps/api/main.py` 배포 엔트리포인트, RBAC `avm:read`). MLflow 3단계 폴백 Production→Staging→면적 기반 단순 추정(55~83행), MOLIT 실거래 비교사례(±15㎡), 실패 시 합성 비교사례 폴백(330~372행), `validate_mape` 기보유(※ T1 #9 버그가 이 파일 — 일괄수정에서 선치료). ② 신규 `app/services/avm/avm_service.py`(172행) — XGBoost+IDW 앙상블, MLflow 런 로드 실패 시 미학습 XGBRegressor→사실상 IDW만 동작.
- **MLflow 인프라 존재, 모델 0건**: docker-compose에 mlflow 서비스 정의, requirements에 mlflow 2.17.2·xgboost 2.1.2 완비. 그러나 **`ml/avm`·`ml/price_prediction` 디렉터리는 빈 폴더** — 학습 파이프라인·등록 모델 0건 → 런타임은 항상 폴백 경로.
- **시세→수지 미결선**: 분양가는 `project_pipeline.py:1534~1566`에서 `regional_pricing` **정적 테이블** + `MarketRevaluationService` 사용 — AVM과 미결선. MC 분석에서 분양가 ±10%가 손익 최대 변수(1718~1723행)인데 그 입력이 정적 테이블.
- 판정: AVM 자체는 테이블 스테이크(밸류맵 등 3세대 경쟁 존재) — PropAI 맥락의 가치는 **"시세→분양가→세후 IRR" 결선**. 기획 Ph04 MAPE<7% 대비 현재 "모델 없음 = 측정 불가".

**방안**
1. `ml/avm/`에 학습 파이프라인 신설: MOLIT 수집(기존 `_fetch_comparables` 클라이언트 재사용)→피처(레거시 16개 피처 정의 재사용)→XGBoost 학습→**MLflow Production 등록**. 새 서빙 코드 불요 — 레거시 Production 로드 경로(55~80행)가 자동 승격.
2. 홀드아웃 MAPE를 MLflow 메트릭으로 기록, 임계 7% 게이트화 — 미달 모델은 등록 차단.
3. 수지 결선: `MarketRevaluationService.revalue()`에 AVM 추정치를 confidence 가중 블렌딩 소스로 추가 → `sale_price_source="avm_blended"` 정직 표기. AVM 실패 시 기존 동작 완전 동일(graceful).
4. 구조 정리: 레거시(마운트본)를 정본 확정, 신규본은 IDW 유틸만 흡수 후 정리.

**규모·의존성**: 코드 **중** / 데이터·운영 **대**(수집 배치·재학습 주기). 선행조건: MOLIT API 키(기존 사용 중)·MLflow 컨테이너 가동·**pandas/xgboost/sklearn 설치(T1 D2와 공유)**. R1과 코드 영역 분리 — 병렬 가능.

**실행 프롬프트**
```
propai-platform에서 R5 AVM 실모델을 구현하라.
1) ml/avm/train.py 신설: 기존 apps/api/services/avm_service.py의 MOLIT 수집·16피처 정의를
   재사용해 시군구별 실거래 학습셋 구축→XGBoost 학습→홀드아웃 MAPE 산출→
   MAPE<7%일 때만 MLflow Production 등록(미달 시 등록 거부·사유 출력).
2) 서빙 무수정 검증: 레거시 AVMService._load_model이 Production 모델을 자동 로드해
   _model_stage가 'fallback'→'production'으로 전환되는 통합 테스트.
3) apps/api/app/services/feasibility/market_revaluation_service.py에 AVM 추정을
   confidence 가중 블렌딩 소스로 추가, sale_price_source='avm_blended' 표기.
   AVM 실패 시 기존 동작 완전 동일(graceful).
4) AVM 이원화 정리: app/services/avm/avm_service.py의 IDW 로직만 레거시로 흡수 후 중복 제거.
```

---

## ④ 권장 실행 순서 (다음 세션부터)

| 세션 | 작업 | 이유 |
|---|---|---|
| **다음 세션 (즉시)** | **T1 테스트 12건 일괄수정** (②절 프롬프트 그룹 A→B→C→D) | 그린 베이스라인 없이는 이후 모든 R작업의 회귀 판정 불가. 그룹 A에 **제품 버그 3건**(#9 AVM 운영 크래시 최우선, #8 드론, A3 json 직렬화) 포함 — 단순 정리가 아닌 정확성 수리. D2의 pandas/xgboost/sklearn 설치는 **R5 선행조건 겸용**이라 이 세션에서 함께 해소하는 게 동선 최적. 난이도 소 11/중 1 — 가장 싸게 가장 큰 신뢰 회복 |
| **세션 2** | **R1 세후 IRR** (③R1 프롬프트) | 필수 1순위. 세금 38종 엔진·시점 구조 모두 보유, 배선만 부재 → 최소 공수로 경쟁 0 셀(국내 8개사 전부 ×) 선점. 계산 정확성 가치 직결 |
| **세션 2~3 (병렬 가능)** | **R5 AVM 실모델** (③R5 프롬프트) | 필수 2순위. R1과 코드 영역 분리로 병렬 안전. 선행조건(의존성 설치)은 세션 1 D2에서 기해소 — 잔여는 MOLIT API 키·MLflow 컨테이너 가동 확인(사용자 액션 포함 가능). R1+R5 = "시세→분양가→세후 IRR" 신뢰의 양대 축 |
| **세션 4** | **R2 버전드 룰엔진** (③R2 프롬프트) | R1이 만든 세후 수치의 시점 정합성을 보증하는 기반 — R1 완료 직후가 결합 효율 최대(legal_refs 시행일 표기가 세후 IRR 응답까지 관통). 경쟁사 전무 해자 |
| **세션 5** | **R4′ IFC 품질 보강** (③R4′ 프롬프트) | 소~중 규모. Pset/QTO 부착 → 자기 생성 IFC 자가 적산 → bim_quantities 배선(감사 D2 해소 진입점). R3-1의 토대 |
| **세션 6+** | **R3-1 결정론 유닛플랜** (③R3-1 프롬프트) | 차별화 신규 빌드 — 선행 작업이 닦은 검증기·IFC 토대 위에서 착수. **R3-2(ML)·web-ifc 원안은 각각 데이터 수집·뷰잉 병목 조건 충족 시 재평가(보류)** |

**한 줄 요약**: 다음 세션은 무조건 **테스트 12건 일괄수정**부터 — 그 안의 제품 버그 3건(특히 #9 AVM 폴백 크래시)이 계산·서비스 정확성을 직접 건드리고, 0 failed 베이스라인이 R1~R5 전체의 회귀 안전망이며, D2 의존성 설치가 R5의 선행조건까지 겸한다. 이후 R1(세후 IRR)→R5(AVM)를 "기존 엔진 배선 작업"으로 빠르게 회수하고, R2→R4′→R3-1 순으로 해자를 쌓는다. R1·R2·R5는 새 엔진이 아니라 **기존 엔진(세금 38종·MLflow·법령 레지스트리)의 배선**이고, R4는 스코프 재정의, R3만이 유일한 진짜 신규 빌드(그나마 결정론 MVP는 커널 확장)다.

---

### 핵심 파일 경로 (WSL 정본 `~/My_Projects/Development_AI/propai-platform/` 하위)

- 버그: `apps/api/services/avm_service.py`(L101), `apps/api/services/drone_iot_service.py`(L107-109), `apps/worker/tasks/parse_large_ifc.py`(L41 db_factory·L113 str저장)
- 테스트 교정 대상 정본: `apps/api/app/routers/v2_feasibility.py`(L861-913), `apps/api/app/services/billing/billing_service.py`(L384-415), `apps/api/auth/kakao_handler.py`(L149), `apps/api/app/tasks/celery_app.py`(L62-93), `apps/api/tests/test_workers/conftest.py`(L85-94), `apps/worker/tasks/mlops.py`
- R1: `apps/api/app/services/feasibility/cashflow_generator.py`, `apps/api/app/services/feasibility/modules/common/cost_blocks.py`, `apps/api/app/services/tax/integrated_tax_engine.py`, `apps/api/app/services/pipeline/project_pipeline.py`
- R2: `apps/api/app/services/tax/regional_tax_data.py`, `apps/api/app/services/legal/legal_reference_registry.py`
- R3: `apps/api/app/services/cad/{design_spec,auto_design_engine}.py`
- R4′: `apps/api/app/services/bim/ifc_generator_service.py`, `apps/api/services/bim_ifc_service.py`, `apps/api/app/services/cost/ifc_work_map.py`, `apps/api/app/routers/design_v61.py`(L1052)
- R5: `ml/avm/`(빈 폴더), `apps/api/app/services/avm/avm_service.py`, `apps/api/app/services/feasibility/market_revaluation_service.py`, `apps/api/app/services/pipeline/project_pipeline.py`(L1534-1566)

*검증 기준: 2026-06-12, git HEAD 57d5c44, WSL `.venv/bin/python -m pytest` 격리 재실행(11 failed 재현 + 1 env skip) + 대상 코드 8개 파일 직접 열람. 로드맵 판정은 전부 정본 코드 라인 근거 인용. 전판(HEAD 463dbbc) 트리아지와 결론 일치 — #10 메커니즘·#11 부수 결함 2건 정밀화 반영.*
