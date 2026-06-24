# SiteCanvas(지도 단일창) 갭 재분석 + 보완·개선방안

> 2026-06-24. 라우트 /projects/[id]/canvas. 현 7탭(토지/규제/개발방식/일조·배치/수지/통합/구획도)
> + 자급식 지도(구획도↔실거래) + 필지선택 + 구획도 다운로드. v315 라이브·v316 배포중.
> 참조: jootek(map.jootek.com) 맥락형 탭 + 추천 건축모델 + 건축비용 CTA.

## 도출된 문제점

### A. ★LLM 미적용 (최우선 갭)
- 7탭 전부 규칙기반 KPI, AI 해석/통합 인사이트 0.
- 10개+ 인터프리터(site_analysis·cost·feasibility·market·permit·esg·design·avm·digital_twin·deliberation)
  실재하나 캔버스 미연결.
- '통합' 탭 = 정적 SSOT rollup, LLM 통합 해석 아님.

### B. 각 기능 미연결
- 규제법령집(district_legal_refs 14조문, P1 신규) → 규제 탭 미노출.
- 특이부지 개발가능 방안(신규) → 개발방식 탭 존재하나 비강조.
- 입지점수/POI(SiteInfraPoiCard)·환경/지형(Terrain/Environment)·ESG(GresbScoreCard)·시장(market) → 탭 없음.
- 추천 건축모델/설계(jootek式 design 추천) → 미연결. design_interpreter·auto-design 미surface.
- 건축 예상 비용(cost estimate) → 수지 탭이 feasibilityData만 읽고 cost 추정 미트리거.
- 실거래 마커지도 = 시각만 미환류. 본맵 직접 클릭선택 = 임베드 picker(P1 훅 미추출).

### C. 검증·근거·심의 미연결
- VerificationBadge(검증)·근거/신뢰도(evidence/trust)·심의엔진(DeliberationResultPanel) 미노출.

### D. UX/데이터
- 탭이 FULL 카드 재사용(무거움), 컴팩트 요약 아님(디자이너 의도 미달).
- 분석 미실행 시 카드 빈상태(캔버스發 자동 트리거 부재).
- 통합 탭 rollup 빈약.

## 보완·개선방안 (우선순위 로드맵)

### I1 ★LLM 통합 해석 탭 (최우선·핵심)
- '통합' 탭에 site_analysis_interpreter / comprehensive AI 해석을 surface — 부지 요약·기회·리스크·
  근거·신뢰도. BaseInterpreter 단일경유(과금계측 기존). 캔버스發 on-demand(opt-in 버튼) 또는 SSOT
  캐시 소비. jootek엔 없는 PropAI 차별 — 비전문가 대행 핵심.
- 각 탭에 경량 'AI 인사이트' 1~2문장(해당 인터프리터 요약) 가산.

### I2 신규 자산 surface (방금 만든 것 + 누락 분석)
- 규제 탭: district_legal_refs(규제법령집 14조문 칩) + 특이부지 개발가능 방안 강조.
- 입지 탭 신설: SiteInfraPoiCard(입지점수·POI) — jootek '교통/학군' 등가.
- ESG/환경 탭 또는 통합 rollup: GresbScoreCard·Terrain·Environment 요약.

### I3 추천 건축모델/설계 (jootek式)
- 일조·배치 탭 또는 신설 '설계' 탭: design_interpreter/auto-design 추천 매스·모델 + 썸네일.
  '건축 예상 비용 확인' CTA → cost/estimate-overview 트리거(수지 탭 연계).

### I4 검증·근거·심의 배지
- 각 탭 결과에 VerificationBadge(검증 PASS/WARN/FAIL) + 근거보기(evidence) + 심의엔진 요약(있으면).

### I5 캔버스發 자동 트리거 + 컴팩트 요약
- 부지 선택 시 핵심 분석(zoning·envelope·placement·scenarios) 자동 실행(현재 일부만).
- 카드 'compact' 모드(요약 3~5지표) prop — 캔버스는 요약, 상세는 전용페이지(기존 정련 유지).

### I6 본맵 직접 클릭선택 (P1 훅)
- useParcelSelection 훅 추출 → 우측 본맵 클릭으로 다필지 선택(현 임베드 picker 대체). 회귀 라이브검증 동반.

## 권장 착수 순서
I1(LLM 통합 해석) → I2(규제법령집·입지 surface) → I3(추천 설계모델·건축비용) → I4(검증·근거) → I5/I6.
전부 additive·기존 전용페이지 무손상. I1이 'LLM 미적용' 핵심 갭을 직접 해소.
