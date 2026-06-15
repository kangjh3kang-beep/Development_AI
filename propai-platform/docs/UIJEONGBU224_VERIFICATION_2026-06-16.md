# 의정부동 224 실무자 검증 보고 — 분석/공동경영 에이전트 시스템

작성: 2026-06-16 · 브랜치 `feature/trust-infra-2026-06-11` · 대상 입력: 경기 의정부시 의정부동 224(대표 PNU 4115010100102240000, 용도지역 시나리오 일반상업/제3종일반주거, 대지 660㎡)

> **방법·정직 표기:** 38-에이전트 워크플로가 12개 기능군별로 **DB·앱부팅 불필요한 결정론 함수를 실제 호출(WSL `.venv` python)** 해 실출력을 관찰하고, 라우터/DB 흐름은 정적 추적했다. critical/high 25건은 독립 에이전트가 file:line으로 적대 검증. **"실행한 것(executed)"과 "환경상 못 돌린 것(static/blocked)"을 명확히 구분**한다. 종합 단계 에이전트가 과보수적으로 작성을 거부해, 검증된 상류 결과를 오케스트레이터(메인)가 종합함.
>
> **환경 한계(그 자체가 결과):** 이 환경은 Docker 미연동(Postgres 없음) + 의존성 cascade 누락(`slowapi` 등) → **전체 앱(메뉴/라우터/인증/DB 흐름) 부팅 불가**. 결정론 분석 엔진 코어만 실구동. 이는 로드맵 P0-1/P0-2를 실증.

## 1. 한 줄 결론

**"코어는 최상에 근접, 전주기 운용은 아직 미달."** 시스템의 중심 설계 — *LLM 수치 비생성 + citation_gate + 데이터 없으면 skipped 정직 degrade* — 가 **실구동으로 작동함이 입증**됐다(할루시네이션 '날조'는 결정론 코어에서 확정 0건). 그러나 (a) 클린 환경 전체 부팅 불가, (b) 추정·합성·LLM 값을 그것으로 라벨하지 않는 **정직성 라벨 갭 6건**, (c) 공동경영 멀티에이전트 계층의 미성숙(coordinator 스텁·domain_agent 휴리스틱·orchestrator 종료신호 부재), (d) 운영 차단급 보안 critical — 때문에 "최상 운용"까지는 보완이 필요.

## 2. 기능별 구동 현황 (의정부동 224)

| 기능군 | live | 실무자 verdict | 핵심 |
|---|---|---|---|
| **설계심사 8엔진** | executed | **works** | 제3종 660㎡·FAR290 → 조건부적합(주차 24대·정북일조 51.3m), 한도초과→부적합+축소치. citation_gate 라이브 입증(미등록 법조문 차단·"[전문가 확인 필요]" 치환). 할루시네이션 PASS |
| **설계변경 예측** | executed | **works** | 3종 리스크 결정론·재현가능, 근거조문·물리모순(전용률>100%) 검출 |
| **비용/BOQ** | executed | **works** | 수지경로+적산(12단계 법정요율)+몬테카를로 P10/50/90. 단가DB 비어도 fallback 정직표기(price_source=fallback). 할루시네이션 PASS |
| 사업성/수지 | executed | partial | NPV/ROI/등급 결정론 실산출(상업>주거, F등급 타당). **갭: 금융·소프트비 자동추정 플래그(auto_estimated)가 출력에 소실→입력유래로 오표기** |
| 토지/입지 | partial | partial | 법정한도·실효용적률·입지점수 정직. **갭: 분양가가 데이터 0건이어도 의정부 1400만원/평 하드코딩을 confidence/skipped 없이 반환; /comprehensive LLM에 citation_gate 미배선** |
| 인허가/규제 | partial | works(부분) | 개발방식 허용/불가 매트릭스 법리 부합. **갭: VWorld 키 없으면 224를 제2종주거 기본값 추론(오판 위험); ai-analysis score는 LLM생성; regulation 실패시 is_compliant=True fail-open** |
| ESG/재해/환경 | executed | partial | LCA/EPD 표준식 정직(ef_source 단계표기). **갭: DisasterRisk가 경기/의정부 미수록→default 폴백(전 경기 동일점수)인데 미표기; ESG LLM 해석에 검증게이트 없음; EsgInterpreter 프롬프트가 입력에 없는 수치 요구** |
| 경매/AVM | executed | partial | 모듈러 경매·AVM은 모범(unavailable 정직 degrade·교차검증). **위반: flat `avm_service`가 CTGAN 합성 30건을 comparable_count에 섞고 confidence 0.30→0.42 상승시키며 synthetic 플래그 없음=mock을 live로(오케스트레이터 _step_avm 경로)** |
| 정직성·citation_gate(횡단) | executed | works-with-gaps | verifier 결정론 계층이 **날조 순이익을 라이브 적발(verdict=fail, Δ33%)**. **갭: check_against_legal이 국가상한(1300%)만 비교→의정부 조례 900% 초과(1000~1200%) 통과; verifier/calc_ledger가 design_audit 외엔 opt-in(use_verification_retry 기본 False)** |
| **공동경영 멀티에이전트** | partial | partial | ExpertPanel은 LLM실패시 generated=False 정직 degrade(합격). **미성숙: coordinator는 네트워크가 pass인 빈 스텁; DomainAgents는 입력무관 동일 0.89·영문전용 리스크트리거(한국어 '리스크' 미발동); orchestrator가 partial 상태를 종료이벤트로 미통지→손상데이터 위 투자등급** |
| 파이프라인/원장/협업 | partial | partial | 원장 해시 결정성·변조탐지 라이브 확인, range_rules가 무근거 400% high 적발. **갭: P2-10 comprehensive_report 실패 silent pass; 조례조회 실패 국가기준 silent fallback; /interpret LLM sections가 무결성 원장에 citation_gate 없이 append. 성장루프(read)는 Phase1 미구현(정직)** |

## 3. 할루시네이션 검증 결론

**결정론 코어의 수치 날조 = 확정 0건.** 방어선이 실제로 작동함을 라이브로 확인: ① 8엔진·cost·feasibility·verifier에 LLM import 0(grep), ② verifier가 날조 순이익 적발, ③ citation_gate가 미등록 법조문/근거없는 수치를 "[전문가 확인 필요]"+confidence=low로 강등, ④ 데이터 없으면 skipped/unavailable 정직 degrade(VWorld None·온비드 unavailable).

**그러나 "라벨 없는 비실측값" 6건이 할루시네이션-인접 리스크**(사용자가 추정/합성/LLM값을 실측으로 오인):
1. 🟠 **AVM 합성(CTGAN 30) 무표식 전파** + confidence 상승 — mock을 live로(불변규칙 위반). flat avm_service·오케스트레이터.
2. 🟠 **check_against_legal 조례상한 미집행** — 의정부 일반상업 900% 초과 주장 미적발(국가 1300%만 비교).
3. 🟡 **ESG interpreter 프롬프트가 입력에 없는 수치(tCO2 감축·비용·프리미엄) 요구** — 검증 미적용 경로서 날조 위험.
4. 🟡 **분양가 하드코딩(의정부 1400만/평)** confidence/skipped 없이 반환.
5. 🟡 **verifier/calc_ledger opt-in** — /interpret·report·avm narrative는 프롬프트 soft-guard만.
6. 🟡 **DomainAgents 휴리스틱**(고정 0.89)이 "analysis completed 89%"로 분석 가장.

## 4. 정직성(불변규칙) 종합

결정론 코어가 LLM 수치생성을 막는 구조는 **실효적**(LLM이 죽어도 verdict=fail 유지·수치는 결정론 필드 불변). `data_source(live|fallback|mock|unavailable)` 어휘는 일관되나 **커버리지 편중**(13개 파일만 표기, skipped는 9개 파일만 — 횡단 표준 아님). 진짜 `except: pass`(무처리) 0건이나 광범위 except→pass 49건(대부분 best-effort 주석/noqa). → **설계 철학은 견고, 표준화·게이트 배선의 일관성이 부족.**

## 5. 구동을 막는 실제 장벽

- **부팅:** `slowapi` 등 의존 cascade(P0-2 확장) + Postgres 부재(Docker 미연동) → 메뉴/라우터/인증/DB·LLM 흐름 live 불가. 실무자도 동일하게 막힘.
- **보안 critical(운영 전 필수):** P0-4(cost 무인증→무결성체인 오염), P0-5(rbac fail-open→전체 사용자 덤프), P0-3(CI가 apps/api 75% 미수집), P0-1(arq 미선언→worker 크래시).
- **회귀 안전망 부재:** CI 허위 green + **신규: `test_rbac.py:100-104`가 인증우회를 `assert True`로 정상 인증**(보안구멍을 green으로 박제).

## 6. 로드맵 재검증 델타 (HEAD e2f1773 기준)

- **P0-1·P0-3·P0-4·P0-5 = critical 유효(미수정) 재확인.** P1-1·P1-2·P1-5도 유효.
- **P0-2 정정(staleness):** prometheus-client는 oracle뿐 아니라 `pyproject.toml:72`에도 선언됨 → "oracle only" 서술 갱신 필요(3매니페스트 SSOT drift는 유효).
- **신규 발견(로드맵 미기재):** ① test_rbac가 P0-5 우회를 green 인증(메타-정직 결함, high). ② check_against_legal 조례상한 미집행(의정부 over-FAR 통과, high). ③ AVM 합성 무표식(mock-as-live, high). ④ DomainAgents 영문전용 리스크트리거(한국어 미발동, medium). ⑤ DisasterRisk 지역 default 폴백 미표기(medium). ⑥ feasibility auto_estimated 플래그 소실(medium).

## 7. '최상 운용'까지 권고 (우선순위)

1. **운영 차단 해제(보안·게이트):** P0-4/P0-5 인증·테넌트 가드 + test_rbac 교정 + P0-3 CI 양트리 수집 + P0-1/P0-2 의존 선언. (로드맵 PR-1·PR-3)
2. **정직성 라벨 표준화:** AVM synthetic 플래그·check_against_legal 조례상한 집행·분양가 confidence/skipped·feasibility estimate 플래그 전파 — "추정/합성/LLM"을 스키마에 박제. (할루시네이션-인접 6건)
3. **citation_gate 횡단 배선:** /interpret·report·avm·esg narrative에 verifier/calc_ledger를 기본 적용(opt-in→on).
4. **공동경영 계층 실구현:** coordinator 스텁→실조정 또는 제거, DomainAgents 휴리스틱→실분석·다국어, orchestrator 종료 요약 이벤트. (로드맵 PR-4 + Phase 3)
5. **전주기 실검증:** Docker Postgres + 의존 정합 후 apps/api 통합테스트로 본 보고의 static/blocked 항목을 live 재검증.
