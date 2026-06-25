# 심의/설계도면 자동분석엔진 — 벤치마크·갭분석·구현 로드맵 (2026-06-19)

다층 정보취합(외부 유사플랫폼·논문·기술 3트랙 + 내부 대량필지 통합분석·엔진 현황 3트랙) → 종합 분석.
오케스트레이터 워크플로 산출(7 에이전트, 근거: 외부 출처 URL·내부 file:line). 목적: 엔진이 목표(멀티모달 AI
심의분석+설계도면자동분석 중심엔진)에 최적·완벽 구현되고 있는지 냉정 검증 + 차용안 + 우선순위 계획.

## 최적성 판정 — 약 7.0/10 (목표 9.5 미달)

신뢰성/추적성 **설계 철학은 SOTA급**이나 "최적·완벽 구현"은 과장 — **형식보장·운영가동·입력편의 3축이 9.5를 막음**.

**강점(코드 검증)**
- 11계층 파이프라인이 단일 `run_analysis`(analysis_pipeline.py:55)에 무손 배선.
- INV-1..33 33개 전부 코드 존재 + emit 게이트로 집행.
- 설명가능성(CalcTrace held_reason·legal_refs 27조문 1차출처·Rationale·FinalGate 강등사유·reg_graph 조문본문)이
  전 산출에 일관 — 랜드북/스페이스워크/밸류맵/Forma/TestFit/Deepblocks가 **비공개로 둔 영역** = 명확한 차별점.
- 결정론(input_hash·vision temp=0+cache·교차검증 다수결)·공급/소비 분리 AST 강제·SSRF 화이트리스트.

**냉정한 약점(9.5 블로커)**
- (a) 결정론을 **주장하나 인프라 레벨(batch-invariant)로 증명 안 함**.
- (b) 수치규제 **SMT/Z3 형식보장 부재**(외부: F1 1.0 vs LLM 0.308).
- (c) 엔진 **운영 미가동**(LIVE_NETWORK off·키 미주입·worker 미기동·BFF engine_url="") → 전 경로 degrade.
- (d) **도면 업로드 인테이크/OCR/PDF분할 부재** → 사용자가 image_ref JSON 손작성(UX 격차).

## 갭 (severity·근거)

| # | 갭 | sev | 근거 |
|---|---|---|---|
| 1 | 수치규제 SMT/Z3 형식보장 부재(unsat-core 강등사유 기계산출 없음) | HIGH | grep z3/smt 0건; arxiv 2601.06181 F1=1.0 vs 0.308 |
| 2 | 인프라 결정론 미증명(batch-invariance 회귀 없음) | HIGH | grep batch.invariant 0건; lmsys 2025-09-22 |
| 3 | 엔진 운영 미가동(중심엔진 미실현) | HIGH | config engine_url=""·shadow off; integration_status mock |
| 4 | 도면 업로드 인테이크/OCR/PDF분할 부재 | HIGH | upload/ocr/pdf_split 파일 0건 |
| 5 | 중심엔진 승격가치 0(shadow가 echo sanity) | MED | shadow_mappers.py:7; quant_rel_err 항상 None |
| 6 | 규제 환각 능동가드 부재(IFCD/RTO temporal abstention/CFRT) | MED | grep 0건; SSRN 6747439 CLARA |
| 7 | 인용오류 taxonomy 미세분(e2/e3/e4 미구분) | MED | final_gate 4종; arxiv 2510.08111 7카테고리 |
| 8 | 고위험 HITL Human-Auth 게이트·override-rate 부재 | MED | hitl_task=R2용; EU AI Act Art.14 |
| 9 | bi-temporal point-in-time 규제재현 부재 | MED | grep 0건; arxiv 2511.07585 |
| 10 | 대량/지구단위 일괄처리 미흡(30필지 하드코딩·배치큐 없음) | MED | auto_zoning parcels[:30] |
| 11 | E2E 라이브 통합테스트 부재(434 passed=mock) | MED | SERIES_COMPLETE '다음' |
| 12 | 입력 정보요구(IDM/MVD) 프리체크 부재 | LOW | Automation in Construction 2026 |

## 차용안 — 대량필지 통합분석시스템 → 심의/설계도면 엔진

1. **결정론 규칙기반 게이트**(`special_parcel.py:276` detect_*는 전부 LLM무의존) → 엔진 R3 "확정 가능 룰은 결정론" 강화(SMT 전 단계).
2. **"가장 제약 큰 필지가 전체 좌우" 발산차단**(`special_parcel.py:299`): 1필지라도 해결불가 → 규모산정 거부 → **엔진 FinalGate "치명 위반 1건이면 정량산출 거부"** 구조적 할루시네이션 차단으로 이식.
3. **다출처 면적 교차검증+신뢰도 임계**(`auto_zoning.py:614` 토지대장 vs 지적도 5% → high/low) → 도면 geometry_area vs VLLM vs IFC `cross_validate`에 **FD(±임계) 게이트**로 직접 차용.
4. **additive 무손상 try/except**(`auto_zoning_service.py:392`) → 엔진 SMT/HITL/abstention 레이어 도입 시 동일 패턴.
5. **shapely union-find 인접+union 외곽선**(`auto_zoning.py:686`) → 통합개발 merged_geometry를 엔진 도면해석/자동배치 입력으로 연결(현재 렌더만 소비=단선).
6. **zone_source 출처 정직표기**(`auto_zoning_service.py:96`) → 엔진 extraction source 신뢰등급 표면화와 통합.
7. **far_tier 계층완화**(min(법정,조례)→지구단위→기부채납, `far_tier_service.py:70`) → 엔진 완화추론을 SMT soft-constraint로 형식화하기 전 한국형 골격.

## 차용안 — 외부(검증 출처)

- **Neuro-Symbolic(LLM+SMT/Z3)**: 수치규제 Z3 인코딩 → 위반 UNSAT 결정론검출·unsat-core 강등사유·soft-constraint 완화제시. arxiv 2601.06181, SYNAPSE.
- **Batch-invariant 결정론 게이트**: single/mixed/prefix×50 unique==1 + num_splits=1 커널. lmsys 2025-09-22.
- **규제 환각 taxonomy 가드**(temporal abstention·cross-framework disambiguation·IFCD). SSRN 6747439.
- **인용오류 7-카테고리 taxonomy** → FinalGate enum. arxiv 2510.08111.
- **bi-temporal SSOT + point-in-time retrieval**. arxiv 2511.07585·2601.06216.
- **Chain-of-Verification 적대 재검증**(domain_agents를 peer-review로). arxiv 2309.11495.
- **도면해석 6단계 모듈화 + 벡터/래스터 듀얼패스 + 선분류→LLM 2단**. CGF 2024 Raster-to-Graph·ArchCAD-400K.
- **VLM 역할분담**(VLLM=시맨틱만, 정량=벡터·기하 결정론+이중경로). arxiv 2503.02861·PlanGPT-VL.
- **RASE 규제태깅 + CODE-ACCORD 온톨로지** 추출 출력스키마. mdpi 2673-4109·PMC11779898.
- **토지이음/LURIS 개방 API**를 reg_graph 정기동기화·staleness 소스로(eum.go.kr 화이트리스트 보유).

## 우선순위 구현계획 (effort·confidence)

| 순위 | 항목 | effort | conf |
|---|---|---|---|
| P1 | 엔진 운영 가동(키+LIVE_NETWORK+worker+BFF engine_url+shadow) → doctor live·E2E 1건 | M | high |
| P2 | 인용오류 7-카테고리 taxonomy → FinalGate 강등사유 enum (저비용 고효과·차별점 정량화) | S | high |
| P3 | 차용2: FinalGate "치명 위반 1건→정량산출 거부" 구조적 가드 | S~M | high |
| P4 | 차용3: cross_validate FD(±임계) 다출처 교차검증 게이트 | M | high |
| P5 | 도면 업로드 인테이크(INC-17): /analyze/upload·PDF분할·드래그앤드롭 | M | high |
| P6 | SMT/Z3 neuro-symbolic 정량검토 레이어(위반 UNSAT·unsat-core 강등사유) | L | high |
| P7 | batch-invariant 결정론 회귀게이트 | M | high |
| P8 | 규제 환각 가드(temporal abstention+IFCD+CFRT) | M | med |
| P9 | 중심엔진 shadow stage3 승격(독립산출 노출→quant_rel_err 실측) | L | med |
| P10 | bi-temporal SSOT·HITL Human-Auth·CoVe·OCR(INC-18) | L | med |

## 배포 준비도

- **지금 degrade-safe 배포 가능(코드완성)**: 엔진 11계층(mock/결정론 폴백)·BFF 740줄(인증·멱등·parity·degrade·alembic 032/033)·프런트 운영카드+콘솔. ⚠️ `page.tsx`의 "PREVIEW/통합예정" 표기가 실상(라이브 배선)과 괴리 → 정직성 원칙상 표기 갱신 후 배포.
- **키/인프라 대기(라이브 승격)**: ANTHROPIC/VWORLD/MOLIT/Qdrant 키, Celery worker+redis+beat, LIVE_NETWORK=on, 두 .env API_TOKEN(≥32B) 동일값 + engine_url + shadow on.
- **배포 금지(미구현)**: 업로드 인테이크·OCR·SMT·bi-temporal·authoritative 승격·다중워커(redis 공유 breaker).
- **권고 순서**: 코드완성분(표기갱신 후) degrade-safe 선배포 → 키/인프라 주입 라이브 승격 → 트래픽 누적 후 shadow stage3.

---
*근거 전문: 워크플로 산출(외부 3트랙 RESEARCH + 내부 3트랙 INTERNAL → 종합). 본 문서는 후속 세션의 구현 기준선.*
