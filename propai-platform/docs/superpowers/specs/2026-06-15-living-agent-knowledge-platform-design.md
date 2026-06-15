# 마스터 설계 — 살아 성장하는 개발사업 지원 에이전트 플랫폼

작성: 2026-06-15 · 브랜치 `feature/trust-infra-2026-06-11` · 상태: **마스터 spec(승인 대기)** · 성격: 플랫폼 진화 리팩토링(additive)

> 이 문서는 5단계(Phase 0~4)를 아우르는 **마스터 spec**이다. 각 Phase는 승인 후 별도 구현 plan(`docs/superpowers/plans/`)으로 분해한다. 코드 실측은 멀티에이전트 audit(2026-06-15)으로 file:line 확보했고, 외부 비교분석은 동일 세션 웹조사로 보강했다.

---

## 0. 비전과 한 줄 결론

**비전(사용자)**: 분야별 전문 에이전트가 개발사업 전주기를 지원하고, 문제·위험을 사전 도출/예측/회피하며, 프로젝트별 통합 지식저장소(블록체인처럼 모든 수집·조사·분석·입력 자료를 통합·빅데이터화)에 정보가 쌓일수록 더 정확·다층적이 되는 '살아 성장하는' 공동경영 에이전트 시스템.

**결론**: 비전의 빌딩블록 다수가 **이미 구현돼 동작 중**이다(그린필드 아님). 단일 최대 격차는 *"원장에 쌓기만(write) 하고 다음 분석이 그걸 읽지(read) 않는다"* — '쌓일수록 정확해지는' 성장 루프가 코드 레벨에서 닫혀 있지 않다. 새 플랫폼이 아니라 **이 루프를 닫고(Phase 1) 그 위에 토론형 멀티에이전트를 올리는(Phase 3) additive 리팩토링**으로 비전에 도달한다.

---

## 1. 불변규칙 (전 Phase 적용 — 위반 금지)

1. **브랜치**: `feature/trust-infra-2026-06-11`에서만 작업. main 직푸시·머지 금지. 배포(머지·alembic 적용·prod)는 별도 배포 담당 — 이 작업은 커밋·푸시까지.
2. **additive·하위호환**: 기존 키/엔드포인트/스토어/테스트 계약/8엔진/DesignReviewResult/원장 스키마 불변, 신규만 추가. 모든 마이그레이션은 additive(컬럼/테이블 추가, 기존 변경·삭제 금지).
3. **결정론 코어 불변**: 계층1(8엔진·18 도메인·룰예측)은 '진실의 원천'. **LLM은 절대 수치를 생성하지 않는다**(해석·종합·토론만). 수치는 항상 결정론 서비스가 산출하고 LLM은 그 결과를 근거로만 발언한다(citation_gate 코드게이트로 강제).
4. **정직 표기**: 가짜/날조 값 금지. data_source(live|fallback|mock|unavailable)·confidence·skipped 유지. silent failure 금지(except→`logger.warning`, 원장 append 실패가 분석을 막지 않음).
5. **무결성**: 블록체인 미도입. 검증된 **내부 SHA256 해시체인 + verify_chain**으로 한정(사용자 결정: 내부 해시체인으로 충분). Merkle/외부앵커링은 범위 밖.
6. **갭 판단은 실코드 file:line 인용**(과거 audit가 EXISTS를 MISSING으로 반복 오판).
7. 커밋 푸터 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## 2. 확정 결정 (2026-06-15, 사용자)

| # | 결정 사항 | 선택 | 설계 반영 |
|---|---|---|---|
| D1 | 착수 범위 | **전체 0~4 마스터 spec 먼저** | 이 문서 = 마스터, Phase별 구현 plan 분해 |
| D2 | 성장루프 학습 범위 | **전체 cross-project 유사사례** | §6 프라이버시 가드 필수 설계 |
| D3 | Phase 3 우선 도메인 | **전 도메인 동시**(asset/development/transaction/finance) | SpecialistAgent 4종 동시 구현 |
| D4 | 무결성 수준 | **내부 해시체인으로 충분** | Merkle/앵커링 미구현, verify_chain만 |

---

## 3. 외부 비교분석 (벤치마크 — 설계 근거)

- **경쟁 플랫폼**: TestFit(설계생성)·Deepblocks(취득)·Archistar(인허가 확률)·Northspyre(PM)는 대부분 **단일기능 특화**. PropAI는 8엔진+18도메인 **전주기 폭**을 이미 보유 → '살아 성장'이 경쟁사가 못 가진 해자.
- **멀티에이전트**: 업계는 **Supervisor/orchestrator-worker**를 가장 프로덕션-검증된 패턴으로 수렴. LangGraph(상태·추적성)가 결정론·감사성과 정합. → 새 프레임워크 없이 expert_panel(토론)+coordinator(supervisor)로 구현.
- **지식 축적**: GraphRAG **데이터 플라이휠**("모든 산출물이 지식그래프로 되돌아가 스스로 똑똑해진다") + 에이전트 메모리 3계층(episodic/semantic/procedural) + "학습 커밋 전 human-gate". → PropAI의 빠진 read 루프가 정확히 이것이며, DomainAgentApproval이 곧 memory-write gate.
- **위험 예측**: ML(XGBoost/GBDT 87~92%, BIM+신경망 전주기 조기경보)은 유효하나 PropAI는 현재 룰기반만. → 로드맵 밖 후속(Phase 1 데이터 축적 이후, 정직성 유지하며 추가).
- **무결성**: append-only 해시체인이 기본, Merkle/앵커링은 선택. PropAI `analysis_ledger`가 이미 SHA256 해시체인 → '블록체인처럼'의 80% 구현됨.
- **하이브리드**: 2025/26 정설 = "LLM 실행·수치생성 금지, 제안만→제어층 검증". PropAI 정직표기+LLM 해석전용+citation_gate가 **이미 이 정설을 체화** → 순수-LLM 경쟁사보다 앞섬(불변규칙으로 고정).

---

## 4. 목표 아키텍처 — 3계층

```
계층3  공동경영 멀티에이전트   expert_panel 토론(기존) · SpecialistAgent(신설) · 다계층 승인큐(확장)
          ▲ 해석·토론·종합            ▼ 도구 호출(결정론)
계층2  프로젝트 지식저장소(SSOT)  analysis_ledger 해시체인(기존) · Lineage DAG(신설) · 유사사례 검색(신설)
          ▲ write: append             ▼ read: prior_context  ← 성장 루프(Phase 1, 최대 갭)
계층1  결정론 분석 코어(불변)     8엔진 오케스트레이터 · 18 도메인 서비스 · 룰 사전예측
```

**성장 루프**: 계층1 산출 → 계층2 append(이미 가동) → 다음 분석이 계층2를 read(prior_context)로 입력 → 계층1 재계산이 더 정확. 이 read 경로 신설이 Phase 1의 핵심.

---

## 5. 현재 자산 실측 (file:line)

**계층1 (견고)**
- 8엔진 오케스트레이터 `apps/api/app/services/design_audit/design_audit_orchestrator.py:54` — asyncio.gather 병렬, skipped 정직판정, LLM 미개입 결정론.
- 18+ 도메인: feasibility/permit/auto_zoning/cost(boq)/registry/disaster_risk/esg(lca)/auction/regulation/market/environment/land_intelligence …
- 룰 사전예측 `apps/api/app/services/design_risk/design_change_predictor.py:95`(초과/누락/간섭 3종).
- 검증 가드 `apps/api/app/services/verification/verifier_service.py`(수치모순·내부모순), 토론 `apps/api/app/services/expert_panel/expert_panel_service.py:21`(9유형 ROSTER, single/deep).

**계층2 (절반 구현 — 핵심 발견)**
- `apps/api/app/services/ledger/analysis_ledger_service.py` — SHA256 content_hash + prev_hash 해시체인, append-only, **verify_chain**(변조탐지), **get_latest/get_history** 구현. `apps/api/app/services/pipeline/project_pipeline.py:425`에서 매 스테이지 자동 append **가동 중**.
- `apps/api/app/services/feasibility/version_control_db.py` — SHA1 커밋·parent_sha DAG·브랜치.
- `apps/api/database/init_qdrant.py` — Qdrant 3컬렉션(regulations/design_references/**project_documents**, 1536-dim). `reference_image` feature_vector_json(`apps/api/services/reference_image_service.py`).

**계층3 (가장 미성숙)**
- `expert_panel_service.py:21` = 최고 레버리지(토론 ROSTER 이미 존재).
- 단 `apps/api/agents/propai_orchestrator.py`는 순차 파이프라인+LLM 보고서 1회, `apps/api/core/coordinator.py:9`는 `pass` 스텁, `apps/api/app/services/agents/`는 빈 폴더.
- domain_agents: `apps/api/services/domain_agents_service.py:20`(_score 결정론 가중치), 모델 `apps/api/database/models/phase_f_domain_agents.py:13`(DomainAgentTask/Approval).

**미영속 결함**: `apps/api/app/services/audit/audit_service.py:77` self._entries는 in-memory list(SHA256 체인은 구현, DB 영속 경로 없음).

---

## 6. 프라이버시 가드 (D2 전체 cross-project 학습의 필수 설계 요건)

전체 cross-project 학습은 정확도가 최대지만 테넌트 경계를 넘으므로, 다음을 **강제 설계 제약**으로 둔다(정직성·격리 양립):

1. **원시 데이터 비참조**: 타 프로젝트의 원시 문서·확정수치를 그대로 노출/주입하지 않는다. 학습 입력은 (a) feature_vector(임베딩), (b) 집계통계(분포·중앙값), (c) 익명 사례 메타(용도지역·지역·개발유형)로 한정.
2. **결정론 재계산 우선**: 유사사례는 '참고 힌트/사전분포(prior)'로만 쓰고, 신규 프로젝트의 수치는 항상 계층1이 재계산한다(LLM·타 사례가 수치를 확정하지 않음).
3. **익명 표기**: 출처는 "유사 사례(타 프로젝트·익명, N건)"로 표기. 식별 가능한 주소·고객·금액 원문 노출 금지.
4. **opt-out**: 테넌트/프로젝트 단위 cross-project 학습 제외 플래그(기본 on, 민감 프로젝트는 off 가능). 같은-프로젝트 학습(prior_context)은 항상 동작.
5. **격리 검증 테스트**: 타 테넌트 원문이 응답에 유출되지 않음을 회귀 테스트로 박제(Phase 1 수용기준).

---

## 7. 핵심 갭 (6)

1. **🔴 성장 피드백 루프 부재(단일 최대)**: `ledger.get_latest/get_history` 구현됐으나 입력으로 읽는 분석 서비스 0건(유일 소비처=리포트 조립).
2. **진짜 멀티에이전트 협업 부재**: cross-domain 충돌(설계변경↔수지↔인허가) 조율·합의 오케스트레이터 없음.
3. **Lineage/provenance 엣지 부재**: 시간축 체인만, 인과 DAG(입력→출력) 없음 → 모순감지·'왜' 설명 불가.
4. **감사추적 비영속**: audit_service in-memory.
5. **실시간 성장 체감 부재**: 완료 이벤트 자동 push 없음(수동 폴링).
6. **규제 변경 자동반영 부재**: 모니터 존재하나 능동 반영 없음.

---

## 8. 단계적 로드맵 (Phase 0~4)

각 Phase: 목표 · 단위(units) · 레버리지(기존자산) · additive 마이그레이션 · 수용기준(metric/test). 가치순+의존성순.

### Phase 0 — 진실 정렬 + 무결성 단일화 (1~2주, 위험 0)
- **목표**: 기존 자산을 비전 언어로 매핑하고, 흩어진 해시체인 무결성을 `analysis_ledger` 단일 SSOT로 수렴. 새 기능 없이 신뢰 가능하게.
- **단위**: (a) 아키텍처 문서에 계층1/2/3 경계·LLM 비수치 규칙 명문화. (b) in-memory AuditTrailService를 ledger와 동일 DB append-only 패턴으로 영속화(또는 ledger에 `audit` analysis_type으로 흡수). (c) verify_chain 온디맨드/주기 점검 엔드포인트 노출(함수 배선만). (d) design_audits·feasibility_vcs·DomainAgentTask 산출물을 ledger append 경로로 일원화하는 어댑터(기존 테이블 유지).
- **레버리지**: analysis_ledger_service(완성), audit_service(SHA256 로직), version_control_db(DAG 패턴), pipeline.py:425 기존 append.
- **마이그레이션**: audit_trail 영속 테이블 추가(additive).
- **수용기준**: 모든 산출물이 단일 원장 체인에 append, verify_chain이 전 프로젝트 '변조 없음' 반환, 감사로그 재시작 후 0건 소실.

### Phase 1 — ★ 성장 루프 닫기: 원장 read 경로 (2~3주, 최고 가치)
- **목표**: 분석 서비스가 같은 PNU·프로젝트의 이전 원장 버전 + (cross-project) 유사사례를 입력으로 읽어 '쌓일수록 정확'을 코드로 실현.
- **단위**: (a) comprehensive_analysis·design_audit·feasibility 진입부에서 `ledger.get_latest`(같은 PNU/프로젝트)를 `prior_context`로 주입(없으면 무영향). (b) BaseInterpreter 9개 해석 프롬프트에 prior_context 근거블록 + '이전 결론과 모순 시 명시' citation_gate 규칙. (c) cross-project 유사검색(Qdrant project_documents·feature_vector top-k) — **§6 프라이버시 가드 적용**. (d) 지식 성숙도 지표(체인 길이·확정수치 커버리지·confidence 추세)를 ledger에서 계산·노출.
- **레버리지**: ledger.get_latest/get_history, base_interpreter 그라운딩+캐시, reference_image feature_vector·Qdrant project_documents, comprehensive_analysis/design_audit 진입부.
- **마이그레이션**: 없음(읽기 경로) / Qdrant project_documents 인덱싱 배선.
- **수용기준**: 동일 프로젝트 N차 분석 prior_context 주입률 100%, 이전 확정수치 재계산 모순 0건(verifier 통과), 유사사례 힌트가 confidence/다층성에 측정 가능 개선, **타 테넌트 원문 유출 0건(격리 테스트)**.

### Phase 2 — Lineage DAG + 모순 감지 (2~3주)
- **목표**: 버전 체인(시간축)에 분석 간 인과 엣지(입력→출력)를 더해 provenance·신뢰도 전파·모순 감지.
- **단위**: (a) lineage 엣지 테이블(child_hash, parent_hash, relation: derived_from/contradicts/refines). (b) Phase1 prior_context 출처를 lineage 엣지로 자동 기록. (c) verifier 확장 — 체인 내 수치 모순(예: 이전 GFA↔현재 GFA) lineage 따라 탐지·플래그. (d) '왜 이 결론' 추적 엔드포인트(결론→입력→법적근거→도메인결정).
- **레버리지**: ledger 해시체인(child/parent 해시=엣지 키), verifier_service(모순 룰), design_audit make_finding legal_refs.
- **마이그레이션**: analysis_lineage 테이블 추가(additive).
- **수용기준**: 임의 결론에서 입력·법령·도메인결정까지 lineage 100% 추적, 주입 prior_context 대비 수치 모순 자동 플래그(거짓음성 0 목표).

### Phase 3 — 전문 에이전트화 + 토론 오케스트레이션 (4~6주, 심화)
- **목표**: expert_panel을 코어로, domain_agents·결정론 서비스를 도구로 'specialist agent = 결정론 결과를 근거로만 발언하는 LLM 페르소나'를 **4 도메인 동시(D3)** 구현하고 cross-domain 충돌을 토론으로 조정.
- **단위**: (a) 빈 `app/services/agents/`에 SpecialistAgent 기반클래스 — 도메인 결정론 서비스 호출→ROSTER 페르소나로 결과 근거 발언(citation_gate, BaseInterpreter 패턴). asset/development/transaction/finance 4종. (b) coordinator.py 스텁→실 조정 로직: 단계별 적합 에이전트 활성화 + cross-domain 충돌 탐지 시 expert_panel deep-debate 트리거. (c) domain_agents 4스코어를 통합 risk-reward로 재해석하는 reconcile(portfolio_summary 확장). (d) 합의 결과를 DomainAgentApproval 다계층 심의로 라우팅.
- **레버리지**: expert_panel ROSTERS·single/deep, domain_agents 스코어·승인큐·batch decide, base_interpreter citation_gate, phase_f_domain_agents 모델, propai_orchestrator 단계 디스패처 골격.
- **마이그레이션**: 없음(또는 합의/충돌 기록 컬럼 additive).
- **수용기준**: cross-domain 충돌 시 토론→통합권고가 단일 에이전트 대비 높은 verifier grounded_score, 다계층 승인이 2개+ 이해관계자 관점 분리 기록, 모든 에이전트 발언이 결정론 결과에 citation 매핑(미근거 발언 0). 비용가드: 단일모드 기본, 충돌 탐지 시에만 deep(coordinator 게이트) + 테넌트 쿼터.

### Phase 4 — 실시간 성장 이벤트 + 능동 위험감지 (2~3주)
- **목표**: 분석완료·규제변경·모순탐지를 자동 publish해 '살아 성장' 체감과 사전 위험 회피.
- **단위**: (a) 파이프라인/분석 완료 시 event pub/sub(append→notify→SSE push) — realtime.ts·socialWs.ts 소비 인프라 연결. (b) regulation_monitor 능동화 — 법령 변경 감지 시 영향 프로젝트 원장에 `risk` analysis_type 자동 append + 알림. (c) 설계 변경 시 영향 도메인(수지·인허가) 자동 재계산 신호(Phase2 lineage dirty 전파). (d) 변경예측·disaster_risk를 원장 위험 타임라인으로 통합 노출.
- **레버리지**: realtime.ts·socialWs.ts, notification_service 다채널, regulation_monitor assess_impact, Phase2 lineage.
- **마이그레이션**: 없음(또는 event_log additive).
- **수용기준**: 완료→협업자 push 지연 측정(폴링 제거), 모니터 법령변경 영향 프로젝트 자동 플래그율 100%, 설계변경 시 종속 분석 재계산 신호 누락 0건.

### 로드맵 밖 후속 (별도 의사결정)
- **ML 위험예측층**: XGBoost/GBDT 공기·원가 리스크(외부 87~92% 사례). Phase 1 데이터 축적 이후, '데이터 부족 시 skip' 정직성 유지하며 추가. 별도 spec.

---

## 9. 리스크 & 완화

| 리스크 | 완화 |
|---|---|
| LLM이 결정론 경계 침범(수치 생성) | agent는 결정론 호출 결과 근거로만 발언, 수치 생성 금지를 코드게이트(citation_gate)로 박제 |
| 모순된 과거데이터 무비판 주입 | Phase 2 모순감지를 Phase 1 직후 배치, prior_context는 '참고' 표기·신규 결정론 재계산 우선 |
| 토론 비용·지연 폭증 | 단일모드 기본, cross-domain 충돌 탐지 시에만 deep(coordinator 게이트), 테넌트 쿼터 |
| cross-project 데이터 유출 | §6 프라이버시 가드(feature_vector·집계만, 익명, opt-out, 격리 테스트) |
| lineage/이벤트가 파이프라인 성능 저하 | additive·비동기 append, 기존 캐시·인덱스 활용, 실패 무중단(append 실패가 분석 불방해) |

---

## 10. 분해 & 다음 단계

- 이 마스터 spec 승인 후 **Phase 0부터 순차로 구현 plan(`docs/superpowers/plans/2026-XX-XX-phaseN-*.md`)으로 분해** → TDD 구현 → 검증 → 커밋·푸시.
- 각 Phase는 독립 배포 가능 단위(additive)이며, 이전 Phase가 다음의 전제(0→1→2→3→4).
- 배포(머지·alembic 적용·prod)는 별도 배포 담당.
