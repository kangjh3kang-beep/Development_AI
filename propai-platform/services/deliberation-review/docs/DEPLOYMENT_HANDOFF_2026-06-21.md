# 배포 인계 — 인·허가/심의 + 설계 라이프사이클 스킬 (2026-06-21)

> 콜드 스타트 배포자용. 이 세션에서 구축한 두 스킬 + 설명가능성 + 참조법규 + Phase 2를 운영에 올리는 절차.
> ★제약: 비밀키/시크릿·실인프라 변경은 **사용자 승인·실값 필요 — 임의 실행 금지, 각 단계 사용자 확인**.
> 전 과정·결과: docs/SESSION_PROGRESS_2026-06-21.md. 코드: 브랜치 feature/deliberation-review(origin kangjh3kang-beep/Development_AI).

## 1. 구축 내용 (모두 9.5 적대 게이트 HIGH 0 통과)

- 시스템1 인·허가/심의(PD1~PD6): 선언적 프로세스 스펙 + 얇은 결정론 실행기. 엔진 라우트 + 심의 SpecialistAgent.
- 시스템2 건축설계 라이프사이클(DL1~DL3 + 설계 에이전트): 동일 실행기 재사용(6단계 + 완결성).
- 설명가능성 기본화(EX1 엔진·EX2 플랫폼): 모든 결과물에 근거(법령·조항·요지)+링크 동반.
- 참조법규: _REFS 26→71(집합건물법 등) + resolve_text 접두앵커. 끊긴링크 2건 해소·orphan §77 배선.
- Phase 2: P2A 결과예측 휴리스틱(승인 가능성 등급·무날조) + MASS1 검증형 매스 캐파(design_gen 비중복).

## 2. 배포 대상 (monorepo, 같은 브랜치)

- 엔진 서비스: services/deliberation-review (FastAPI, Postgres review 스키마, alembic).
- 플랫폼: apps/api — 심의/설계 SpecialistAgent 등록(기존 dispatch 엔드포인트로 자동 노출), config 2개 추가.

## 3. 사전 검증 (코드 — 현재 그린, 재현 명령)

WSL, 엔진 venv ~/My_Projects/propai-review/.venv/bin/python (=$PY):
```
cd <repo>/services/deliberation-review
$PY -m pytest -q                                                # 559 passed
$PY -m pytest tests/acceptance/test_no_hardcoded_params.py -q   # INV-3 통과
~/My_Projects/propai-review/.venv/bin/ruff check apps/api/app   # clean
cd apps/api && $PY -m alembic -c alembic.ini upgrade head        # 0016_permit_process까지(가역 확인됨)
```

## 4. 배포 절차 (★게이트됨 — 각 단계 사용자 승인·실값)

### 4.1 엔진 서비스
1. DB 마이그레이션 alembic upgrade head(0016_permit_process 포함). [실DB 대상 — 사용자 승인]
2. API_TOKEN 설정(베어러 인증). 미설정=개방(dev만). [시크릿 — 사용자 실값]
3. 기동 후 헬스 GET /health → ok.

### 4.2 플랫폼 ↔ 엔진 연동 (심의/설계 에이전트 가동)
1. 플랫폼 config: DELIBERATION_ENGINE_URL(엔진 베이스 URL), DELIBERATION_ENGINE_TOKEN(=엔진 API_TOKEN). [시크릿/URL — 사용자 실값]
   - 미설정 시 에이전트 graceful(available=False) — 장애 아님, 미연동 표면화.
2. 노출: POST /api/v1/agents/specialist/dispatch body {"domain":"심의"|"설계","data":{...}} → 엔진 permit/design 프로세스 호출, findings에 근거+링크 동반.

### 4.3 (선택) 라이브 법령/조례 소싱
1. LIVE_NETWORK=true + MOLEG_API_KEY(law.go.kr) → 규제 reconcile·라이브 법령. [시크릿 — 사용자 실값]
2. 자치법규(elis) 어댑터는 인터페이스 완비 — 키·운영 준비 시 점등(현재 graceful None).

## 5. 배포 후 검증 (스모크)

- 엔진 POST /api/v1/permit/process body {"pnu":"...","use_zone":"제2종일반주거지역","rules":[...],"calc_targets":[...]}
  → PermitProcessResult(stages·overall_conformance·overall_verification·overall_outcome). criteria에 calc_trace+legal_basis(source 링크) 확인.
- 엔진 POST /api/v1/design/process body에 "provided":{"massing":true,"proposed_gfa":2000} → massing 단계 capacity(max_gfa·conformance) 확인.
- 조회 GET /api/v1/projects/{id}/permit · /design(spec_id 분리·테넌트 격리).
- 플랫폼 dispatch(domain=심의/설계) → summary.overall_outcome·findings.basis/links 확인.

## 6. 미완(후속 — 게이트/타트랙/데이터팀)

- 결과예측 pluggable ML(휴리스틱→학습모델): 데이터·배포팀.
- 참조법규 정밀 조문화: law.go.kr 라이브 검증(키·승인).
- 생성형 설계(매스/세대수 본격): design_gen 트랙 소관(엔진은 MASS1 검증형으로 비중복).
- §84(둘 이상 용도지역 안분)·§36: 다필지 안분 로직 도입 시 인용 연결.
- design_gen 전용률 0.75 하드코딩(INV-11 의심): design_gen 트랙 개선.

## 7. 롤백

- 엔진 DB: alembic downgrade -1(0016→0015, 가역 검증됨).
- 플랫폼: config 2개 비우면 에이전트 graceful 미연동(코드 롤백 불필요).
