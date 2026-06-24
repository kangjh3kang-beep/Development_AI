# 지도 중심 단일창 분석 경험 — 최적안 (스토리보드 + 로드맵)

> 작성 2026-06-24. OMC 3에이전트(explore/architect/designer) 조사·설계를 종합. 사용자 요청=
> "하나의 지도 창에서 구획도부터 모든 분석을 맥락형으로, 창 이동 없이. VWorld/토지이음 지적도 기반
> 다필지 구획도 설정·다운로드. 소규모 필지 평수별 개발방식 상세 분류." (레퍼런스: Naver부동산·매물노트/jootek·토지이음)

## 핵심 진단 — 기능 부재가 아니라 컴포지션 부재
빌딩블록 **80% 실재**: SSOT(`useProjectContextStore.siteAnalysis.parcels[]`), 지적도 지도(`ParcelBoundaryMap`=Kakao HYBRID+VWorld geometry+종별색상+`merged_geometry`), 클릭선택(`ParcelPickerMap`), 다필지 통합(`enrichParcels`→`/zoning/integrated-analysis`), 통합외곽선(백엔드 `unary_union`), 평수 게이트(`scenario_simulator.SINGLE_SMALL_MAX_SQM`), **전 패널이 이미 SSOT 구독**(선택 변경→자동 in-place 재분석).
**갭**: ①단일창 셸 부재(현재 25페이지·70+패널 세로 스크롤 분산) ②선택지도(Leaflet)·표시지도(Kakao) 이원화 ③지적도 base 미선택(오버레이만) ④구획도 다운로드 엔드포인트 없음 ⑤평수 티어 매트릭스 미노출.

## 권장 아키텍처
- **신규 `SiteCanvas` 셸**: 2분할(좌 380px 맥락형 탭 rail + 중앙 지도). 기존 패널을 탭으로 **도킹**(재배치). 로직·계산 무손상 재사용.
- **지적도 base = Kakao base/HYBRID + VWorld geometry 오버레이**(권장 — ParcelBoundaryMap 라이브 검증·위성+지적 동시·Referer프록시 회피). VWorld 지적도 WMTS는 토글 레이어로 추가.
- **선택+표시 단일화**: `ParcelPickerMap`의 선택로직을 공용 훅 `useParcelSelection`으로 추출 → `SiteMapCanvas`에서 호출(라이브러리 Kakao 통일).
- **다필지 통합**: 클라 union 금지 → 백엔드 `unary_union` 재사용(`/zoning/parcel-boundaries`의 `merged_geometry`).
- **구획도 다운로드**: 신규 `POST /zoning/parcel-boundaries/export`(geojson→png→pdf). GeoJSON은 메모리 데이터 직렬화(결정론).
- **맥락형 동기화**: 이미 달성된 메커니즘 재배치(전 패널 SSOT 구독). `effectiveLandAreaSqm` 강제·#185 가드 적용.

## ★요약 + 드릴다운 원칙 (2026-06-24 사용자 정련)
지도페이지(SiteCanvas)는 **요약 산출 분석만** 제공한다. **상세 분석·자료 제공은 각 기능 패널의 전용
메뉴/페이지로 연결**(drill-down)한다. 즉 지도페이지 = 개요 허브, 상세는 기존 25개 전용 페이지가 책임.
- 각 맥락형 탭 = ①핵심 요약 카드(3~5지표) + ②"상세보기 →" CTA(해당 기능 페이지로 라우팅).
- 이미 존재하는 전용 페이지(site-analysis·design·cost·feasibility·legal·permit·esg·report·cad·bim 등)를
  버리지 않고 **상세 뷰로 재활용** → 지도페이지는 과밀 방지·진입 속도 유지, 상세는 깊이 유지.
- 효과: ①한 화면에서 전체 조망(요약) ②필요 시 1클릭으로 해당 패널 상세 진입(자료·다운로드·편집).
  창 이동은 "원할 때만"(요약 단계는 무이동, 상세는 의도적 drill-down).

## 맥락형 탭 구조 (좌측 rail — 요약 카드 + 상세 CTA)
| 탭 | 요약(지도페이지 표시) | 상세 연결(드릴다운) |
|----|---------------------|--------------------|
| 토지 | 지번·지목·면적·공시지가·용도지역 | → /site-analysis(토지대장·실거래·적정매입가) |
| 규제 | 건폐/용적(실효)·특이부지·지구단위 | → /legal·/permit(규제계층·인허가 상세) |
| 건물 | 건축물대장 요약·노후도 | → /site-analysis(대장 전문·집합건물 대지지분) |
| 개발방식 | **평수 티어 매트릭스(가능/조건부/불가)**·추천 | → /permit(인허가 로드맵·시나리오 상세) |
| 일조·배치 | 최적 배치안·8방위 일조 요약 | → /design(설계 스튜디오·CAD/BIM) |
| 수지 | ROI·총사업비·매출 요약 | → /feasibility(수지 편집·민감도) |
| 통합분석 | AI 해석 요약·신뢰도·리스크 | → /report(은행제출 보고서·PDF) |
- 탭 전환 = **로컬 view state**(orchestration store·SSOT 무접촉 — RunMode 오류 재발 방지).
- 요약 카드는 기존 패널의 '요약 모드'(props로 compact) 또는 경량 요약 컴포넌트, 상세는 기존 페이지 그대로.

## 스토리보드 (프로젝트 생성 단일창)
STEP0 진입(검색창+지도) → STEP1 주소검색→지도 flyTo·필지 하이라이트 → STEP2 필지확정→좌패널 자동채움(스켈레톤→실데이터) → STEP3 (다필지)인접필지 추가선택→바텀 버킷 누적·인접성검증 → STEP4 구획도 인라인 오버레이(미리보기+PNG/PDF) → STEP5 6탭 순차 채움 → STEP6 개발방식 매트릭스→최적안 → STEP7 프로젝트 저장. (전 과정 창 이동 0.)

## 소규모 개발방식 평수 티어 매트릭스 (★첫 증분)
백엔드 `_classify_by_pyeong_tier()`(scenario_simulator 내, 기존 게이트 상수 재사용·순수 additive):
- T1 ~50평(<165㎡): 단순건축만
- T2 ~100평(<330㎡): +자율주택정비(주거<2000㎡)
- T3 ~300평(<1000㎡): 단독 정비 하한 직전(인접통합 권고)
- T4 ~1000평(<3300㎡): +모아주택(≥1500㎡)·지구단위 편입
- T5 1000평+(≥3300㎡): +지구단위 단독(≥5000)·도시개발(≥10000)·정비사업
출력: `{tier, pyeong, matrix:[{scheme, status:가능|조건부|불가, reason, area_gate}], self_standing_only}`.
프론트 `DevelopmentMethodMatrix`: 평수구간×방식 가능(녹)/조건부(황)/불가(회), 현 필지 하이라이트, 인접통합 시 가능화 표시.

## 로드맵 (무손상·additive 우선)
- **P0** 멀티세션 claim(auto_zoning.py·useProjectContextStore), base map 확정(B).
- **P1** `useParcelSelection` 훅 추출(순수 리팩토링·동작동일 라이브검증).
- **P2** `SiteMapCanvas`=ParcelBoundaryMap+mode=select+VWorld 지적도 토글.
- **P3** `/zoning/parcel-boundaries/export`(geojson→png→pdf)+`ParcelExportButton`.
- **P4** `SiteCanvas` 셸+`ContextPanelRail`(기존 패널 도킹), site-analysis page 교체+`?legacy=1` 폴백.
- **P5** 평수 매트릭스+projects/new 통합.
- **★즉시 착수(P-independent, additive)**: 평수 티어 매트릭스(백엔드+프론트), GeoJSON export — 셸 마이그레이션 위험 없이 즉시 가치.

## 위험요소
#185 렌더루프(값변화시에만 setState 가드), 다필지 면적 대표값 덮임(effectiveLandAreaSqm 강제), VWorld 타일 Referer/성능(프록시 경유), 멀티세션 충돌(P0 claim), useParcelSelection 추출 회귀(P1 라이브검증), PNG/PDF 의존성(GeoJSON 먼저).
