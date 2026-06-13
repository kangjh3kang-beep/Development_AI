# 새 세션 인계 — 적산 자동화 "다음 단계" (2026-06-13)

> 이 문서는 적산(BOQ) 자동화의 **다음 단계 3종을 새 세션이 끊김 없이 구현**하기 위한 단일 출발점이다.
> 1단계(마스터 추출 + 파라메트릭 엔진 + API + 프론트 + 시뮬레이션 7/7)는 **완료·커밋됨**(`5f737e2`).
> 본 문서의 §3 N1·N2·N3 가 다음 구현 대상이다. 먼저 §1 불변규칙을 읽고, §2로 현재 상태를 확인한 뒤 시작하라.

## 0. 한 줄 요약

실무 공내역서 5공종 마스터(3,997항목)에서 **연면적·세대수 → 공내역서 초안 자동생성**까지 완성됨(단가 빈칸).
다음 단계는 ①실적 N건 누적·회귀 ②BIM 실측 물량 우선 병합 ③단가DB 결합 → **금액까지 채운 완전 내역서**.

## 1. 불변 규칙 (위반 금지)

1. **브랜치**: `feature/trust-infra-2026-06-11` 에서 작업. **main 직접 푸시 금지**. 작업 브랜치만 푸시(remote: `git@github.com:kangjh3kang-beep/Development_AI.git`). main 머지·Oracle 배포는 다른 Claude 담당.
2. **additive·하위호환**: 기존 응답 키·store·테스트 계약 0개 변경. 단가/금액은 새 옵셔널 키로만 가산.
3. **정직 표기**: 가짜 단가·날조 수치·할루시네이션 금지. 표본 n=1 동안 `confidence='낮음(n=1)'`·"전문 적산 검토 필수" 배지 유지. 추정 기준값은 basis 문자열로 근거 명시. 데이터 없으면 "데이터 없음".
4. **출처 플래그**: 물량 출처(`qty_source` ∈ {user, bim, parametric}), 단가 출처(`price_source` ∈ {db, 표준품셈, KCCI, fallback})를 항목별로 표기.
5. **결정론**: LLM 0. 스케일링·병합·단가결합 모두 규칙 기반.
6. 검증은 WSL: `wsl.exe -d Ubuntu -- bash -c 'cd ~/My_Projects/Development_AI/propai-platform/apps/api && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest ...'` (venv: `apps/api/.venv`, 프론트: pnpm).
7. **서버 기동 주의**: uvicorn은 반드시 **플랫폼 루트에서 `PYTHONPATH=.:apps/api`** 로 — `cd propai-platform && PYTHONPATH=.:apps/api apps/api/.venv/bin/uvicorn apps.api.main:app --port 8901`. (apps/api에서 직접 띄우면 `No module named 'packages'`/`'app'` 으로 죽음 — 1단계에서 실측한 함정.)

## 2. 현재 상태 (커밋 `5f737e2` 기준)

기존 자산(전부 무수정 재사용):
- 마스터: `apps/api/app/services/cost/data/boq_master/{architecture,mechanical,electrical,landscape,civil}.json` + `_meta.json` (3,997항목·414섹션). item={id,section_code,section_name,name,spec,unit,qty_sample,row_count,ref_mat_price?}. **전기 1,025/1,029 항목에 ref_mat_price(참고 재료단가)** 보유 — N3 단가결합의 1차 소스.
- 추출기: `apps/api/scripts/extract_boq_master.py` (실적 추가 시 그대로 재실행).
- 레지스트리: `app/services/cost/boq_master_registry.py` — list_disciplines/get_sections/get_items/get_provenance.
- 엔진: `app/services/cost/boq_parametric_engine.py` — generate_draft(params)/build_xlsx. REF_GFA=238504, REF_HOUSEHOLDS=1384(추정), REF_LANDSCAPE=5060(추정). 드라이버: 세대>조경>고정(식·qty≤2)>연면적. 항목에 qty_basis·driver·basis·confidence 부착.
- 엑셀: `app/services/cost/boq_excel_export.py` — 실무 포맷(공종별 시트·단가 8칸 공란).
- 라우터: `app/routers/boq_auto.py` (prefix `/api/v1/boq-auto`): GET master/summary·master/items, POST draft·draft/export·draft/apply-cost. 무인증(기존 cost.py 패턴). 등록: `apps/api/main.py`.
- 파이프라인: `_run_cost` 말미 `_attach_boq_draft_hint`(project_pipeline.py:1529-1594) — additive 키 `boq_draft_hint`.
- 프론트: `components/cost/{BoqAutoWorkspace.tsx,boqAutoTypes.ts}` + `app/[locale]/(dashboard)/projects/[id]/boq/page.tsx`.
- 시뮬레이션: `apps/api/scripts/simulate_boq_user.py` (라이브 7/7), `tests/test_boq_e2e_contract.py` (오프라인 e2e).
- 설계/근거 문서: `docs/BOQ_AUTOMATION_2026-06-12.md` (§(d) 확장 로드맵이 본 다음단계의 원본 사양).

기존 적산 자산(N2·N3에서 결합):
- `app/models/v61_cost.py` — `BimQuantity`(테이블 `bim_quantities`: project_id, work_code, quantity, unit, qty_source 등), `MaterialUnitPrice`, `CostCalculationSheet`.
- `app/routers/cost.py:206` `_load_bim_quantities(db, project_id)` — 프로젝트 BIM 물량을 work_code 단위 합산 조회(있으면 list, 없으면 빈). :230 `bim_quantities_origin_cost` — BIM 물량 0건 시 `status='no_bim_quantities'` 정직 응답(가짜 0원 금지). `IFC_WORK_MAP`(ifc_work_map.py) — IFC타입→공종코드.
- `app/services/cost/unit_price_repository.py` — `get_price(key)`(async, DB 우선 fallback, 반환 {key,spec,unit,mat_unit,labor_unit,exp_unit,price_source,price_basis_year,region} 또는 None), `get_direct_sqm`, `get_prices`. `_KEY_TO_MATERIAL_CODE`(concrete/rebar/...→RC-001 등).
- `app/services/cost/boq_builder.py` → `origin_cost_calculator.py` — 12단계 법정요율 원가계산 체인(이미 apply-cost가 개산경로로 사용 중).

검증 베이스라인: pytest **3263 passed / 0 failed**, tsc·build 그린.
※ `tests/test_auction_demock_court.py`·`tests/test_molit_client.py` 2건은 **다른 세션 커밋**(경매·molit)으로 수집부터 깨짐 — 본 작업 무관, 전체 회귀 시 `--ignore` 둘. `unit/` 디렉터리(testpaths 밖 레거시 18건 실패)도 무관.

## 3. 다음 단계 구현 명세 (N1·N2·N3)

> 권장: **N3(단가결합) 우선** — 사용자가 체감하는 "금액까지 자동" 가치가 가장 크고, 전기 ref_mat_price 1,025건이 이미 있어 즉시 착수 가능. N2(BIM 병합)는 BimQuantity 적재 데이터에 의존. N1(N건 회귀)은 표본이 1건뿐이라 인프라만(코드 경로) 깔고 n≥3 전까지 배지 유지.

### N3 — 단가DB 결합 → 완전 내역서 (우선)
- **신규** `app/services/cost/boq_price_join.py`: `join_prices(draft) -> draft+`. 항목별로 단가 소스를 우선순위로 결합:
  1) 공종키 매핑(name/spec→`_KEY_TO_MATERIAL_CODE` 키) 가능 시 `unit_price_repository.get_price(key)` → mat/labor/exp_unit + price_source='db|fallback'.
  2) 전기 항목 ref_mat_price 보유 시 → 재료비 단가만 채움(price_source='도면참고단가', 노무·경비는 빈칸 유지·정직).
  3) 둘 다 없으면 단가 빈칸 유지(price_source=null) — **가짜 단가 금지**.
  금액 = qty × (mat+labor+exp). 항목에 {mat_unit,labor_unit,exp_unit,amount,price_source} 가산(전부 옵셔널). 매칭 통계(priced_count/total, coverage_pct)를 summary에 추가.
- **라우터** boq_auto.py: `POST /draft/priced` (draft 또는 params 수용 → generate_draft → join_prices) + `/draft/priced/export`(금액 포함 엑셀 — 단가칸 채움). 기존 /draft·/export 무수정.
- **엑셀** boq_excel_export.py: 금액 모드 분기(단가/금액 칸 채우고 공종별 소계·총계 행 추가) — 기존 빈칸 모드는 default 유지(하위호환).
- **apply-cost 정밀화**: draft에 금액이 있으면 `boq_builder` 개산 대신 **항목 합산 직접비 → origin_cost_calculator** 경로 옵션 추가(cost_source='boq_priced'로 정직 표기). 기존 개산 경로 폴백 보존.
- 테스트: join 우선순위·coverage 통계·전기 참고단가 단독 결합·미매칭 빈칸·금액 엑셀 소계.

### N2 — BIM 물량 우선 병합
- **신규** `app/services/cost/boq_bim_merge.py`: `merge_bim(draft, bim_rows) -> draft+`. bim_rows(=`_load_bim_quantities` 출력, work_code·quantity·unit)와 draft 항목을 work_code/공종 기준 정합. 우선순위 **user > bim > parametric**. BIM 매칭 항목은 qty를 실측치로 교체하고 `qty_source='bim'`, 비매칭은 `qty_source='parametric'` 유지. 단위 불일치는 변환 안 하고 경고(정직).
- **라우터**: `POST /draft/from-project {project_id, params}` — `_load_bim_quantities(db, project_id)` 호출(있으면 병합, 0건이면 parametric 그대로 + 안내). 기존 cost.py `_load_bim_quantities` 재사용(무수정).
- 프론트 BoqAutoWorkspace: qty_source 칩(BIM실측/추정) 표시, 병합 커버리지 배지.
- 테스트: 병합 우선순위·qty_source 플래그·BIM 0건 폴백·단위불일치 경고.

### N1 — 실적 N건 누적 → 계수 회귀 (인프라만)
- 추출기 `extract_boq_master.py`를 `data/boq_master/<project>/…` 프로젝트별 누적 구조 수용하도록 확장(현 단일 구조는 default 프로젝트로 유지·하위호환).
- **신규** `app/services/cost/boq_sample_stats.py`: 동일 항목(name,spec,unit)의 프로젝트별 원단위(qty/㎡) 표본 집계 → 평균·CV(변동계수)·n. n≥3이면 엔진 REF를 표본평균으로, 배지를 "실적 N건 기반·CV xx%"로 자동 갱신. **n<3이면 현 n=1 배지·단일표본 유지**(섣부른 일반화 금지).
- 엔진 generate_draft가 boq_sample_stats를 옵셔널 참조(없으면 현 동작 그대로).
- 테스트: n=1 현행 유지, 합성 n=3 표본으로 평균·CV·배지 전환.

## 4. 구현 후 검증 절차

```bash
# 1) 신규·관련 테스트
cd apps/api && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/test_boq_price_join.py tests/test_boq_bim_merge.py tests/test_boq_sample_stats.py \
  tests/test_boq_auto_api.py tests/test_boq_parametric_engine.py tests/test_boq_e2e_contract.py \
  tests/test_cost_router.py -q -p no:cacheprovider
# 2) 전체 회귀(2 pre-broken 제외, 기준 3263 passed 이상)
.venv/bin/python -m pytest -q -p no:cacheprovider \
  --ignore=tests/test_auction_demock_court.py --ignore=tests/test_molit_client.py
# 3) 프론트
cd ../../apps/web && pnpm exec tsc --noEmit && pnpm build
# 4) 라이브 시뮬레이션(서버 기동은 §1-7 방식)
#    simulate_boq_user.py 에 priced/from-project 시나리오 추가 후 7/7 → 9/9 확장
```

전부 그린이면 커밋(작업 브랜치) → `git push origin feature/trust-infra-2026-06-11`.
커밋 메시지 말미: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (모델은 실행 세션 기준).

## 5. 새 세션 첫 메시지 예시

> `propai-platform/docs/HANDOFF_BOQ_NEXTSTEPS_2026-06-13.md`를 읽고, §3의 N3(단가결합)→N2(BIM병합)→N1(N건 인프라) 순으로 구현해줘. §1 불변규칙 준수, §4 검증 통과 후 작업 브랜치에 커밋·푸시. main 푸시 금지.
