# Phase 4 — 실시간 이벤트·능동 위험감지 (착수 slice) Implementation Plan

> REQUIRED SUB-SKILL: executing-plans. 체크박스 추적.

**Goal:** 원장(ledger)을 능동 스캔해 **위험 이벤트**(고심각 모순·판정 fail·staleness)를 결정론으로 탐지하는 `risk_monitor` 서비스. Phase 2(contradiction/lineage)·P5(staleness)를 소비.

**Architecture:** 순수 분류 로직(`classify_risks`) + 체인 평가(`evaluate_chain_risk`: get_latest + lineage 엣지 max_severity + age) + 프로젝트 능동 스캔(`scan_project_risks`: 전 체인 집계). 원장·수치 불변(read·표면화). LLM 비개입. **실시간 이벤트** = `evaluate_chain_risk`를 append 시점 훅으로 호출 가능(이번 slice는 on-demand/scan API; 이벤트 버스·push 채널은 후속).

**불변규칙:** additive · 결정론 · 정직표기 · feature 브랜치 푸시만.

## File Structure
- Create `apps/api/app/services/ledger/risk_monitor.py`.
- Create `apps/api/tests/ledger/test_risk_monitor.py`.

## Task 1: risk_monitor (순수 분류 + 체인평가 + 프로젝트 스캔)
- [ ] 실패 테스트(`test_risk_monitor.py`): classify_risks 순수(고심각 모순+fail+stale→3위험 / clean→[]), evaluate_chain_risk(실DB: v1 적합→v2 부적합 → contradiction_high+status_fail), scan_project_risks(실DB: 위험 체인 집계).
- [ ] 실패 확인 → 구현 → 통과(skipped==0) → 회귀(tests/ledger) → 커밋.

핵심 API:
- `classify_risks(*, latest, contradictions, age_days, max_age_days=90) -> list[dict]` (순수): 고심각 모순(contradiction_high/high) · 판정 fail(status_fail/high, verdict 부적합/fail finding) · staleness(stale/medium).
- `evaluate_chain_risk(*, analysis_type, tenant_id, pnu, address, project_id, max_age_days=90) -> {risks, risk_level, version}` (실DB): get_latest + lineage.get_parents(max_severity) + staleness._age_days → classify.
- `scan_project_risks(*, tenant_id, project_id, max_age_days=90) -> {chains_at_risk, risk_level, chains}` (실DB): DISTINCT (analysis_type,pnu,address) → evaluate 각 → 위험만 집계.

## 후속(Phase 4.2): append 훅 실시간 배선 + 알림 채널(ws/telegram) + ML 위험예측층.
