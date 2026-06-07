# PropAI 정합·혁신 종합 (2026-06-05)

3개 감사/리서치(04_audit_backend / 04_audit_frontend / 04_research_innovation) 종합.

## 1. 목표↔기획↔구현 정합 매트릭스 (전주기 9단계)

| 단계 | 백엔드 | 프론트 | 정합/갭 |
|------|--------|--------|---------|
| 1 부지발굴 | 공공데이터 실연동(VWorld/NED) | site-analysis 라이브 | △ 도시단위 기회필지 자동발굴 부재 |
| 2 입지/시장 | 상권·POI·실거래·R-ONE | market 부분목업 | △ 대화형은 있으나 시각화 공백 |
| 3 설계 CAD/BIM | 절차생성 IFC→glTF | design-studio 라이브 | ◯ 단, 진짜 생성형(Neural-CAD) 부재 |
| 4 인허가/법규 | 법규 RAG·규제계층 | permits 라이브 | ◯ 단, 90초 즉시 룰체크 UX 부재 |
| 5 사업성/수지/세금 | v2 feasibility·tax·ROI | 라이브 | ◯ 강점 |
| 6 시공/적산 | QTO·5D 강함 | bim-studio 라이브 | △ 공정·기성·원가 실행ERP 빈약 |
| 7 분양 ERP | 66테이블 모델만 | sales 3종 라이브 | ✕ 상태전이·RLS·마이그레이션 미완 |
| 8 ESG/탄소 | GRESB 스코어링 | esg 부분목업 | △ 설계단계 실시간 내재탄소 부재 |
| 9 운영 | digital_twin 단순회귀·drone 스텁 | iot/maintenance 목업 | ✕ 실시간 센서·트윈 부재 |

신뢰성 인프라(검증배지·계산메타·분석원장 해시체인·10 인터프리터)= **글로벌 희소 강점(해자)**.

## 2. 결정적 갭 (경쟁사·논문 대비)
- 진짜 생성형 설계(Forma Neural CAD / ChatHouseDiffusion) — 현재 절차생성.
- 이미지 융합 AVM(위성/스트리트뷰, PLOS One MAPE<4.5%).
- 90초 AI PreCheck 룰체크 UX(Archistar).
- 도시 단위 조닝 시그널·기회필지 발굴(Deepblocks).
- 운영 디지털트윈, RWA/STO 금융 레일.

## 3. 즉시 개선(Quick wins, 자산 이미 존재)
- 라이프사이클 진행 레일(데이터·getNextRecommendedStage 존재, 뷰만 부재).
- 데이터 계보 툴팁(dataSource/fetchedAt 타입 존재, 미렌더).
- AnalysisVerdict 통합카드(검증배지 12곳 vs 해석카드 3곳 비대칭 해소).
- api-client localhost 폴백 화이트리스트 결함(prod 도메인 밖 전 API 실패).
- 사이드바 i18n dictionary화(현 64%→100%), Leaflet CDN→npm.

## 4. 인프라(제미나이 레인 — 본 세션 제외)
라우터 이원화 단일화, public_data_registry 영속화, 단일워커→Redis 권위소스, 런타임 CREATE TABLE→Alembic.

## 5. 권고 우선순위
- **Flagship A(혁신·버들able now):** 90초 AI PreCheck 룰체크 + 조닝 시그널 — 기존 법규 RAG·공공데이터·규제계층 재사용, 차별성 상.
- **Flagship B(전략투자):** 이미지 융합 AVM / Neural-CAD 평면 생성 — 난이도 상, 해자 깊음.
- **Journey 완성(Quick wins):** 진행레일+계보툴팁+AnalysisVerdict+api-client수정 — 저위험, 체감 "완성도" 급상승.
