# 새 세션 인계 — 적산(BOQ) 자동화 "다음 단계" (2026-06-14)

> 이 문서는 `HANDOFF_BOQ_NEXTSTEPS_2026-06-13.md`(N1·N2·N3 사양)의 **후속**이다.
> 그 문서의 N3(단가결합)·N2(BIM병합)·N1(N건회귀 인프라)는 **구현·커밋·푸시 완료**됐고,
> 이어서 **BOQ 워크스페이스 UI를 실제 백엔드 계약에 정합**시키고 N3/N2를 화면에 연결했다.
> 본 문서 §3 이 다음 구현 대상이다. 먼저 §1 불변규칙, §2 현재 상태를 읽고 시작하라.

## 0. 한 줄 요약

5공종 마스터(3,997항목, n=1) → **연면적·세대수 → 공내역서 초안**(수량) → **단가 결합(금액)**
→ **BIM 실측 우선 병합** 까지 백엔드+UI 모두 동작. 단가 커버리지 **≈56.5%**(전기 도면참고단가
1,025 + 표준품셈2025(DB) 83 + fallback 16). 남은 핵심은 ①실적 2건째 누적(n≥3 일반화 발동)
②단가 SSOT 공종 확장(커버리지↑) ③BIM 실데이터(bim_quantities) 적재 연동.

## 1. 불변 규칙 (위반 금지 — 1차와 동일)

1. **브랜치**: `feature/trust-infra-2026-06-11` 에서 작업. **main 직접 푸시 금지**. 작업 브랜치만 푸시(remote `git@github.com:kangjh3kang-beep/Development_AI.git`). 레포 루트는 `~/My_Projects/Development_AI`(서브디렉터리 `propai-platform/`).
2. **additive·하위호환**: 기존 응답 키·store·테스트 계약 0개 변경. 단가/금액/출처는 새 옵셔널 키로만 가산.
3. **정직 표기**: 가짜 단가·날조 수치 금지. 미매칭·단위불일치 항목은 **단가/금액 빈칸(null)** 유지하고 "—"로 표기. 표본 n=1 동안 `confidence='낮음(n=1)'`·"전문 적산 검토 필수" 배지 유지. 데이터 없으면 "데이터 없음".
4. **출처 플래그**: `qty_source ∈ {user, bim, parametric}`, `price_source ∈ {db출처문자열, fallback, 도면참고단가, null}` 를 항목별 표기.
5. **결정론**: LLM 0. 스케일링·병합·단가결합·표본통계 모두 규칙 기반.
6. **검증(WSL)**: venv `apps/api/.venv`, 프론트 `pnpm`. 전체 회귀는 `cd apps/api && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_auction_demock_court.py --ignore=tests/test_molit_client.py` (※`pytest.ini`의 `testpaths=tests`는 **레포 루트 기준**이라 positional `tests/`를 **반드시 명시**해야 `apps/api/tests`가 수집됨. 명시 안 하면 엉뚱한 트리+`unit/` 레거시 18실패를 수집한다).
7. **서버 기동**: uvicorn은 **플랫폼 루트에서 `PYTHONPATH=.:apps/api`** — `cd propai-platform && PYTHONPATH=.:apps/api apps/api/.venv/bin/uvicorn apps.api.main:app --port 8901`. (apps/api에서 직접 띄우면 `No module named 'packages'/'app'` 으로 죽음.)
8. **계약 함정(실측·반드시 숙지)**:
   - 요청 body는 **`{ "params": { "gfa_sqm", "households"? }, "disciplines"? }` 중첩 필수**. 평탄형 `{gfa_sqm}`은 **422**. apply-cost·from-project는 상단 레벨 `project_id` 필수.
   - 응답 `disciplines`는 **dict**(한글 공종명 키: 건축/기계소방/전기통신소방/조경/토목), 배열 아님.
   - `confidence` 값은 `"낮음(n=1)"` 또는 `"실적 N건 기반·CV xx%"`(영문 `low` 아님).
   - 프론트 `apiClient`는 `/api/v1` 접두를 붙인다 → 라우트 상수에 `/api/v1` 넣지 말 것. export/apply-cost 라우트는 `/draft/export`·`/draft/apply-cost`(`/draft` 누락 주의).

## 2. 현재 상태 (커밋)

- **1차(`f70b42d` feat(boq))**: N3/N2/N1 백엔드.
  - `app/services/cost/boq_price_join.py` — `join_prices(draft, prices=None)`. 키워드→단가SSOT(단위정합)·전기 `ref_mat_price` 단독결합·미매칭 빈칸. `summary.pricing`.
  - `app/services/cost/boq_bim_merge.py` — `merge_bim(draft, bim_rows)`. user>bim>parametric, work_code(IFC_WORK_MAP)→항목 1:1 정합 교체. 모호·단위불일치 미적용. `summary.bim_merge`.
  - `app/services/cost/boq_sample_stats.py` — 원단위 평균·CV·n. `REF_MIN_N=3`. `load_projects`/`load_sample_stats`(프로젝트별 누적 구조·평면 하위호환).
  - `app/services/cost/boq_parametric_engine.py` — `generate_draft(..., sample_stats=None)` N1 훅(n≥3 시 표본평균·배지 전환). 미제공 시 현 동작 보존.
  - `app/services/cost/boq_excel_export.py` — `build_xlsx(draft, *, priced=False)` 금액 모드(단가/금액칸·공종 소계·총계 시트).
  - `app/routers/boq_auto.py` — `POST /draft/priced`, `/draft/priced/export`, `/draft/from-project`; `apply-cost`에 `priced_cost_estimate`(boq_priced 12단계 법정요율) 가산.
  - `scripts/extract_boq_master.py --project <name>`(누적), `scripts/simulate_boq_user.py`(라이브 9/9).
  - 별도 `5eef3d2 fix(web)`: 타 세션 705ac7d 가드 중복라인 22파일 복구(빌드 그린화).
- **2차(이번 — 미커밋/커밋예정)**: UI 정합 + N3/N2 화면 연결.
  - `apps/web/components/cost/boqAutoTypes.ts` — `BOQ_AUTO_API` 라우트 정정(+priced/pricedExport/fromProject), `disciplines` dict 유니온, `BoqDraftRequestBody`(중첩), `BoqApplyCostResponse`/`BoqPricedCostEstimate` 실제 형태, item N2/N3 옵셔널 키.
  - `apps/web/components/cost/BoqAutoWorkspace.tsx` — disciplines dict 정규화(`getDisciplineItems`/`allDraftItems`), 요청 `{params}` 중첩, **생성 모드 토글(수량만/단가·금액/BIM 병합)**, 금액 열·`PriceSourceChip`, 단가/BIM/N1 커버리지 배지, apply-cost 실제 응답(개산+priced 블록) 렌더, BIM모드 엑셀 정직 라벨.
  - `apps/api/tests/test_boq_e2e_contract.py` — `/draft/priced`·`/draft/from-project` 오프라인 계약 테스트(실엔진).

검증 베이스라인: 1차 pytest 전체 **3298 passed / 0 failed**(2 pre-broken ignore), tsc·build 그린, 라이브 9/9. 2차 tsc·build 그린, e2e 신규 2 passed, omc 적대적 검증(3렌즈+스켑틱) 통과(반영 완료).
※ `tests/test_auction_demock_court.py`·`tests/test_molit_client.py`(경매·molit, 타 세션 수집부터 깨짐)·`unit/`(testpaths 밖 레거시 18실패)는 **본 작업 무관** — 회귀 시 위 §1-6 명령으로 분리.

## 3. 다음 단계 (우선순위)

### A. 실적 2건째 누적 → N1 일반화 발동 (최우선·체감 큼)
- 2번째 실무 공내역서를 `extract_boq_master.py --project <식별자>` 로 `data/boq_master/<project>/` 에 추출(평면 구조는 default 프로젝트로 자동 인식).
- `generate_draft` 호출부(라우터)에서 `boq_sample_stats.load_sample_stats()` 결과를 `sample_stats=` 로 주입하는 배선 추가(현재는 옵셔널 인자만 존재, 라우터 미주입). n≥3 항목은 자동으로 표본평균·"실적 N건·CV%" 전환.
- 테스트: 합성 2~3프로젝트로 `load_sample_stats`→`generate_draft(sample_stats=...)` 전환 + 라우터 주입 경로.

### B. 단가 SSOT 공종 확장 → 커버리지 정직 상승
- 현재 6키(concrete/rebar/formwork/masonry/waterproof/window)+전기 도면참고단가. 기계/마감/토목/조경 공종 단가키를 `standard_quantity_estimator.UNIT_PRICES_2026`(fallback) 및 `material_unit_prices`(DB 시드, `cost_tables_bootstrap`)에 추가.
- `boq_price_join._PRICE_KEYWORD_RULES` 에 신규 키 키워드 매핑 + 단위 추가. **단위 정합 가드 유지**(날조 금지).
- 테스트: 신규 키 결합·단위 불일치 빈칸·coverage 상승.

### C. BIM 실데이터(bim_quantities) 적재 연동 → N2 실측 surface
- IFC 분석 산출물 → `bim_quantities`(project_id, work_code, quantity, unit) 적재 파이프라인 확인/연결. 적재되면 `/draft/from-project` 가 실측 우선 병합을 자동 표기(현재 0건 폴백).
- `boq_bim_merge._SYNONYMS`/IFC_WORK_MAP 커버리지 점검(콘크리트↔레미콘 등 실항목명 정합).

### D. BIM/금액 엑셀 라우트 보강
- `/draft/from-project/export`(BIM 병합 결과 엑셀) 신설 — 현재 bim 모드 UI 엑셀은 추정 물량만(정직 라벨로 안내 중). `merge_bim`→`boq_excel_export.build_xlsx` 경로.

### E. apply-cost → costData 실제 반영 경로
- 현재 `persisted=false` 후보만. `priced_cost_estimate`(boq_priced)를 기존 COST 모듈 "공사비 정밀 분석 → 수지 반영" 흐름으로 적용하는 사용자 확인형 경로.

### F. UI 런타임 스모크(권장)
- 정합은 tsc·build·오프라인 계약테스트로 검증했으나 실제 브라우저 렌더(인증+프로젝트 필요)는 미검. Playwright/preview 로 `/[locale]/(dashboard)/projects/[id]/boq` 3모드 스모크.

## 4. 구현 후 검증 절차

```bash
# 1) 신규·관련 테스트
cd apps/api && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/test_boq_price_join.py tests/test_boq_bim_merge.py tests/test_boq_sample_stats.py \
  tests/test_boq_auto_api.py tests/test_boq_parametric_engine.py tests/test_boq_e2e_contract.py \
  tests/test_cost_router.py -q -p no:cacheprovider
# 2) 전체 회귀(positional tests/ 명시, 2 pre-broken 제외, 기준 3298 passed 이상)
.venv/bin/python -m pytest tests/ -q -p no:cacheprovider \
  --ignore=tests/test_auction_demock_court.py --ignore=tests/test_molit_client.py
# 3) 프론트
cd ../../apps/web && pnpm exec tsc --noEmit && pnpm build
# 4) 라이브 시뮬(서버 기동은 §1-7) — simulate_boq_user.py 9/9
```

전부 그린이면 커밋(작업 브랜치) → `git push origin feature/trust-infra-2026-06-11`.
커밋 메시지 말미: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`(모델은 실행 세션 기준).
※ 커밋 시 `.omc/template-version.json`(하네스), `propai-platform/_workspace/…`(타 세션)는 **스테이징 제외**.

## 5. 새 세션 첫 메시지 예시

> `propai-platform/docs/HANDOFF_BOQ_NEXTSTEPS_2026-06-14.md`를 읽고, §3-A(실적 2건째 누적→N1 일반화 라우터 주입)부터 구현해줘. §1 불변규칙 준수, §4 검증 통과 후 작업 브랜치에 커밋·푸시. main 푸시 금지.
