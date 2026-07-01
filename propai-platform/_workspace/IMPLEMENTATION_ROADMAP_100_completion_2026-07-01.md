# 사통팔땅 100% 완성 — 상세 구현 로드맵 (실행 순서·스펙·검증)

- 작성일: 2026-07-01
- 상위: `REDTEAM_PASS4_GROUNDTRUTH_VERIFIED_PLAN`(검증·보정), `EXPANSION_PLAN_forest_terrain`(산지/임목), 코덱스 3문서
- 목적: 검증으로 확정된 실결함 R-1~R-10 + 확장 E1~E5를 **의존성·순서·파일·수정스펙·검증·완료판정**까지 전개한 실행계획. 각 단계는 성장루프(executor→code-reviewer≥9.5→통합자머지→블루그린배포→라이브검증) 1회.
- 원칙: 한 번에 하나 모듈 완벽 / 국소패치 금지·공용화·전역스윕 / 무목업·정직표기 / 재구현 금지(기존자산 확장) / 근거+링크.

## 0. 완료판정(선언 가능한 100%) — 재정의 채택

코덱스 계획의 "외부API fetch 100%"(달성불가 바)를 폐기하고 **"사용자가 false 적합/확정을 볼 수 있는 경로 0건 + 미확보는 정직 차단·표기 + 산출물 provenance 완비"** 로 정의(4G-3/4G-8). 측정가능·무목업 원칙 정합.

**절대차단 조건(보정):** ①**라이브** fail-open 1건 이상 ②핵심 도메인 백엔드 테스트 실패 or 수집 실코드오류>0 ③확정 산출물 evidence 없음 ④production 판정경로 mock/fallback ⑤statutory_only를 "확정 조례"로 표기 ⑥cross-tenant 데이터 누출.

## 1. 워크스트림 & 의존성 그래프

```
[WS-A 무결성 코어]  R-1(라이브 fail-open) ─done? PR#131
                     ├ R-2(verify-backend.sh·py3.12 게이트) ──┐ (독립·기반)
                     ├ R-4(고아 fail-open 하드닝) ─────────────┤
                     └ R-3(CAD커널 ZONE_LIMITS SSOT 정합) ─────┤
[WS-B 격리·정직]     R-7(조례 전역캐시 테넌트격리) ───────────┤
                     R-8(정직상태 i18n/a11y) ──────────────────┤
                     R-5(마지막필지 stale) / R-6(면적 needs_enrichment)
[WS-C 계약 확장]     R-9(면책·의존자 audit = evidence 확장) ── R-10(시행일 각인)
[WS-D 특수조건]      E1(special_parcel 정량+차단상태) → E3(산림청 커넥터) → E2/E4/E5
```
- WS-A/B는 서로 독립(다른 파일) → 순차이되 병렬 가능. WS-C는 evidence_contract 확장(선행 없음). WS-D는 E1→E3 의존.
- **권장 순서**: R-1(진행) → R-2 → R-3 → R-7 → R-8 → R-4 → R-5/R-6 → R-9 → R-10 → E1 → E3 → E2/E4/E5.
- 근거: 기반(R-2) 먼저, 그다음 안전측 소규모(R-3), 격리 P1(R-7), 사용자가시 정직(R-8), 하드닝(R-4), 프론트 경미(R-5/6), 계약확장(R-9/10), 마지막 대형 특수조건(E*).

---

## 2. 단계별 상세 스펙

### R-1 · /legal-check fail-open (진행중 — PR #131)
상태: 구현·리뷰9.6·PR생성 완료, CI 대기→머지→배포→라이브검증 남음. 세부 생략(별도 추적).

### R-2 · 검증환경 게이트 `scripts/verify-backend.sh` (P1·기반)
- **문제**: 코드 `requires-python>=3.12`인데 감사가 3.10으로 돌려 "검증환경 실패" 오진. 재발 방지 게이트 부재.
- **파일**: `scripts/verify-backend.sh`(신규), `apps/api/requirements.txt`(참조), CI 워크플로(선택).
- **스펙**: ①`python3.12` 강제(미만이면 `datetime.UTC`/`StrEnum` ImportError 안내 후 non-zero) ②venv+requirements 설치 ③핵심 도메인 테스트(`-k "legal or zone or ordinance or special_parcel or precheck or evidence or compliance"`) ④`--collect-only` 수집 실코드오류 0 검증(의존성 누락과 코드오류 구분). ⑤결과 요약 출력.
- **검증**: 스크립트 실행 → 핵심 도메인 그린 + 수집오류0. CI에서도 동일.
- **완료판정**: 3.11 이하로 돌리면 즉시 실패 안내, 3.12+deps면 통과. 감사 재발 불가.
- **규모**: 소(반나절). 코드리뷰 경량.

### R-3 · CAD커널 ZONE_LIMITS SSOT 정합 (P2·안전측)
- **문제**: `auto_design_engine.ZONE_LIMITS`(2R far=200%·GC 1000%)가 SSOT(250%·1300%)와 드리프트. 보수방향(과소)이라 안전측이나 사용자에 다른 숫자 노출.
- **파일**: `apps/api/app/services/cad/auto_design_engine.py:47-52`, 소비 `design_spec.py`, `drawing.py:388-398`(재클램프).
- **스펙**: `auto_design_engine.ZONE_LIMITS`를 SSOT `legal_limits_for()`에서 도출하도록 배선(하드코딩 표 제거 또는 SSOT값으로 동기화). 단 CAD는 높이/전면후퇴 등 추가필드 필요 → SSOT 한도(bcr/far)만 SSOT에서 가져오고 CAD전용 파라미터는 유지. `drawing.py`의 "엔진 vs SSOT 상이" 주석·재클램프 정리.
- **검증**: `test_zone_limits_engine_sync` 확장 — CAD엔진 far/bcr == SSOT far/bcr(전 zone). 2R=250·GC=1300 일치.
- **완료판정**: 동일 zone의 bcr/far가 모든 엔진에서 동일 provenance. drift 검사 CI화.
- **규모**: 소. ★회귀주의: CAD 매스 산출층수 변동 가능 → 설계스튜디오 라이브검증 필수.

### R-7 · 조례 전역캐시 테넌트 격리 + statutory 비영속 (P1·격리)
- **문제**: `ordinance_service._save_resolution`가 `ON CONFLICT (sigungu, zone_type)` 전역키·테넌트 스코프 없음·TTL 없음. statutory 폴백(confidence 0.60)도 저장 → 실 조례가 법정상한보다 낮을 때 전 테넌트에 법정상한 서빙(계정격리 위반).
- **파일**: `apps/api/app/services/land_intelligence/ordinance_service.py:82-119, 355-363`, 소비 `far_tier_service.py`·`precheck_service.py`.
- **스펙**: ①**statutory 폴백은 `_save_resolution` 호출 제거**(3차 폴백 경로) — 전역캐시에 미확정값 저장 금지. ②성공 fetch(법제처/정적캐시)만 저장. ③소비 시 provenance.source가 statutory면 항상 재조회(캐시 미신뢰). ④(장기) 조례 캐시는 전역이되 "확정 여부"를 프로젝트 verdict 스냅샷에 복사 — 전역캐시를 판정 SSOT로 쓰지 않음. 이번 단계는 ①~③.
- **검증**: 신규 테스트 — statutory 폴백 후 `_load_stored` 재조회 시 statutory 미재사용(재fetch 시도), 성공 fetch만 저장. cross-tenant 시나리오(A 실패→B 조회) 격리 확인.
- **완료판정**: 미확정(statutory) 조례가 다른 프로젝트/테넌트에 재사용되지 않음. min-클램프는 유지(법정최대 초과 여전히 불가).
- **규모**: 중. ★소비처(far_tier·precheck) 회귀검증.

### R-8 · 정직 실패상태 i18n/a11y (P1·정직성)
- **문제**: needs_verification/BLOCKED 등 상태문자열이 하드코딩 한국어(useTranslation 미사용) → en/zh 사용자는 차단사유를 못 읽어 정직성이 언어장벽에서 붕괴. 차단배너 `role="alert"` 부재.
- **파일**: `apps/web/components/precheck/*`, `design/DesignWorkspace.tsx`, `ProjectLegalWorkspaceClient.tsx`(R-1에서 verifyLabel 일부 도입) 등 판정상태 렌더 컴포넌트.
- **스펙**: ①상태 라벨을 enum→i18n 키 표준화(`status.needs_verification`·`status.blocked`·`status.needs_official_survey`) 3로케일(ko/en/zh-CN) 딕셔너리 등록. ②차단 배너에 `role="alert"`/`aria-live="assertive"`. ③공용 `<VerdictStatusBadge status=.../>` 컴포넌트로 추출(전역스윕·재사용).
- **검증**: 3로케일 렌더 스냅샷, 하드코딩 상태문자열 0(lint 규칙 or grep 게이트).
- **완료판정**: 모든 판정 상태문자열 i18n 키 경유, 스크린리더 announce.
- **규모**: 중. 공용 컴포넌트화로 전역 적용.

### R-4 · 고아 fail-open 엔드포인트 하드닝 (P2·하드닝)
- **문제**: `/regulation/check`·`/agents/orchestrate`(RegulationService)는 프론트 소비 0이나 등록된 채 fail-open(is_compliant=True) 잔존. R-1에서 폴백 2지점은 이미 fail-closed화. 남은 것은 이 엔드포인트를 fail-closed 계약으로 완전 전환 or 제거.
- **파일**: `apps/api/services/regulation_service.py`, `apps/api/routers/regulation.py`, `apps/api/agents/propai_orchestrator.py`.
- **스펙**: RegulationService의 응답을 ComplianceStatus(UNKNOWN/NEEDS_VERIFICATION) 도입 or `/regulation/check` deprecate(주 경로 `/regulation/analyze`가 이미 fail-closed SSOT). 직접 API호출·추후 재배선 시 재발 방지.
- **검증**: Qdrant장애+LLM장애 시 PASS 미반환 테스트.
- **완료판정**: `rg "is_compliant.*True"` 판정경로 0. 규모: 소~중.

### R-5 · 마지막 필지 제거 시 컨텍스트 clear (P2·경미)
- **파일**: `apps/web/components/precheck/SatongMapShell.tsx:452-470`.
- **스펙**: `removeParcel`이 `next.length===0`일 때도 `commitParcelsToContext([])`로 store clear(현재 length>0만). `clearParcels`도 컨텍스트 clear 확인.
- **검증**: 마지막 필지 제거 후 siteAnalysis.parcels/address/pnu 비워짐 테스트. 규모: 소.

### R-6 · 면적 미보강 필지 needs_enrichment (P2)
- **파일**: `apps/web/components/precheck/satong-map-selection.ts`(areaSqm>0 필터).
- **스펙**: 면적 없는 필지를 제외 대신 `status="needs_enrichment"`로 전달, 백엔드가 PNU/주소로 면적 재보강·실패 시 명시오류. 규모: 중(백+프론트).

### R-9 · 면책·의존자 audit 계약 (evidence 확장) (P2·계약)
- **문제**: 법령 판정응답에 "법률자문 아님" 경계·의존자 audit 부재(면책은 818건 산발·비일관).
- **파일**: `apps/api/app/services/data_validation/evidence_contract.py`, `apps/api/app/schemas/evidence.py`(BaseEvidenceResponse), 판정 라우터들.
- **스펙(★재구현 금지 — 확장)**: evidence 계약에 `legal_boundary`("advisory"/"not_legal_advice")·`reliance_audit`(tenant/project/user + 열람·다운로드 시각) additive 필드. 판정 PASS/FAIL 응답이 `BaseEvidenceResponse` 상속하도록. 자유문자열 면책은 registry 단일문구화.
- **검증**: 판정응답에 legal_boundary 존재 계약테스트. 규모: 중.

### R-10 · verdict 시행일 각인 (P2·시점)
- **파일**: evidence 계약(위 확장), `legal_hub`/`gosi_search_service`.
- **스펙**: verdict evidence에 `law_effective_date`(적용 법령 시행일)+`analysis_as_of`(분석 기준일). `regulation_monitor` 공포일 변경이 verdict의 law_effective_date보다 나중이면 해당 verdict만 선택적 stale.
- **검증**: verdict 재현 시 동일 law_version이면 동일 결과. 규모: 중.

---

## 3. 확장 워크스트림 WS-D (특수조건 — `EXPANSION_PLAN_forest_terrain` 상세)
- **E1**: `special_parcel` 임야 게이트에 `forest_facts` 정량필드 + `NEEDS_OFFICIAL_SURVEY` 차단상태(신규 아님·확장). ★최우선(커넥터 없이 참고vs확정 분리·차단 확보).
- **E3**: 산림청 커넥터 `forest_data_service.py`(★유일 신규) — 산지구분도·임상도·산림기본통계. ConnectorReadiness 라벨(열람전용=manual_only). special_parcel 게이트 경유.
- **E2**: `terrain_service` 공식 DEM 분기(SRTM=derived_estimate 명시).
- **E4**: 입목축적 예비산정 + 산지전용 게이트. **E5**: 산지/임야 전용 UI 패널 + 전문가 연결 CTA.
- 순서: E1 → E3(원천 readiness 조사 선행) → E2/E4/E5.

---

## 4. 각 단계 공통 성장루프 체크리스트
1. 전용 브랜치(`fix/<item>` 또는 `feat/<item>`) off origin/main.
2. executor 구현(무목업·쉬운 한국어 주석·기존자산 확장).
3. py3.12 venv로 테스트 그린 + 회귀락 추가.
4. code-reviewer ≥9.5(별도 레인·self-approval 금지). REAL 결함 0.
5. 통합자 머지(PR) → CI green.
6. 프론트 변경 시 sw.js bump.
7. 백엔드 블루그린 배포(health 게이트) + 프론트 배포.
8. 라이브검증(실 엔드포인트·번들 코드 실재).
9. 기록(커밋+메모리+_workspace) + 전역스윕(동일패턴 타 경로).

## 5. 리스크·주의
- ★R-3(CAD)·R-7(조례)은 소비처 회귀 위험 → 라이브검증 필수.
- 멀티세션: 각 단계 전용 워크트리·main 단일배포(발산방지).
- 서브에이전트 한도: 대형 단계는 리뷰를 직접 수행 폴백.
- 배포충돌: 코덱스 등 타세션과 main 단일브랜치 배포 합의 유지.

## 6. 진행 추적표
| 단계 | 상태 | PR | 비고 |
|---|---|---|---|
| R-1 | 구현·리뷰9.6·PR#131 | #131 | CI대기→머지→배포→검증 |
| R-2 | 대기 | - | 기반·소 |
| R-3 | 대기 | - | 안전측·CAD회귀주의 |
| R-7 | 대기 | - | 격리 P1 |
| R-8 | 대기 | - | i18n 공용컴포넌트 |
| R-4/5/6/9/10 | 대기 | - | 순차 |
| E1~E5 | 대기 | - | 특수조건 |
