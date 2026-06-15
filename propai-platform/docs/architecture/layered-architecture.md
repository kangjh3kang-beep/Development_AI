# 계층형 아키텍처 — 살아 성장하는 개발사업 지원 에이전트 플랫폼

작성: 2026-06-15 · 성격: 진실 정렬(Phase 0). 본 문서는 마스터 spec
(`docs/superpowers/specs/2026-06-15-living-agent-knowledge-platform-design.md`)의
3계층을 코드 경계로 못박는다.

## 계층1 — 결정론 분석 코어 (불변, '진실의 원천')

8엔진 오케스트레이터(`apps/api/app/services/design_audit/design_audit_orchestrator.py`)·
18+ 도메인 서비스·룰 사전예측(`design_change_predictor.py`)이 **모든 수치를 산출**한다.

- **LLM은 절대 수치를 생성하지 않는다.** 면적·비용·확률·판정 등 정량값은 항상 결정론
  서비스가 계산하고, LLM은 그 결과를 **해석·종합·토론**하는 데만 쓰인다.
- **citation_gate**: LLM 발언은 결정론 결과에 citation으로 매핑될 때만 허용(미근거 발언 차단).
- 정직 표기: `data_source(live|fallback|mock|unavailable)`·`confidence`·`skipped` 유지.

## 계층2 — 프로젝트 지식저장소 (SSOT)

`analysis_ledger`(SHA256 해시체인, append-only)가 **유일한 무결성 원장**이다.

- write: 계층1 산출물이 `analysis_ledger_service.append_analysis(...)`로 누적(버전+해시체인).
- payload 규약: 모든 신규 적재 payload는 `schema_version`+`kind`를 포함하고, read는 키 추정이 아니라
  `payload.get("schema_version")`로 안전 파싱한다(스키마 드리프트 방지). 대용량 원시는 원장에 넣지 않고
  `source` 참조키(`audit_id`/`sha`/`task_id`)로 기존 테이블과 역연결한다.
- 정규화·중복: 멱등은 '직전-동일 `content_hash`'일 때만 생략이며 A→B→A 같은 비연속 재출현은 의도된 누적이다.
  `_canonical`은 키 정렬만 보장하므로 매퍼는 수치 표현(소수자리·결측 표기)을 호출부에서 정규화(SHOULD).
- 무결성: `content_hash = sha256(정규화 payload)`, `prev_hash = 직전 버전 해시`. 변조탐지는
  `verify_chain`(단건 체인) / `verify_all_chains`(테넌트·프로젝트 전 체인 일괄)로 수행.
- 감사 흡수: 감사 이벤트도 `analysis_type="audit"`로 같은 원장에 append(별도 해시체인 폐기).
- read(성장 루프): 다음 분석이 이전 원장 버전을 `prior_context`로 읽는 경로는 **Phase 1**에서 닫는다.
  `get_latest`는 `analysis_type` 지정 시 단건 dict, 미지정 시 타입맵을 반환하며 `payload`는 임의 타입일 수
  있다(소비측 `isinstance(payload, dict)` 가드 필요) — 이 계약을 Phase 1 `get_prior_context` 헬퍼가 흡수한다.

## 계층3 — 공동경영 멀티에이전트

`expert_panel`(토론)·`coordinator`(supervisor)·SpecialistAgent(신설 예정)가 계층1을
**도구로 호출**해 결과를 근거로만 발언한다(citation_gate). 실구현은 Phase 3.

## 경계 규칙 요약

| 계층 | 책임 | 금지 |
|---|---|---|
| 1 | 수치 산출(결정론) | LLM 의존, 비결정성 |
| 2 | append-only 누적·무결성 검증 | 덮어쓰기, 원장 우회 |
| 3 | 해석·토론·종합 | 수치 생성, 미근거 발언 |
