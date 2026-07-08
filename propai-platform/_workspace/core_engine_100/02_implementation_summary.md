# 핵심엔진 100% — 구현 요약 (2026-07-08, feat/core-engine-100-completion)

5개 병렬 레인(파일 소유권 분리) 구현 완료. base=origin/main bec93a20.

## Lane BE-1: 심의 코어 배선 소생
- **A1** project_pipeline `_run_design_review` 죽은 import(`_post_analyze`/`_wrap_result` 부재) → 실존 `_engine_post_analyze`+`_compat_fields` 정렬. 파이프라인 design_review 단계 소생(기존: 항상 무음 SKIPPED). rules measured=0 날조 제거(무날조).
- **A2** specialist_dispatch `zone_type`→`use_zone` 계약키 교정(기존: 엔진 100% NEEDS_INPUT 공회전). 신규 공용 SSOT `app/services/agents/engine_inputs.py`(build_deliberation_engine_input/build_design_engine_input/build_bcr_far_rules) — decision_brief·dispatch 공유.
- **A3** registry `_build_deliberation`/`_build_design`에 PermitInterpreter/DesignInterpreter 주입(market 선례 복제·graceful). +2차 dead-path 발견·수정: 인터프리터가 `prior_context` kwarg 미지원인데 무조건 전달→TypeError→claims 영구 [] → inspect.signature 호환 호출.
- **A4** dispatch ok 엔트리에 `claims`·`recalled_count` 추가(FE DecisionSpecialistCard가 이미 claim 소비 — FE 무수정 표면화).
- **A5** SpecialistAgent.run `allow_llm=True` 게이트 — comprehensive는 allow_llm=False(무과금 유지), decision_brief는 use_llm 경로만 LLM.
- **C3** capture_service.record_fallback 공용계약 + producer 2곳(registry 엔진실패, ledger verify_chain broken=kind 'ledger_broken') → healing_rules 죽은 2룰 각성.
- **C5** specialist_agent 기본 ingester `.delay`→`dispatch_memory_ingest`(PR#173 패턴 전파 잔여).
- 테스트 334 passed(신규 26 포함), net≤2 엔진콜 계약(test_permit_capacity) 무손상.

## Lane BE-2: 설계엔진 SSOT 관통
- **B1** BimGenerateRequest에 ordinance_far_pct/bcr_pct additive → 자동산출 분기 SiteInput 주입(_effective_limits min 클램프·엔진 무수정). /layout ordinance None 하드코딩 제거.
- **캐시오염 실버그 발견·수정**: 신규 필드가 `_request_fingerprint`에 누락→조례값만 다른 요청이 같은 캐시 충돌. 회귀테스트 잠금.
- **B2** special_parcel_gate.py 공용 게이트(detect_special_parcel 재사용) → /mass·/bim·/layout·seed-design additive `special_parcel` 부착(경고·무차단·입력부족 시 정직 생략).
- 테스트 223 passed(신규 14).

## Lane BE-3: 성장루프 read-back(학습→행동)
- settings_readback.py 신설(TTL캐시+schema_guard 재사용): analyzer가 threshold.fallback_warn_pct 오버라이드 실참조(자기참조 단선 해소·연속보정 활성), feature_flags evaluate current 자기값, feature.llm_narrative 설정우선.
- 프롬프트 A/B 이중 빈 dict → platform_settings `prompt_candidates.<service>` 단일 소스(화이트리스트 유지·임의문자열 채택 불가). main.py 인프로세스 learn→`_learn_async`(프롬프트 후보 생성 포함).
- 성장 사이클 시뮬레이션 harness 13건 신규. 총 49 passed.
- 안전: 기존 ±20% 클램프·시간당 캡·쿨다운 불변. 현재 버전 라벨은 텔레메트리/캐시키만 분기(콘텐츠 분기 없음=안전).

## Lane BE-4: 심의 시나리오 매트릭스(다경우수 시뮬레이션)
- POST /api/v1/deliberation/scenario-matrix: base+scenarios(≤12) → overrides 4축(완화 relaxation_states·대안 rules 패치·종상향 use_zone[ZONE_LIMITS 실치환]·calc_targets 변형) 깊은병합 → 기존 analyze 흐름(prevalidate·멱등캐시·_engine_post_analyze·감사) 재사용 N회 전개, Semaphore(4)+예산가드, 시나리오별 verdict/key_criteria/deltas 비교. 무과금(결정론)·graceful(unavailable 정직).
- 테스트 12 신규, 심의 계열 177 passed 무회귀.

## Lane FE-1: use_llm 공용화 + 핸드오프 복구
- UseLlmToggle 공용 컴포넌트 + 7경로 배선(동작보존 기본값: 기존 OFF→기본 false, 기존 항상ON→기본 true 명시전송). 인라인 3곳 치환.
- 핸드오프 복구: ComprehensiveAnalysisPanel(contradictions 경고카드·score_breakdown·regulation_notes/risk_level/risk_factors·buildable_options_interpretation), SolarPlacementCard envelope, DeliberationResultPanel sim_metrics/precedent/qualitative.
- CadBimIntegrationPanel에 zoning-ssot resolveFarPct/resolveBcrPct 기반 ordinance 주입(BE-2 계약).
- tsc 0·eslint 신규 0·vitest 관련 61 통과(사전결함 5건 무관 확인).

## 알려진 환경 제약
- 로컬 검증 venv에 reportlab 미설치 → tests/test_decision_brief_pdf.py·test_pdf_xml_escape_builders.py 수집 불가(origin/main에서도 동일 재현=기존 환경결함, CI 통과 대상).
- 검증 환경 = py3.12 venv(메인 워크트리 .venv 대여).

## 배포 후 라이브 점화 조건(운영)
- 심의/설계 LLM 해석: decision_brief use_llm=true 경로에서 ANTHROPIC_API_KEY 유효 시 발화.
- record_fallback → healing: 다음 heal 사이클(10분)부터 fallback 이벤트 소비.
- 프롬프트 A/B: improvement_agent가 prompt_candidates.<service> 등록 후부터.
- INTERP_FEWSHOT=1(few-shot go-live)은 별도 운영 결정(이번 PR 미포함).
