# 신뢰 기반 인프라 구현 로드맵 (통합 실행계획)

> 종합 출처: PRECHECK_UPGRADE_BLUEPRINT(90초 진단), PLATFORM_INFRA_SYNERGY(4레이어 횡단 인프라), 규제연동 요구.
> **파일럿 순서(사용자 지정)**: ①입지분석(메인=프로젝트 생성→site-analysis) → ②파이프라인 site 단계 → ③소비자(90초 진단·규제연동) → ④확산.
> 원칙: **새 엔진 0 · 기존 자산 재사용 · additive**(기존 응답/store/계약 1개도 제거·변경 금지).

## 왜 입지분석이 첫 적용처인가
입지분석(`siteAnalysis`: 주소·PNU·용도지역·면적·공시지가)이 모세혈관의 **상류 원천**이다. 여기에 신뢰 레이어(출처·근거·법령링크)가 붙으면 설계→공사비→수지→ESG 하류가 자동 상속한다. 90초 진단·규제연동은 이 데이터의 **소비자**이므로 원천을 먼저 고친다.

## 웨이브

### W0 — 공통 기반 (응답 변화 0, 준비만)
- **WP-A** `legal_reference_registry.py` 신규 — {근거키 → 법령명·조문·title·law.go.kr URL}. PRECHECK 블루프린트 ②-3 검증표가 마스터. 데이터 매핑만(계산 0).
- **WP-B** `legal_zone_limits.py`에 `LEGAL_REF_KEYS`/`legal_ref_keys` 가산(기존 LEGAL_BASIS 유지).
- **WP-C** 프론트 공통 컴포넌트: `LegalRefChip.tsx`(법령 원문링크 칩, target=_blank rel=noopener), `EvidencePanel.tsx`(법령·계산·출처 수렴 근거 패널). FieldSourceBadge는 기존 재사용.

### W1 — 파일럿: 입지분석 (메인 진입점)
- **WP-D** 백엔드 `/zoning/comprehensive`(auto_zoning 라우터 + comprehensive_analysis_service): 응답에 `legal_refs[]`(zone 한도·조례 근거 law.go.kr 링크) + `inputs`(필드별 provenance: zone/area/공시지가/PNU 출처·신뢰도) + `evidence[]`(수치 산출 트레이스) 가산. 조례 실효값(applicable_limits_for) 적용 + 출처 정직표기.
- **WP-E** 프론트 `ProjectSiteAnalysisWorkspaceClient` + `AutoZoningBadge`: 미표시 `legal_basis`를 LegalRefChip로, 필드 출처 배지, EvidencePanel 렌더. 신뢰 메타데이터를 SSOT(updateSiteAnalysis)에 포함 저장.

### W2 — 입지분석 2순위 진입점: 파이프라인 site 단계
- **WP-F** `project_pipeline._run_site`: 동일 legal_refs/provenance 메타데이터 부착(레지스트리 재사용이라 소량). E7 가정값 표기는 기존 유지.

### W3 — 소비자
- **WP-G** 90초 진단(precheck): PRECHECK 블루프린트 WP-3~9 — inputs·data_quality·feasibility_band(최저/기본/최대)·evidence·legal_refs. PreCheckWorkspace를 SSOT 연결.
- **WP-H** 규제연동: ProjectPicker(프로젝트 선택 자동입력) + 계층 트리 각 노드 LegalRefChip + SiteResolver 경유 + 라이트백(ordinance writer).

### W4 — 검증·빌드
- 백엔드 테스트(레지스트리·zoning·precheck 골든), 프론트 tsc+vitest+build, law.go.kr 링크 유효성 체크, 커밋.

## 법령 링크 안전 규칙 (필수)
- URL은 PRECHECK 블루프린트 ②에서 **실접속 검증된 law.go.kr 한글주소 형식만** 사용(`/법령/{명}/제{N}조`, `/자치법규/{조례명}`).
- 조(條) 단위까지만(항·호 미지원). 미검증 조문은 법령 루트 링크로 폴백(틀린 딥링크 금지).
- 레지스트리에 없는 근거는 링크 없이 텍스트만(할루시네이션 링크 절대 금지).
