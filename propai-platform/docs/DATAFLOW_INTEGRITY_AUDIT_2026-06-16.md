# 데이터흐름 무결성 종합감사 + 보강 계획 (2026-06-16)

작성: 배포 코디네이터 세션 · 방법: 3개 병렬 감사 에이전트(파이프라인-컨텍스트 단선 / 분석 연동 정합 / 데이터품질 검증루프) → **배포 코디가 실코드로 적대적 재검증**(에이전트 결과 맹신 금지 — 일부 부정확 확인).
목적: 사용자 요청 "단선·병목 분석 + 최적연동 + 반복루프 데이터품질 극대화 검증 + 부족분 보강 + 탄탄한 구현계획".

> ⚠️ **세션 디컨플릭트**: 검증/원장/파이프라인 코어는 **트러스트-인프라 세션의 활성 작업(플랫폼 진화 P0~P4 + 개선 로드맵)** 도메인. 본 문서는 그와 **충돌 없이** 실행되도록 담당을 명시한다(아래 §4). 배포 코디는 코어 미수정.

---

## 0. 검증 상태 범례
- ✅ **검증됨**: 배포 코디가 실코드로 확인.
- ⚠️ **부분/요재검증**: 에이전트 보고했으나 실코드 일부 불일치 — 구현 전 재확인 필요.

## 1. 근본원인 3가지
1. **단선(프론트 미소비)**: 백엔드 파이프라인이 `stage.data`(dict[str,Any])에 풍부한 산출을 담지만, 프론트 Data 타입(DesignData/CostData…)이 일부 필드만 명시 read → 나머지 산출이 어디서도 소비 안 됨(lazy binding). 계약 부재가 원인.
2. **검증/신뢰/원장 루프 미연결**: validator·trust·verifier·ledger 모듈이 **정의는 됐으나 라이브 분석 경로에 미연결** → "데이터품질 극대화 반복루프"가 폐루프를 못 이룸.
3. **연동 정합(상수 이원화)**: 공사비/간접비/평단가/분양가가 여러 곳에서 서로 다른 상수·로직으로 계산 → 1~3% 불일치 + 적정분양가는 원가 미참조.

## 2. 단선 — 파이프라인 ↔ 프론트 (배포 코디 lane: 프론트)
| 심각도 | 단선 | 위치 | 상태 |
|--------|------|------|------|
| HIGH | 설계 `unit_types`/`unit_mix_revenue_won` 산출이 store 미저장 → 수지 세대구성/매출 pre-fill 누락 | project_pipeline.py(설계) ↔ useProjectContextStore.DesignData / projects/[id]/page.tsx updateDesignData | ⚠️ 필드 매핑 재확인 |
| HIGH | 공사비 `material_quantities` 산출이 store/BOQ 미소비 → BOQ 수작업 의존 | project_pipeline.py(cost) ↔ CostData(materialQuantities 필드 없음) | ⚠️ |
| MEDIUM | 설계 `compliance` 검증결과 store 미저장 | project_pipeline.py(design compliance) ↔ ComplianceData 복원부 | ⚠️ |
| MEDIUM | stage별 상세(tax/esg)가 summary 필드로만 전달 → cost_breakdown 손실 | routers/pipeline.py summary 추출 ↔ 프론트 Data 타입 | ⚠️ |
| LOW | `applied_overrides`(편집이력) store 미저장 → SSOT 편집추적 불가 | project_pipeline.py ↔ DesignData | ⚠️ |
| — | (에이전트가 "comprehensive_report 미전달" 보고했으나 ❌**부정확**: collect_comprehensive 데이터는 pre_collected로 실제 병합됨. project_pipeline.py:461~487 확인) | — | ✅ 반증됨 |

→ **공통 해법**: 파이프라인 stage별 응답 정식 스키마 ↔ 프론트 Data 타입 1:1 계약화. 프론트 store/page 매핑 보강은 **배포 코디 lane**(백엔드 코어 불변).

## 3. 데이터품질 검증·신뢰 루프 미연결 (★대부분 트러스트-인프라 lane)
| 심각도 | 항목 | 위치 | 상태 | 담당 |
|--------|------|------|------|------|
| CRITICAL | 파이프라인 5단계에 VerifierService 호출 0건 | project_pipeline.py(`.verify(` 검색 0) | ✅ **확정** | trust-infra |
| CRITICAL | analysis_ledger **읽기·피드백 루프 0건**(write전용 → staleness/재분석 제안 부재) | analysis_ledger_service.py | ✅ 트러스트-인프라 핸드오프가 "단일 최대 갭"으로 자인 = **그들의 P1** | trust-infra |
| HIGH | trust.cross_validate 호출 2곳(avm·분양가)뿐 | trust.py | ⚠️ | trust-infra |
| HIGH | FreshnessChecker/AnomalyDetector/PublicDataRegistry/CalculationMetadata 분석경로 미연결 | validator.py·public_data_registry.py·calculation_metadata.py | ⚠️ 호출수 재확인 | trust-infra |
| MEDIUM | 외부데이터 실패 silent 폴백 → "unavailable" 미표기 잔존(market_report 등) | market_report_service.py:260·274 등 | ⚠️ (nearby-map은 이미 본 세션서 정직표기 완료) | 공동 |

→ **배포 코디 미수정**(충돌 회피). 트러스트-인프라 로드맵에 합류 권고.

## 4. 연동 정합 — 공사비/수지/ROI/분양가 (혼재 lane)
| 심각도 | 불일치 | 위치 | 상태 |
|--------|--------|------|------|
| HIGH | 간접비 산정에 조경 포함/제외 경로 이원화(최대 1.5% 차) | cost.py:123 vs design_v61.py:438 | ⚠️ |
| HIGH | 구조 가중계수(SRC 1.15 등) design_v61 경로 누락 | cost.py:106 vs design_v61.py:433-436 | ⚠️ |
| MEDIUM | **적정분양가가 공사비(원가) 미참조** — 정밀공사비 갱신해도 분양가 불변 | suggest.py(`construction_cost` 검색 0) | ✅ **확정** |
| MEDIUM | 직접공사비 단가 상수 3곳 중복정의 | construction_cost_engine.py·unit_price_repository.py·cost.py | ⚠️ |
| MEDIUM | 전용률 0.747 하드코딩(유형별 미반영, 오피스텔 등 ~3% 오차) | suggest.py:27 | ✅ 상수 확인 |

→ **해법**: 간접비/구조계수/단가/전용률을 단일 함수(SSOT)로 통일 + 적정분양가에 원가기반 최저가 검증 추가. 일부는 트러스트-인프라가 건드린 cost/feasibility와 겹침 → **머지 후 공동 조율** 권고.

## 5. 우선순위·실행 배분 (충돌 회피)
1. **트러스트-인프라(코어·진행중)**: §3 전부(검증 강제·원장 피드백 루프·신뢰/신선도 연결) — 그들의 P0~P4 로드맵. 본 문서를 입력으로 제공.
2. **배포 코디(프론트·정합, 비충돌)**: §2 프론트 단선 매핑 보강(unit_types/material_quantities/compliance → store), §4 적정분양가↔원가 연동(suggest.py·확정 항목).
3. **공동 조율(머지 후)**: §4 상수 SSOT 통일(cost/feasibility 겹침).

## 6. 결론
- **신뢰 가능(견고)**: 연결결산·할루시네이션 가드(verify 라우터)·적정분양가(거래사례)·실거래지도·계정격리·정직표기(nearby-map)·블루그린 무중단·원장 무결성 체인.
- **최대 갭**: **데이터품질 반복루프 미폐쇄**(검증·원장 read 미연결) = 트러스트-인프라 P1의 핵심. + 프론트 단선(산출 미소비) + 정합 상수 이원화.
- **다음 실행**: §5-2(배포 코디 비충돌 항목)부터 — 단, 각 항목 **구현 전 file:line 재검증 필수**(에이전트 부정확 사례 있었음).