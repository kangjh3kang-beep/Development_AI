# 부지분석 품질 강화 작업 로그

## 작업 개요
- **일시**: 2026-05-30
- **목표**: 부지분석 결과의 데이터 정확도, 분석 해석, AI 설명 3단계 품질 강화
- **상태**: 진행 중

## 진행 경과

### Phase 0: 컨텍스트 확인 (완료)
- 기존 `_workspace/` 존재 확인
- 새 작업으로 판단 → Phase 1 진행

### Phase 1: 현황 분석 (완료)

#### 발견된 문제점
| # | 문제 | 근본 원인 | 심각도 |
|---|------|----------|--------|
| 1 | 조례 용적률 250% (법정상한 동일) | ORDINANCE_CACHE 부정확 | HIGH |
| 2 | 건축물대장 연면적/층수 0 | API 응답 파싱 불완전 | HIGH |
| 3 | 주변 인프라 "데이터 없음" | VWORLD POI 검색 실패 (404) | HIGH |
| 4 | 공시지가 시세 추정 단순 | 1.2배 고정 보정 | MEDIUM |
| 5 | 분석 주석 기술적/형식적 | 규칙 기반 해석 로직 부재 | HIGH |
| 6 | AI 해석 없음 | LLM 연동 미구현 | HIGH |

### Phase 2: 작업 분배 (완료)

#### 에이전트 배정
| 에이전트 | 담당 영역 | 대상 파일 |
|---------|----------|---------|
| backend-dev | 데이터 정확도 + 분석 해석 | ordinance_service.py, land_info_service.py, comprehensive_analysis_service.py |
| ai-ml-dev | LLM 종합 해석 생성 | 신규: site_analysis_interpreter.py |
| frontend-dev | 보고서 UI 강화 | ComprehensiveAnalysisPanel.tsx |

### Phase 3: 병렬 구현 (진행 중)

#### 백엔드 작업 상세
1. **조례 캐시 검증/업데이트**: 의정부시 등 주요 시 데이터 정확성 확인
2. **건축물대장 파싱 보강**: API 응답 필드 매핑 수정
3. **인프라 POI 폴백**: VWORLD 검색 실패 시 대안 로직
4. **공시지가 보정계수**: 지역별 차등 적용 (서울 1.5배, 경기 1.2배 등)
5. **분석 주석 개선**: 자연어 설명 + 법적 근거

#### AI/ML 작업 상세
1. **SiteAnalysisInterpreter 서비스**: Claude API 연동
2. **프롬프트 설계**: 부동산 전문가 페르소나
3. **7개 섹션별 해석**: 시사점 + 리스크 + 기회 요인
4. **폴백 처리**: API 실패 시 기존 결과 유지

#### 프론트엔드 작업 상세
1. **AI 종합 요약 카드**: 리스크/기회 요인 분리 표시
2. **섹션별 AI 해석 영역**: 데이터 아래 해석 텍스트
3. **annotations 컬러 배지**: 태그별 색상 구분
4. **로딩 상태**: AI 분석 중 인디케이터

### Phase 4: 통합 검증 (대기)
- 에이전트 작업 완료 후 교차 검증 수행 예정

### Phase 5: 배포 (대기)
- 커밋 + push + Oracle VM 업데이트

## 변경 파일 목록 (예정)
- `apps/api/app/services/land_intelligence/ordinance_service.py` — 조례 캐시 정확성
- `apps/api/app/services/land_intelligence/land_info_service.py` — 건축물대장 + 인프라
- `apps/api/app/services/land_intelligence/comprehensive_analysis_service.py` — 분석 주석 강화
- `apps/api/app/services/ai/site_analysis_interpreter.py` — 신규: LLM 해석
- `apps/web/components/analysis/ComprehensiveAnalysisPanel.tsx` — UI 강화
