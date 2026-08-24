# PLAN — 분석 자가검증 파이프라인 (Analysis Self-Audit Layer)

작성: 2026-07-24 · 통합자 세션 · 상태: **계획 확정(실행 승인 대기)**
근거 감사: 호미곶 산1-1 외 2필지(보전관리 임야) 7패널 종합분석 필드 정확성 감사 (동일 세션)

---

## 0. 문제 정의 (왜 필요한가)

세션마다 사람(LLM 리뷰)이 잡아내는 분석 오류를 **플랫폼 스스로** 매 분석마다 잡게 만든다.
현재 플랫폼은 **정직성(모르면 판정불가)** 과 **grounding(생성문이 근거있나)** 은 검증하지만
**정확성(결정적으로 계산된 필드값이 도메인상 맞나)** 은 검증하지 않는다. 이번에 발견한 결함이 그 증거:

| # | 결함 | 계층 | 근본원인 | 현행 게이트 통과 이유 |
|---|------|------|----------|----------------------|
| D1 | 군사(방공기지) 통제/제한보호구역인데 **종합 리스크 "낮음"** | A | `risk_keywords`가 `"군사시설보호"`만 매칭, `통제보호/제한보호/방공기지` 누락 | 값이 존재(=정직성 통과), 서술 근거도 있음(=grounding 통과) |
| D2 | 대보초 1곳을 **학교 5개교**로 오카운트→입지점수 부풀림 | A | POI dedup이 좌표근접만, `운동장/병설/체육관`(다른 이름·같은 모학교) 미병합 | 상동 |
| D3 | 보전/생산/계획 관리지역 **인허가 판정불가** | A | `ZONE_PERMIT_MATRIX`에 관리지역 미등재 | 판정불가=정직성으로 통과(정확성 아님) |
| D4 | 토지시세를 **공시지가×1.2 고정**(실거래 미반영) | B | Section 3이 desk_appraisal 교차검증·실거래 원/㎡ 미사용 | 방법론 검증 부재 |
| D5 | 실거래 최저 2만원(지분/정정) 잔존·apt 혼입·**단가 미정규화** | B | Section 4가 거래총액 평균, robust_price_stats를 단가 기준 미적용 | 분포·품질 게이트 부재 |
| D6 | 경사도(기구현)·산림 **고아 데이터**(전부 NEEDS_OFFICIAL_SURVEY) | B/A | terrain_service 산출값이 special_parcel에 미주입 | 수집가능/실측필요 미분리 |

**핵심 원리:** 박제하는 것은 *값*이 아니라 *규칙·관계·출처·방법론*. 값은 런타임에 권위 소스에서 신선하게
당겨오고, 검증기는 "그 값이 규칙에 맞는가"만 본다 → 수시변동 데이터에도 검증기가 안 낡는다.

---

## 1. 목표 / 비목표

**목표**
- 결정적 필드층에 **정확성 검증 게이트** 신설(현행 정직성·grounding과 병렬).
- 발견 결함 6건을 **회귀 골든**으로 박제, 재발을 결정적으로 차단.
- 검증 규칙을 **공용 모듈**에 축적 → 한 곳 고치면 전 분석·전 엔드포인트에 적용(전역 전파방지 정책).
- 수시변동 데이터는 절대값이 아니라 **분포소속·출처·신선도·방법론**으로 검증.

**비목표(이번 캠페인 범위 밖)**
- 새 외부 데이터 소스 신규 연동(기존 VWorld/MOLIT/KOSIS/desk_appraisal 재사용).
- 분석 알고리즘 전면 교체(검증층 + 6개 결함 국소 수정만).
- LLM 검증을 core-path 동기 의존으로 만들기(반드시 best-effort·off-path 유지).

---

## 2. 아키텍처

### 2.1 계층별 검증 메커니즘 (데이터 변동성 기준)

| 계층 | 데이터 | 검증 방식 | 위반 정책 |
|---|---|---|---|
| **A. 불변 규칙** | 용도지역 제한·용적률 법정한도·규제→리스크·POI정의·면적합 | **하드 불변식**(pure assert) | P0=차단(소비처), P1=제자리 교정+배지 |
| **B. 수시변동 수치** | 실거래·공시지가·금리·시세·통계 | ①방법론 태그 ②동적분포 이상치 ③출처·신선도 TTL ④교차 삼각검증 | **경고+배지**(비차단) |
| **C. 오라클 없는 추정** | 적정분양가·수익성·흡수율 | 방법론 정합 + 신뢰구간/시나리오 + LLM sanity | 정직성 표기(불확실 명시) |

### 2.2 모듈 구조 (신설: `services/verification/field_audit/`)

기존 `services/verification/`(range_rules·verifier_service·calc_ledger·hotpath_guard) 확장.
`range_rules.run_range_checks(add(sev,claim,note))` 패턴과 `_emit_growth_verdict/_emit_growth_issues` 훅 재사용.

```
services/verification/field_audit/
  __init__.py
  contracts.py         # AuditFinding(code,severity,panel,field,expected,observed,rule_id,tier), AuditReport
  rules_registry.py    # @register 데코레이터 + iterate — 규칙 1개 = pure fn (AnalysisResult)->list[AuditFinding]
  runner.py            # run(result, ctx)->AuditReport ; growth emit ; result["field_audit"] 첨부
  invariants/          # 계층 A
    coverage.py        #  등장 zone/코드가 매트릭스·룩업에 등재됐나(미등재=finding)
    cross_field.py     #  규제→리스크 하한 / POI dedup 정합 / 면적합 / far≤법정한도
  volatile/            # 계층 B (대부분 기존 헬퍼 래핑)
    distribution.py    #  robust_price_stats 단가(원/㎡) 기준 이상치 소속
    freshness.py       #  public_data_registry·calculation_metadata TTL/출처 게이트
    triangulation.py   #  desk_appraisal_service.cross_validate 교차 삼각검증
    methodology.py     #  시세=comparable 원/㎡ 정규화 태그 확인
  oracleless/          # 계층 C
    confidence.py      #  점추정 금지·신뢰구간/시나리오 요구·불확실 정직성
  llm_auditor.py       # 어드버서리얼 필드 감사(grounding과 별개, best-effort·off-path)
```

**공용 헬퍼 승격(전역 전파방지 — 결함 국소패치 금지):**
- `services/regulation/protection_zone_severity.py`(신설) — 보호구역 키워드→severity SSOT.
  소비: `regulation_analysis_service`, `comprehensive_analysis_service`(~1595·~1649), `land_info_service`(~1322).
- `kakao_local_service.dedup_school_cluster()`(신설) — 모학교 클러스터 병합. 소비: `site_score_service`.
- `permit_validator.get_permitted_types()` 확장 + `coverage.py`가 미등재 zone을 자동 finding화.

### 2.3 파이프라인 삽입점

`comprehensive_analysis_service.analyze()` — 모든 섹션 조립 후(현 ~L806~808 special_parcel/warnings 첨부 직후, `return result` 직전):
```python
audit = field_audit.runner.run(result, ctx={"address": address, "zone_type": zone_type, "use_llm": use_llm})
result["field_audit"] = audit.to_dict()      # 프론트 검증 배지 소스
# growth emit은 runner 내부에서 best-effort
```
- 개별 엔드포인트(`site_score`, `land_price /estimate`, `market`)도 해당 계층 규칙 서브셋 호출 가능(공용 runner).
- **성능:** 계층 A/B 불변식은 이미 계산된 result에 대한 pure O(n) — 무시 가능. LLM 감사기는 `use_llm` 게이트·async·캐시·best-effort(verifier와 동일 정책) → core-path 지연 0.

### 2.4 거버넌스 (차단 vs 경고)

- **Tier A P0(D1 유형: 군사·개발제한·상수원 리스크 하한):** 1단계=경고+눈에 띄는 배지. 골든 안정 후 2단계=
  **소비처 하드 차단**(design-audit·인허가 체크리스트 등 과대낙관 소비처가 위험한 값을 못 받게).
- **Tier A P1(D2·D3):** 제자리 교정(dedup·매트릭스가 올바른 값을 직접 산출) + 배지.
- **Tier B/C:** 경고+배지만, 절대 차단 안 함(수시변동 안전).
- 전 규칙 `FIELD_AUDIT_ENABLED` + per-rule enable map 뒤에 배치 → 즉시 무력화 롤백 가능(additive).

---

## 3. Wave별 실행계획

각 서브PR 공통 게이트: **R1 어드버서리얼 리뷰(code-reviewer) → 변이주입으로 골든 flip 증명 → tsc/eslint/pytest → 라이브검증 → 기록**. 공유파일 편집 전 `scripts/coord.sh claim`.

### Wave 0 — 계약·골격·골든 하네스 (behavior 불변, additive)
- **산출물:** `contracts.py`·`rules_registry.py`·`runner.py`(no-op 규칙셋)·growth emit 배선·`field_audit.runner`를 analyze()에 삽입(빈 리포트 첨부).
- **골든 시드 6건**: 결함 입력을 frozen fixture로 캡처, **현행(오류) 출력을 assert**(추후 수정이 flip함을 증명하는 기준선). `tests/services/verification/field_audit/golden/`.
- **게이트:** 신규 테스트 CI 등록. 출력 변화 0.
- **규모:** ~0.5d · PR 1건.

### Wave 1 — 계층 A 하드 불변식 (최고 심각도·결정적)
- **W1-1 [P0 D1] 규제→리스크 하한 + 보호구역 키워드 SSOT**
  - `protection_zone_severity.py` 신설(통제보호/제한보호/방공기지/비행안전/군사/개발제한/상수원→severity). 3개 소비처를 이 SSOT로 수렴(전역 스윕).
  - `cross_field.py`: "규제목록에 보호구역 포함 → 종합리스크 ≥ 매핑 하한" 불변식.
  - 골든: 호미곶 → 리스크 **높음**(현 "낮음" flip). 변이: 키워드 1개 제거 시 테스트 FAIL 확인.
- **W1-2 [P1 D2] POI 학교 dedup 불변식**
  - `dedup_school_cluster()`: 이름 정규화(운동장·체육관·병설·분교 접미 제거)+좌표근접으로 모학교 병합. `site_score_service`가 소비.
  - `cross_field.py`: "school_n = dedup된 고유 모학교 수" 불변식(원카운트와 불일치 시 finding).
  - 골든: 대보초 **5→1**, 입지점수 학교 보너스 재계산. 변이: dedup 우회 시 FAIL.
- **W1-3 [P1 D3] 매트릭스 커버리지 어설션 + 관리지역 등재**
  - `ZONE_PERMIT_MATRIX`에 보전/생산/계획 관리지역 항목 추가(국토계획법 별표 근거).
  - `coverage.py`: 등장 zone이 매트릭스·용적률 룩업에 없으면 finding(판정불가로 조용히 끝내지 않고 "커버리지 갭" 표면화).
  - 골든: 보전관리 → 공급면적·분양가 **산출**(판정불가 해소) 또는 근거명시 정직표기.
- **규모:** ~2.5–3d · PR 3건(각 스윕+R1).

### Wave 2 — 계층 B 수시변동 안전망 (기존 헬퍼를 게이트로 승격·배선)
- **W2-1 [D4] 토지시세 방법론 교정 + 삼각검증 배선**
  - Section 3을 공시지가×1.2 → **실거래 원/㎡ comparable** 경로로(desk_appraisal_service.cross_validate 배선).
  - `methodology.py`: "시세 필드는 comparable·단가정규화 태그를 가져야" 불변식. `triangulation.py`: 공시/실거래/감정 N배 격차 경고.
- **W2-2 [D5] 실거래 품질 게이트**
  - Section 4에 robust_price_stats를 **단가(원/㎡)** 기준 적용 + 지분/정정/타물건종류(apt) 필터. `distribution.py` 동적 IQR 소속.
- **W2-3 [D6-부분·출처] 신선도·출처 게이트 승격**
  - freshness/public_data_registry를 표시→**관문**. stale/unknown-source → 배지(비차단).
- **정책:** 전부 경고+배지(비차단). **규모:** ~2d · PR 2–3건.

### Wave 3 — 계층 C + LLM 어드버서리얼 + 지형/산림 배선
- **W3-1 LLM 필드 감사기(`llm_auditor.py`)** — 결정적 필드값+근거+원본을 도메인/법령 대조로 challenge(grounding과 별개). off-path·best-effort·캐시. 발견→배지+platform_insights.
- **W3-2 [C] 오라클 없는 추정 정직성** — 적정분양가 등 점추정→신뢰구간/시나리오, 불확실 명시(`confidence.py`).
- **W3-3 [D6] 경사도/산림 고아 배선** — terrain_service(SRTM 30m 평균경사도) → special_parcel 주입, **수집가능(경사도)/실측필요(입목축적)** 분리. 수집가능 항목이 None이면 finding.
- **규모:** ~2d · PR 2–3건.

### Wave 4 — 자가치유·학습 폐합 (성장엔진 연결)
- 감사 findings → `growth/healing_rules`·`improvement_agent`: 반복 finding 유형 자동 감지→수정 제안/few-shot 주입.
- 계층 B 기준선(지역·지목별 정상 원/㎡ 범위, IQR 배수)을 `platform_insights`에 **누적 관측으로 학습·갱신**(하드코딩 금지) → 데이터가 변할수록 검증기가 정교해짐.
- admin/대시보드에 감사 verdict 서피스.
- **규모:** ~1.5d · PR 2건.

---

## 4. 골든 회귀 시드 (박제 대상)

| 시드 | 입력(frozen) | 현행(오류) | 수정후(정답) | 검증 계층 |
|---|---|---|---|---|
| G1 | 호미곶 산1-1(통제보호 방공500m) | 리스크 낮음 | 리스크 ≥ 높음 | A cross_field |
| G2 | 대보리 입지 POI | 학교 5개교 | 학교 1(대보초) | A cross_field |
| G3 | 보전관리 임야 | 인허가 판정불가 | 공급면적 산출 or 근거명시 | A coverage |
| G4 | 호미곶 토지 시세 | 공시지가×1.2 | 실거래 원/㎡ comparable | B methodology |
| G5 | land 실거래(최저 2만원) | 2만원 잔존·apt혼입 | 지분/정정/apt 제외·단가정규화 | B distribution |
| G6 | 임야 특이부지 | 경사도 None | terrain_service 주입값 | B/A freshness |

각 시드: 변이주입(가드 무력화)시 테스트 FAIL을 반드시 확인(가드가 실재함을 증명).

---

## 5. 시퀀싱·마일스톤·규모

```
W0(하네스) → W1(계층A·최우선) → W2(계층B) → W3(LLM+C+지형) → W4(자가치유)
             └ W1-1 P0 최우선(가장 심각한 오도 즉시 봉합)
```
- **의존:** W1~W3는 W0 하네스 선행. W1-1/1-2/1-3 상호 독립(병렬 가능). W2는 W0만 의존. W4는 W1~W3 findings 필요.
- **멀티세션:** `verification/`·`comprehensive_analysis_service.py`·`kakao_local_service`·`permit_validator`는 공유 → 편집 전 `coord.sh claim`, 서브PR 작게.
- **총 규모:** ~8–9 dev-day(병렬 시 단축). **권장 착수 순서: W0 → W1-1(P0) → W1-2 → W1-3 → W2 …**

---

## 6. 성공 지표 / 완료 게이트

- **골든 6건 전부 flip**: 현행(오류)→정답, 각 변이테스트로 가드 실재 증명.
- **호미곶 산1-1 라이브 재분석**: 리스크≥높음·학교 1·관리지역 공급면적 산출·시세 실거래 원/㎡ 근거.
- **커버리지**: 7패널 각 ≥1 불변식 부착.
- **성능 회귀 0**: core analyze() 지연 불변(LLM 감사기 off-path 확인).
- **성장 폐합**: 반복 finding 자동감지 라이브.

---

## 7. 리스크 & 완화

| 리스크 | 완화 |
|---|---|
| 하드 차단이 정상 케이스 오차단(false positive) | 1단계 경고+배지로 시작, 골든/실사용 안정 후에만 P0 차단 승격. per-rule enable map |
| 매트릭스/키워드 확장이 다른 용도지역 회귀 | coverage 어설션이 미등재를 표면화하되 기본은 비차단. 기존 골든 유지 |
| 계층 B 기준선이 과적합/편향 | 하드코딩 금지·platform_insights 누적학습, 분포는 런타임 산출. 교차 삼각검증으로 단일소스 편향 방지 |
| LLM 감사기 지연/비용 | off-path·best-effort·캐시·use_llm 게이트. 실패해도 core 반환 불변(verifier 정책 동일) |
| 멀티세션 공유파일 충돌 | coord.sh claim/release·전용 워크트리·작은 서브PR |

---

## 8. 착수 시 첫 커밋(승인 후)

1. `coord.sh claim verification/field_audit` + 전용 워크트리.
2. W0: contracts·runner 골격 + 골든 6 fixture(현행 assert) + analyze() 삽입(빈 리포트) → PR(additive).
3. W1-1: protection_zone_severity SSOT + cross_field 리스크 하한 + G1 골든 flip → R1 → 라이브검증(호미곶 리스크 높음).

> 이 계획은 CLAUDE.md 버그수정 정책("정답 기준선과의 격차로 패턴 정의 → 공용화 → 전역 스윕")을
> **런타임에 플랫폼 스스로 매 분석마다 적용**하게 만드는 것이다. 지금은 사람이 세션마다 하는 일을.
