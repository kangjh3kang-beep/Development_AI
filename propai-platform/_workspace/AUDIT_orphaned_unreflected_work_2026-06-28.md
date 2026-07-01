# 중단·미반영 작업 전수 발굴 리포트 (5축 스윕·2026-06-28)

Confirmed: `중앙분석센타` label points to `/${locale}` (home), and the asset-ops block (lines 119-128) is intentionally commented. The 5-axis findings are grounded. I have sufficient evidence to synthesize the report.

---

# PropAI "중단·미반영 작업" 전수 리포트 (읽기전용)

기준일 2026-06-28 · 브랜치 `feat-tmp` · 5축 발굴(고아라우트/미소비컴포넌트/dangling엔드포인트/미머지브랜치/nav불일치) 종합

---

## 1. 요약

| 축 | 원천 발견 | 중복제거 후 순(純) | 패턴 |
|----|---------:|-----------:|------|
| 고아 라우트 | 5 | 1 (실질) | 존재하나 nav/링크 미도달 — 대부분 **의도적 보류** |
| 미소비 컴포넌트 | 13 | 11 (실질) | 완성된 패널/카드/워크스페이스가 어디서도 import 안 됨 |
| Dangling 엔드포인트 | 79 | ~70 (모듈 12개) | 백엔드 구현 완료, 프론트 소비처 0 |
| 미머지 브랜치 | 6 | 6 | 작업 완료/진행분이 main 미반영 |
| nav불일치·플레이스홀더 | 8 | 2 (실질 이슈) | 라벨↔링크 불일치 + 의도적 placeholder(무목업) |

**핵심 패턴(중앙분석센터형):** "만들어졌으나 가려진 것"이 압도적이다. 코드 품질 문제가 아니라 **마지막 1cm(nav 등록·컴포넌트 import·프론트 fetch 1줄·브랜치 머지)가 빠진** 작업들이다. 이들은 구현 비용이 이미 지불됐으므로 **반영노력 S·사용자가치 高**의 즉효 ROI 후보다.

**중복 교차(같은 기능이 여러 축에 잡힌 것 → 1건으로 통합):**
- `UnitMixOptimizerPanel`(미소비 컴포넌트) ↔ feasibility/설계 엔드포인트군 → **유닛믹스 최적화 1건**
- `ConversationalMarketPanel`(미소비) ↔ `fix/market-insights-ssot-unification` 브랜치(시장 SSOT) → **시장분석 1건**
- 자산운영 4 라우트(고아) ↔ nav 주석블록(L119-128) ↔ `digital-twin/maintenance/tenant` 워크스페이스(미소비) → **자산운영 섹션 1건(의도적 보류)**
- G2B 13 엔드포인트(dangling) ↔ G2B 프론트 모달 → **G2B 콘솔 배선 1건**
- 매스템플릿 2 엔드포인트(dangling) ↔ `feat/mass-template-db` 브랜치 → **매스템플릿 1건**
- SpecialistAgent 폐루프 ↔ `feat/memory-hub-loop` + `fix/land-tools-multiparcel-responsive` 브랜치 → **성장뇌/Specialist 배선 1건**

---

## 2. 우선순위 표 (심각도·가치 × 반영노력)

★ = 중앙분석센터형 즉효 ROI(이미 구현됨, 붙이기만)

| # | 통합항목 | 근거(파일/라우트/브랜치) | 가치 | 노력 | 우선 |
|--:|---------|------------------------|:----:|:----:|:----:|
| 1 ★ | **nav 라벨↔링크 불일치 — "중앙분석센타"→홈** | `nav-config.tsx:45` (`href:/${locale}`) | 高 | S | **P0** |
| 2 ★ | **`fix/market-insights-ssot-unification` 머지**(좌표누수·단일필지고착·PDF 버그수정) | 브랜치 5커밋(b0ac0d52…90838ded) | 高 | S | **P0** |
| 3 ★ | **유닛믹스 최적화 배선** | `UnitMixOptimizerPanel`(import 0) + feasibility 엔드포인트 | 高 | S | **P0** |
| 4 ★ | **C2R 좌표렌더 프론트 소비** | `/c2r/brief`,`/c2r/render`(호출 0) | 高 | S | P1 |
| 5 ★ | **설계심사(Design Audit) 배선** | `/design-audit/run`,`/{id}/pdf`(호출 0) | 高 | S | P1 |
| 6 | **G2B 콘솔 프론트 배선** | `/g2b/*` 13개(호출 0) | 高 | M | P1 |
| 7 | **공사비/BOQ 모듈 배선** | `/cost/*` 14 + `/boq-auto/*` 6(호출 0) | 高 | M~L | P1 |
| 8 | **성장뇌·SpecialistAgent 폐루프 머지** | `feat/memory-hub-loop`+`fix/land-tools-multiparcel-responsive` | 高 | M | P1 |
| 9 | **분석원장(Ledger) 배선** | `/analysis-ledger/*` 7개(호출 0) | 中 | M | P2 |
| 10 | **시장분석 AI 입구 컴포넌트** | `ConversationalMarketPanel`(import 0) | 中 | S | P2 |
| 11 | **ESG/탄소·안전 워크스페이스 배선** | `CarbonEmissionsWorkspaceClient`,`SafetyWorkspaceClient`(import 0) | 中 | M | P2 |
| 12 | **매스템플릿 머지+배선** | `feat/mass-template-db` + `/mass-templates/*` 2개 | 中 | M | P2 |
| 13 | **Gemini 멀티프로바이더 머지** | `fix/multiparcel-ordinance-legallink` | 中 | S | P2 |
| 14 | **WorkspaceShell 표준화(리팩토링 기회)** | import 0, 다른 클라이언트가 직접 구현 | 中 | L | P3 |
| 15 ⚠ | **자산운영 섹션(준공후 운영)** | nav `L119-128` 주석 + 4라우트 + 3워크스페이스 | 低 | S | **보류(의도적)** |
| 16 ⚠ | **레거시 폐기 잔존물** | `PermitsWorkspaceClient`,`ApprovalsWorkspaceClient`(주석상 "제거" 명시) | — | S | **삭제 대상** |
| 17 ⚠ | **Mock 의존 전시 컴포넌트** | `EscrowCard`,`JeonseRiskCard`(mocks/module-data) | 低 | — | 무목업 위배 — 보류/제거 |
| 18 | **docs 인계 문서** | `docs/image-gen-inc2-4-plan` | 低 | S | 통합자 참고용 |

---

## 3. 권고 액션 — Top 5 (무엇을·어디에·어떻게 + 게이트)

> 공통 게이트(CLAUDE.md 정책): ①라이브검증(실데이터) ②완결게이트(린트·빌드) ③기록·공유(커밋+`_workspace`) ④**전역 전파방지 스윕**(같은 패턴이 다른 페이지에도 있는지) ⑤무목업.

**1. nav 라벨 정합 — `nav-config.tsx:45`**
- 무엇: "중앙분석센타" 항목의 `href`가 홈(`/${locale}`)을 가리켜 라벨↔대상 기대값 불일치(SiteCanvas 케이스 재현).
- 어떻게: 홈 대시보드가 실제 중앙분석 역할이면 **라벨을 "홈/대시보드"로 정정**하거나, SiteCanvas(`/projects/[id]/canvas`)가 진짜 센터면 **링크를 그쪽으로 교정**.
- 게이트: 어느 쪽이 의도된 SSOT인지 **반영 전 확인필요**(추측). 결정 후 전역 nav 라벨 스윕.

**2. `fix/market-insights-ssot-unification` 머지 (P0 버그수정)**
- 무엇: 좌표누수·단일필지 고착·PDF 부실을 **공용가드로 SSOT 일원화**한 프로덕션 버그수정 5커밋. CLAUDE.md "전파방지② 공용화" 정책과 정확히 일치.
- 어떻게: `feat-tmp`/`main` 대비 충돌 확인 후 머지 → 시장·시세 분석 라이브검증(다필지 통합면적·우세용도 기준 뱃지 노출 확인).
- 게이트: 다른 분석폼(규제·인허가·법규)에도 단일필지 고착 잔존 여부 스윕(브랜치가 이미 일부 처리 — 98c7fa6c).

**3. 유닛믹스 최적화 배선 (이미 구현·붙이기만)**
- 무엇: `UnitMixOptimizerPanel`(완성 컴포넌트, import 0) + 백엔드 최적화 엔드포인트.
- 어디에: 타당성/설계 모듈 페이지(`/projects/[id]/feasibility` 또는 `/design`)의 placeholder 자리.
- 어떻게: 페이지에서 컴포넌트 import + 엔드포인트 `fetch` 1줄 배선. 과금게이트 적용(선택형 분석 기본).
- 게이트: GFA·주차 제약 입력→결과 라이브검증, 근거계약(value/basis/source) 노출.

**4. C2R + 설계심사 프론트 소비 (시각화·심사 완결)**
- 무엇: `/c2r/brief`·`/c2r/render`(렌더), `/design-audit/run`·`/{id}/pdf`(심사) — 백엔드 라이브(메모리상 PR#82 C2R 라이브)인데 프론트 소비처 0.
- 어디에: 설계 스튜디오/설계 모듈 결과 패널.
- 어떻게: 렌더 버튼→`/c2r/render` 호출(키 없으면 `provider_unconfigured` 정직강등 유지), 심사 PDF 다운로드 배선.
- 게이트: provider 미설정 시 정직 표기(무목업), 렌더 결과 라이브 확인.

**5. 성장뇌·SpecialistAgent 폐루프 머지 (`feat/memory-hub-loop` + `fix/land-tools-multiparcel-responsive`)**
- 무엇: SpecialistAgent 회상/저장 폐루프 + 7도메인(far·cost·market·심의·설계) 배선 완결. MEMORY.md "성장루프 prod 미가동·소비처0"의 직접 해소.
- 어떻게: 두 브랜치 순차 머지(land-tools가 memory-hub 기반 위 배선) → 실데이터 회상/저장 폐루프 라이브검증.
- 게이트: interpreter=None·핸드오프 손실 회귀 없는지(메모리상 9경로) 확인, comprehensive 부지분석에서 도메인 출력 표면화 검증.

---

## 4. 주의 — 반영 전 확인필요 / 추측 명시

- **의도적 보류(반영 금지 후보):** 자산운영 4라우트+nav 주석블록(`nav-config.tsx:119-128`)+`digital-twin/maintenance/tenant` 워크스페이스는 "준공 후 운영 단계, 코어 개발→분양과 단절"로 **명시적 주석에 의해 숨김**. 복원은 운영 단계 진입 시 주석 해제만으로 가능. **현 시점 반영은 비권장.**
- **삭제 대상(추가 아님):** `PermitsWorkspaceClient`·`ApprovalsWorkspaceClient`는 페이지 주석상 "중복·로그인게이트 오류로 제거"라 명시됐으나 파일 잔존 → **배선이 아니라 정리(삭제) 대상.** 되살리면 안 됨.
- **무목업 위배 가능:** `EscrowCard`·`JeonseRiskCard`는 `mocks/module-data` 의존 전시용 → CLAUDE.md 무목업 원칙상 **실API 연결 전 배선 금지**. 블록체인/금융 모듈 활성화 결정이 선행돼야 함.
- **`/guide`(고아로 분류됨):** 실제로는 대시보드 홈 버튼·배너로 도달 가능 → **실질 문제 아님**(거짓 양성). nav 등록은 선택사항.
- **추측 표시:** dangling 엔드포인트 "79개"는 정적 grep 기반 — 동적 URL 조립·SSE·웹훅 소비처를 놓쳤을 수 있어 **배선 착수 전 개별 재확인 권장**. 가치도(高/中/低)도 발굴 에이전트의 추정이며 제품 우선순위와 다를 수 있음.
- **제외 확인:** admin(`/admin/*`)·헬스체크·메트릭·내부 웹훅은 정상적으로 dangling 집계에서 제외됨(거짓 양성 회피 양호).

---

## 5. 근거 파일/라우트/브랜치 (검증된 앵커)

- `propai-platform/apps/web/components/layout/nav-config.tsx:45` — "중앙분석센타"→`/${locale}` 라벨↔링크 불일치
- `propai-platform/apps/web/components/layout/nav-config.tsx:119-128` — 자산운영 섹션 의도적 주석(assetOpsOnly 보존)
- 브랜치 `fix/market-insights-ssot-unification` — 미머지 5커밋(시장 SSOT 버그수정), 최신 2026-06-28
- 브랜치 `feat/memory-hub-loop`(48127c56) + `fix/land-tools-multiparcel-responsive`(6911234c·87c40dc0·54c4aa7e) — SpecialistAgent 폐루프/7도메인 배선
- 브랜치 `feat/mass-template-db`(e5d097b4) / `fix/multiparcel-ordinance-legallink`(27bdddca, Gemini) / `docs/image-gen-inc2-4-plan`(a9eba1e2)
- 미소비 컴포넌트 13종(import 0): `UnitMixOptimizerPanel`·`ConversationalMarketPanel`·`CarbonEmissionsWorkspaceClient`·`SafetyWorkspaceClient`·`ParkingLogView`·`GenerativePanel`·`WorkspaceShell` 등
- Dangling 모듈 12군: `/cost/*`(14)·`/boq-auto/*`(6)·`/g2b/*`(13)·`/analysis-ledger/*`(7)·`/deliberation/*`(6)·`/c2r/*`(2)·`/design-audit/*`(2) 등

**최상단 즉효 ROI 결론:** P0 3건(nav 라벨 정합 / 시장 SSOT 브랜치 머지 / 유닛믹스 배선)은 모두 **이미 구현된 자산을 노출/머지/import만** 하면 되는 중앙분석센터형. 가치 高·노력 S로 가장 먼저 처리할 것을 권고한다.