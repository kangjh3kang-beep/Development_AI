# PropAI 경쟁 리서치 종합 보고서

> 작성일: 2026-06-11 | 작성: PropAI 제품 전략 | 기반: 6트랙 병렬 리서치 (AI 건축설계 자동화 / 수지분석·사업성 플랫폼 / 웹 CAD·BIM 오픈소스 / AI 평면생성 연구 / 적산·공사비 자동화 / AI 자동입력·폼 워크플로 UX)

---

## ① 경쟁 지형 요약 (Executive Summary)

### 핵심 결론 한 줄
**글로벌·국내를 통틀어 "부지분석 → 법규 → 설계 → 수지 → 인허가 → 시공 → 분양 → 운영"을 하나의 데이터 모델로 잇는 전주기 플랫폼은 존재하지 않는다.** 모든 경쟁자는 단일 단계의 점(point) 솔루션이며, PropAI의 핵심 포지셔닝은 이 전주기 통합 + 한국 법규·세제 룰엔진의 결합이다.

### 지형 구조 (4개 전선)

| 전선 | 글로벌 강자 | 국내 강자 | 공백 |
|---|---|---|---|
| **AI 설계 생성** | TestFit, Autodesk Forma(Neural CAD), Snaptrude, Finch3D, Maket | 스페이스워크 랜드북, 텐일레븐 빌드잇 | 한국 법규 + 편집 가능 생성 + 단위세대 평면까지 내려가는 풀스택 |
| **수지·사업성 분석** | ARGUS/EstateMaster(세후 DCF·몬테카를로), Deepblocks, Feasibly | 랜드북, 밸류맵, 닥터빌드 AiCON | 한국 세제(38종) 통합 세후 IRR, 확률 분석, 버전드 룰엔진 — 국내 0개사 |
| **적산·공사비** | RIB CostX, iTWO, Togal.AI/Kreo | 콘엑스, Conpa, XCOST | 도면→물량→표준품셈 내역→수지분석 직결 파이프라인 (Vico 단종으로 5D 공백) |
| **워크플로 UX** | MS Power Apps AI Form Fill, IBM Carbon AI Label, Airtable Field Agents | (부재) | 필드 단위 provenance + 재계산 전파 + audit trail을 가진 국내 프롭테크 전무 |

### 시장 타이밍 신호
- **2026년 Autodesk Neural CAD GA 예정** — AEC 파운데이션 모델이 표준화되기 전에 한국 데이터(건축물대장·분양 평면) 기반 생성 + 세움터 인허가 연동을 선점해야 글로벌 진입 시에도 방어 가능.
- **Trimble Vico 단종(2024-06)** — 5D BIM(물량-내역-공정-현금흐름) 미드마켓에 공백 발생.
- **Hypar의 text-to-BIM 공식 철회** — "자유 프롬프트 단독 설계"는 실패가 검증됨. 성공 패턴은 *구조화 입력 + 대화형 보조 편집 + 항상 편집 가능한 산출물* 하이브리드.
- **Feasibly의 가격 앵커($10,000·3일 bank-ready 보고서)** — 같은 산출물을 분 단위·구독가로 내면 가격 파괴 포지션 확보.
- **건설공사비지수 7개월 연속 사상 최고치(2026-03 134.42)** — 공사비 리스크 자동 반영 수요 급증.

### 가장 직접적인 경쟁자와의 거리
- **랜드북(스페이스워크)**: 한국 법규 가설계의 유일 상용 — 그러나 *결과 열람형*(편집 불가), 수지는 개략 추정(세금·PF·세후 IRR 없음), 인허가·시공·분양 미커버.
- **ArkDesign.ai**: PropAI 컨셉과 가장 유사한 해외 모델(평면 자동생성+수지 리포트) — 그러나 이스라엘 기업·미국 코드 전용으로 **한국 시장은 비어 있음**.

---

## ② 트랙별 핵심 발견 표

### 트랙 1 — AI 건축설계 자동화 (글로벌 8 + 한국 2)

| 제품 | 기능 | 강점 | 약점/공백 |
|---|---|---|---|
| **TestFit** (미국) | 대지 입력→사이트플랜·매스·유닛·주차 실시간 생성, Generative Design(FAR·Yield on Cost 목표 탐색) | 설계↔수지 실시간 연동의 원조, 미국 상위 멀티패밀리 디벨로퍼 50% 사용 | 고가(연 $10K+), 미국 코드 전용, 인허가 도면 불가, 데스크톱 설치형 |
| **Autodesk Forma** (구 Spacemaker) | 일조·바람·소음·탄소 실시간 AI 분석, Neural CAD(2026 GA 예정)로 내부 레이아웃 초 단위 생성 | 환경분석 사실상 표준, $185/월, 업계 최초 AEC 파운데이션 모델 | 전문가 도구(비전문가 부적합), 2D 인허가 도면 미산출, 한국 법규·수지 미지원 |
| **Snaptrude** (미국/인도) | 브라우저 BIM, text-to-BIM(RFP→LOD 300), AI 리서치 통합 | "항상 편집 가능한 BIM" 철학, 무료 플랜 관대, Revit 양방향 | 미국 법규 중심, 인허가 정합성 미보장, 산출물 검증에 전문가 필요 |
| **Arcol** (미국) | 브라우저 협업 설계, zoning·코스트 라이브 동기화, Figma식 멀티플레이어 | 협업 UX 업계 최고, 비전문가 열람·코멘트 최적 | AI 자동생성 거의 없음(수동 모델링), 법규·수지 자동화 없음 |
| **Hypar** (미국) | 면적 프로그램→매스·코어·구조 그리드 자동 제안 | 시스템 수준 자동화, Elements 오픈소스 | **text-to-BIM 공식 철회**(업계 교훈), 비전문가 접근성 낮음 |
| **Finch3D** (스웨덴) | 매싱→층별 평면 자동 생성(유닛믹스·코어), 불가능 사유 설명 | 그래프 기반 설명가능 생성, €49/월 저가 | 유럽 주거 특화, 핵심 기능은 연 €12,000 엔터프라이즈 묶임 |
| **Maket.ai** (캐나다) | 자연어 대화→주거 평면 수백 개 생성+대화형 편집 | 비전문가 대화형 생성·편집 루프가 실제 작동하는 거의 유일한 제품, $20/월 | 단독주택 한정, 공간논리 오류, DWG 내보내기 미지원 |
| **ArkDesign.ai** (이스라엘) | 대지·법규·면적→schematic 평면+수지 리포트 PDF | PropAI와 가장 유사한 컨셉, 무료 Lite, 특허 AI | **미국 코드 전용 — 한국 시장 공백**, 편집 자유도 제한 |
| **랜드북** (한국, 스페이스워크) | 필지 선택→AI 가설계(일조사선·주차 법규 내 최대 규모)+수익 추정 | 한국 법규 반영 유일 상용 엔진, 검증된 무료→유료 BM, RL 기반 배치 | **편집 불가 열람형**, 매스 수준(인허가 연결 안 됨), 시공·분양·운영 미커버 |
| **텐일레븐 빌드잇** (한국) | 아파트 단지 배치 자동화(5일→30분), 일조·법규 검토 | 한국 단지 배치 특화, 현대건설·호반 전략투자 | 단지 배치 한정, B2B 전용(셀프서비스 아님), 이후 단계 미커버 |

### 트랙 2 — 수지분석·사업성 플랫폼 (글로벌 3 + 한국 5)

| 제품 | 기능 | 강점 | 약점/공백 |
|---|---|---|---|
| **Deepblocks** (미국) | AI 부지발굴+조닝+3D 매싱+개략 수지, 조닝 변경 알림 | 조닝 자동화·스크리닝 속도 압도적 | 재무분석이 1년 스냅샷 ROC 수준(설계 철학), DCF·세금·몬테카를로 없음 |
| **Feasibly** (미국) | 멀티에이전트 LLM 타당성 보고서 서비스(bank-ready, 3일, $10K~) | 휴먼인더루프 결합, PropAI verify-agent와 유사 사상 | 셀프서브 SaaS 아님(고가 서비스), 초기 단계, 한국 데이터 전무 |
| **ARGUS Developer + EstateMaster** | 세후 DCF·부채·민감도·**몬테카를로**·8개 시나리오 비교 | 글로벌 SOTA, 금융기관의 lingua franca, 조사 대상 중 유일한 확률분석 | 수동 입력 중심, AI 부재, **한국 세법·인허가 미지원**, 고가·가파른 학습곡선 |
| **랜드북** (한국) | AI 설계+법규+수익 추정 원스톱 | 국내 최초·최고 인지도, 시세 데이터 결합 | 수지가 개략 추정 — 세금 38종·PF·세후 IRR·몬테카를로 없음, 법규 버전관리 미흡 자인 |
| **밸류맵** (한국) | 실거래가 지도+AI 설계+3세대 AVM(생성-검증 이중 AI) | 데이터 커버리지·인지도 최상위, 이중 AI 검증 구조 | 사업성 분석은 부가기능 — 세금·금융·현금흐름·시나리오 없음 |
| **부동산플래닛** (한국) | 노후도 특허 기반 재개발 부지 스크리닝, 동·호수 AVM | 노후도 탐색 독자 영역, 전국 데이터 정합성 | 수지·설계·법규·세금 기능 사실상 없음(탐색 전용) |
| **하우빌드** (한국) | 소규모 건축 입찰·시공관리, 맞춤건축(규모검토+수지 리포트) | 20년 실계약 공사비 데이터(600+ 프로젝트), 시공 실행력 독보적 | 수지가 인적 서비스(300만원+수수료), 자동화·세금·시나리오 없음 |
| **닥터빌드 AiCON** (한국) | 규모검토→공사비→수지분석 일괄, 정비사업 특화 | 국내 소수의 일괄 흐름, 공공 납품 레퍼런스 | 수지가 "평균가 vs 예상가" 정적 비교 수준, 세금·PF·민감도·버전관리 전무 |

### 트랙 3 — 웹 CAD/BIM 오픈소스

| 라이브러리 | 기능 | 강점 | 약점/공백 |
|---|---|---|---|
| **ThatOpen web-ifc** | 브라우저/Node WASM IFC 읽기·**쓰기** | MPL-2.0(SaaS 안전), JS에서 IFC 내보내기 가능한 사실상 유일 경로 | 0.0.x API 불안정, 쓰기 API 저수준, IFC 4.3 지오메트리 부분 지원 |
| **ThatOpen Components + Fragments 2.0** | Three.js BIM 프레임워크(측정·단면·평면도·DXF), IFC 대비 10배 압축 포맷 | MIT, 분기별 릴리스, 수백만 엘리먼트 처리 | React 공식 래퍼 없음, 심화 커스터마이징은 소스 탐독 |
| **OpenCascade.js** | 산업용 CAD 커널 WASM(NURBS·불리언·STEP) | JS 생태계 최강 기능 깊이 | LGPL-2.1(법무 검토), 수십 MB WASM, 성숙도 중하, IFC 무관 |
| **chili3d** | Three.js+OCCT 브라우저 3D CAD | 웹 CAD UI 아키텍처(커맨드·스냅·트랜잭션) 교본 | **AGPL-3.0 — 코드 차용 금지**(SaaS 소스 공개 의무), 알파 단계 |
| **mlightcad/cad-viewer** | 백엔드 없는 브라우저 DXF/DWG 뷰어·에디터 | MIT, 대형 도면 60FPS, 웹 2D AutoCAD 대체 로드맵 | 편집은 로드맵 단계, DWG 일부 미지원 |
| **Maker.js** | 파라메트릭 2D 벡터→DXF/SVG/PDF | Apache-2.0, Next.js 통합 난이도 하, 서버 액션 DXF 생성 가능 | 유지보수 모드(기능 정체), 에디팅 UI 없음 |
| **Speckle** | AEC 데이터 허브(25+ 포맷 버전관리), IfcOpenShell 임포터 | Apache-2.0, IFC 4.3 파싱은 ThatOpen보다 앞섬 | three 버전 충돌 주의, 셀프호스팅 운영 부담, 2D 편집 없음 |
| **Y.js** | CRDT 실시간 협업(오프라인·undo·커서) | 가장 빠른 CRDT, MIT, 생태계 풍부, Rayon이 멀티플레이어 2D CAD 시장성 입증 | CAD 특화 스키마 설계는 자체 몫, 대형 문서 GC 관리 필요 |
| **DXF JS 군** (dxf-parser / @tarikjabiri/dxf) | DXF 파싱(읽기) + TS DXF 생성(쓰기) | 모두 MIT, 읽기+쓰기 조합이 사실상 표준 패턴 | 양방향 단일 라이브러리 부재(매핑 코드 필요) |

### 트랙 4 — AI 평면생성 연구 (학계→상용)

| 연구/제품 | 기능 | 강점 | 약점/공백 |
|---|---|---|---|
| **RPLAN** 데이터셋 | 중국 주거 평면 8만 장 표준 벤치마크 | 규모·주석 품질, 한국 공동주택과 형태 친화성 | 한국 판상형 3~4베이·발코니 확장·전용률 문법 미반영 — **K-RPLAN 부재** |
| **Graph2Plan** (SIGGRAPH 2020) | 경계+그래프→평면, retrieve-then-adapt | 경계 제약 최초 실용화, 0.4초/장, 코드 공개 | 박스 기반 벽 정합 거침, 축정렬 한정 |
| **WallPlan** (SIGGRAPH 2022) | 벽 그래프 중심 생성 | 생성 즉시 벽 정합 보장 → CAD/BIM 변환 품질 우수 | 공식 코드 미공개 |
| **HouseDiffusion** (CVPR 2023) | Transformer 디퓨전, 벡터 코너 직접 생성 | 비-맨해튼(Y자 타워형) 가능, 코드 완전 공개 — **한국 파인튜닝 PoC 1순위** | 외곽 경계 고정 입력 미지원, 샘플링 느림 |
| **MaskPLAN** (CVPR 2024) | 부분 입력→나머지 자동완성 | "84㎡·안방 남향만 지정→자동완성" UX의 레퍼런스, 코드 공개 | 한국 법규 하드 제약 미반영 |
| **HouseTune/HouseLLM, LLM-RLVR** (2024~26) | LLM 공간추론+디퓨전 정제 / 검증 가능 보상 RL | "LLM 스펙 생성→엔진 도면화" 가설의 학술 검증, 제약위반 94% 감소 | 결정론적 법규 검증기 부재(학계 공백), 코드 비공개 다수 |
| **Text-to-Layout / FMLM** (2025~26) | GPT-4o JSON→Revit API 자동 모델링 / 마크업 next-token 통일 | PropAI 검토 아키텍처의 최신 실증 | **건축법규 컴플라이언스 미통합을 저자 스스로 한계로 명시** |
| 상용 (Finch3D·Maket·TestFit·랜드북·빌드잇) | 유닛플랜·배치 자동화 상용화 | 결정론적 솔버+LLM 인터페이스 조합이 검증된 패턴 | 해외는 한국 평면 문법 미지원, 국내 양사는 **단위세대 평면까지 안 내려감** |

### 트랙 5 — 적산·공사비 자동화

| 제품 | 기능 | 강점 | 약점/공백 |
|---|---|---|---|
| **RIB CostX** | 2D/BIM 물량 자동 추출+라이브 링크 워크북, 리비전 비교 | 모델 변경→물량·견적 실시간 갱신, QS 글로벌 표준 | 한국 표준품셈·일위대가 미지원, 수지분석과 단절, 데스크톱 |
| **Trimble Vico** | 5D BIM(물량·공정·코스트) — **2024-06 지원 종료** | 4D+5D 통합 개념 정착시킨 선구자 | 단종 → 미드마켓 5D 공백 = PropAI 기회 |
| **RIB iTWO 4.0** | 설계~시공 단일 모델 5D ERP | openBIM, 전 단계 데이터 일관성 | 엔터프라이즈 가격·복잡도, 디벨로퍼 수지 관점 부재 |
| **Togal.AI / Kreo** | AI 도면 인식 2D takeoff | 12분 takeoff, $35~299/월 접근성 | 실측 85~92%(사람 20% 검수), 내역·수지 다운스트림 없음, 한국 표기 미지원 |
| **콘엑스 ConEx** (한국) | CAD 붙여넣기→물량→표준품셈 검증 내역서, 기성 서류 자동화 | 표준품셈·일위대가 정합, 내역 3일→30분 | 반자동(전체 도면 인식 아님), 전주기 무관, BIM 미지원 |
| **Conpa** (한국) | DWG→AI 물량→BOQ 10분 | 98% 정확도 주장, 대기업 레퍼런스 | **단가 출처 불투명**, 표준품셈 정합 불명, DWG만, 수지 미연결 |
| **XCOST / 코리아소프트 EMS** (한국) | 내역서·일위대가 작성, 물가 DB 연동, 조달청 호환 | 국내 내역 포맷 사실상 허브, 공공발주 생태계 정합 | 물량산출 수동, AI 부재, 수지분석 없음 |
| **건설공사비지수** (KICT) | 월간 공사비 물가 지수 (KOSIS OpenAPI) | 시점 보정·에스컬레이션 공식 기준, 무료 API | 거시 보정용(개별 자재 단가 아님) |

### 트랙 6 — AI 자동입력·동적 폼 워크플로 UX

| 사례 | 기능 | 강점 | 약점/공백 |
|---|---|---|---|
| **MS Power Apps AI Form Fill** | 제안→검토→수락 HITL 폼, 출처 인용 hover | 현존 가장 완성된 패턴, 양방향 소스 추적 | 수락 후 출처 이력 소멸(영구 audit trail 부재) |
| **IBM Carbon AI Label** | 디자인 시스템 레벨 AI provenance 라벨 | 자동값 vs 수동값 구분을 토큰 레벨로 표준화한 유일 사례 | 값 충돌(재계산 vs 오버라이드) 시나리오 미커버 |
| **Notion AI Autofill** | DB 속성 자동 채움+조건부 로직 | 반응형 자동 채움의 대중적 레퍼런스 | **자동 갱신이 수동 편집을 덮어씀 — 반면교사** |
| **Airtable Field Agents** | 필드=AI 에이전트, 셀 단위 실행 | PropAI 부지분석 필드에 이식 가능한 아키텍처 | 셀 간 의존성·재계산 순서 제어 없음 |
| **n8n HITL** | 승인 게이트 워크플로(타임아웃 에스컬레이션) | "실수의 대가가 큰 액션만 게이트" 원칙 명문화 | 필드 레벨 provenance와 별개 계층 |
| **인슈어테크 프리필** (Hippo·Fenris) | 주소 1개→수백 필드 자동 채움 | 입력 최소화 온보딩의 가장 성숙한 상용 사례 | 채움 이후 재계산 전파·audit trail 미커버 |
| **랜드북** (국내 벤치마크) | 필지 클릭→대량 자동 산출 | 입력 최소화 패턴 국내 선행 | **필드 provenance·오버라이드 재계산·HITL 게이트 전무** |
| 기반 기술 (스프레드시트 DAG·금융모델링 색상·Optimistic Undo) | 의존성 재계산, 파랑=수동/검정=수식 관행 | 부동산 금융 사용자에게 학습 비용 제로인 provenance 언어 | 기존 폼 라이브러리에 DAG·오버라이드 보호 미내장(자체 구현 필요) |

---

## ③ PropAI 대비 비교 매트릭스

◎ = 강함 / ○ = 보유 / △ = 부분·개략 / × = 없음

| 역량 | TestFit | Forma | Snaptrude | Maket | ArkDesign | Finch3D | 랜드북 | 빌드잇 | ARGUS/EM | Deepblocks | 닥터빌드 | 콘엑스/Conpa | **PropAI (목표)** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 한국 법규 (일조사선·주차 조례·지구단위) | × | × | × | × | × | × | ◎ | ○ | × | × | △ | × | **◎ (버전드 룰엔진)** |
| AI 설계 생성 (배치·매스) | ◎ | ○ | ○ | △ | ○ | ○ | ○ | ◎ | × | △ | △ | × | **○** |
| 단위세대 평면 자동 생성 | △ | △(베타) | △ | ◎ | ○ | ◎ | × | × | × | × | × | × | **◎ (한국 평면 문법)** |
| 생성 후 사용자 편집 | △(파라미터) | ○ | ◎ | ◎ | △ | ○ | **×** | × | – | × | × | × | **◎ (대화+캔버스)** |
| 비전문가 셀프서비스 UX | △ | × | △ | ◎ | ○ | × | ○ | × | × | △ | ○ | × | **◎** |
| 설계↔수지 실시간 연동 | ◎ | × | × | × | ○ | × | △ | × | × | △ | △ | × | **◎ (한국 데이터)** |
| 세후 IRR/NPV (세금 통합 DCF) | × | × | × | × | × | × | × | × | ◎(해외 세제) | × | × | × | **◎ (38종 세금 엔진)** |
| 몬테카를로 확률 분석 | × | × | × | × | × | × | × | × | ◎(EM 유일) | × | × | × | **◎ (국내 유일 목표)** |
| 적산·공사비 (표준품셈 정합) | × | × | × | × | × | × | × | × | × | × | △ | ◎ | **○ (정밀도 사다리)** |
| 인허가 도서·세움터 연동 | × | × | × | × | × | × | × | × | × | × | × | × | **○ (전 시장 공백)** |
| IFC/DXF 진짜 BIM 산출물 | ○(DWG) | ○ | ◎ | × | × | ○ | **×** | × | × | × | × | × | **○ (국내 최초)** |
| 필드 provenance·audit trail | × | × | × | × | × | × | × | × | × | × | × | × | **◎ (전 시장 공백)** |
| 전주기 커버리지 | 매스·수지 | 조기설계 | 설계 | 평면 | 평면·수지 | 평면 | 부지~개략수지 | 단지배치 | 수지~운영 | 부지~개략수지 | 규모~수지 | 적산 | **부지→운영 전체** |

**판독**: PropAI가 단독 선점 가능한 셀은 ①한국 세제 통합 세후 IRR ②몬테카를로(국내) ③인허가·세움터 연동 ④필드 provenance/audit trail ⑤전주기 통합. 경쟁 우위 확보가 필요한 셀은 ⑥"한국 법규 + 편집 가능 생성"(랜드북의 편집 불가 vs Maket의 한국 부재 사이 공백) ⑦단위세대 평면(국내 상용 공백).

---

## ④ 기술 스택 권고 (웹 CAD/BIM · AI 도면생성)

### 4-1. 웹 CAD/BIM 권고 스택 (전부 MIT/MPL/Apache 계열 — SaaS 임베드 법적 리스크 없음)

| 계층 | 권고 | 라이선스 | 비고 |
|---|---|---|---|
| **3D BIM 뷰** | `@thatopen/components` v3.4 + `web-ifc` 0.0.77 + **Fragments 2.0** 스트리밍 | MIT + MPL-2.0 | IFC 대비 10배 경량 — 모바일·현장 태블릿 뷰잉 성능 우위 |
| **2D 도면 편집** | 자체 캔버스 에디터(SVG 또는 Three.js ortho) + **maker.js**(파라메트릭 생성) + **dxf-parser**(읽기) + **@tarikjabiri/dxf**(쓰기) | Apache/MIT | LLM 파라미터→maker.js 모델→DXF 내보내기 파이프라인이 매우 단순 |
| **IFC 내보내기** | web-ifc 쓰기 API로 IfcProject→IfcSite→IfcBuildingStorey→IfcWall/IfcSlab 조립. **IFC4(Add2) 타깃**, 4.3은 인프라 확장 시 서버사이드 IfcOpenShell 보조 변환 | MPL-2.0 | 국내 프롭테크는 매스를 이미지·수치로만 제공 — "진짜 IFC"는 국내 최초 차별화 |
| **실시간 협업** | **Y.js + Hocuspocus** (y-websocket 별도 노드, 스냅샷만 Supabase Postgres 저장) | MIT | Rayon이 멀티플레이어 2D CAD 시장성 입증 |
| **정밀 불리언** (일조사선 매스컷) | OpenCascade.js — **WebWorker 격리 + LGPL 동적 링크 유지, 도입 지연 가능** | LGPL-2.1 | MVP는 maker.js 2D + 단순 extrusion으로 충분 |
| **DWG 뷰잉/마크업** | mlightcad/cad-viewer 코어 패키지 발췌 | MIT | 관청 제출용 DXF 미리보기에 즉시 활용 |
| **설계사 데이터 수집** | Speckle 셀프호스팅을 **경쟁자가 아닌 커넥터**로 — Revit/Rhino 데이터를 수지 엔진으로 유입 | Apache-2.0 | viewer의 three ^0.140 고정 — ThatOpen과 동일 페이지 공존 시 버전 충돌 주의 |
| **금지 사항** | chili3d 코드 차용 금지(AGPL-3.0 — SaaS 전체 소스 공개 의무). 아키텍처(커맨드 패턴·트랜잭션 undo)만 참고 | – | |
| **Next.js 통합 공통 패턴** | 모든 WASM(web-ifc·LibreDWG·OCCT)은 `/public` 서빙 + `dynamic(ssr:false)` + WebWorker 통일, three 버전은 ThatOpen 요구 버전으로 고정 | – | |

### 4-2. AI 도면생성 아키텍처 권고

**채택 패턴: "LLM → 구조화 JSON 스펙 → 파라메트릭 엔진 → 결정론적 법규 검증 → 재생성 루프"** (2025~26 학계 실증 완료: Text-to-Layout의 GPT-4o JSON→Revit API, FMLM 마크업 next-token. Hypar의 text-to-BIM 철회가 자유 프롬프트 단독의 실패를 검증)

1. **입력 UX**: 구조화 입력(유닛믹스·층수·규모 슬라이더) + 대화형 보조 편집(Maket 패턴) + MaskPLAN식 부분입력 자동완성("84㎡·4베이·안방 남향만 지정") + ChatHouseDiffusion식 영역 한정 편집.
2. **출력 스키마**: 한국 유닛플랜 도메인 전용 JSON Schema(베이 수, 코어 타입, 발코니 확장, 실 클러스터) 강제.
3. **내부 자료구조**: 박스가 아닌 **벽 중심선 토폴로지(WallPlan) + 마크업 직렬화(FMLM)** — CAD/DXF/IFC 변환 품질이 가장 높은 표현.
4. **법규 검증 통합**: PropAI 보유 법규 엔진(채광·피난·인동거리·면적 산정)을 생성 후 결정론적 체커 + 위반 시 재생성 루프로 연결. 중기적으로 RLVR(검증 가능 보상 강화학습 — 제약위반 94% 감소 실증)로 자체 모델 파인튜닝. **법규 검증기 통합은 학계에도 공백 — 논문 수준을 넘는 차별화.**
5. **데이터 전략**: K-RPLAN 구축(분양 평면 공시자료 + LH/SH 표준평면, 5만 장 목표 — 국내 학계에 50K 선례 존재) → 코드 공개된 **HouseDiffusion·MaskPLAN 파인튜닝으로 PoC**. 비-맨해튼 지원으로 타워형(Y자) 평면까지 커버.
6. **모든 생성 결과에**: 근거 법규 조항 인용 + LOD 단계 명시 + 불가능 사유 설명(Finch 'why infeasible' 패턴) — AI 도면 불신의 정면 돌파.

### 4-3. 적산·폼 UX 스택 보강

- **적산**: IfcOpenShell(IFC 파싱·BaseQuantities) + LLM(MCP 도구호출)로 표준품셈 코드 매핑 + 조달청 표준공사코드 공공데이터(2025-09 공개) 내장 + 한국물가정보/물가자료 월간 DB 제휴 + **건설공사비지수 KOSIS OpenAPI**(orgId=397) 자동 연동 3층 단가 구조.
- **폼 워크플로**: 필드 5상태 머신 `{empty → ai_suggested → ai_filled → user_edited → locked}` + 스프레드시트식 의존성 DAG(위상 정렬 재계산) + 금융모델링 색상 관행(파랑=수동/검정=계산) + 필드 단위 이벤트 소싱 audit trail. react-hook-form 등에 미내장이므로 자체 계층 구현.

---

## ⑤ "우리만의 독보적 기능" 후보 Top 10

### 1. 전주기 원파이프라인 (부지분석→법규→설계→수지→인허가→시공→분양→운영)
- **근거 (경쟁사 부재)**: 조사한 30여 개 제품 전부 단일 단계 점 솔루션(Forma=부지, TestFit=매스·수지, Finch=평면, SWAPP=시공도서, 하우빌드=시공, ARGUS=수지). 한 데이터 모델로 잇는 플레이어는 글로벌·국내 모두 부재.
- **실현 가능성 (PropAI 자산)**: 높음 — ProjectContext 단일 데이터 모델이 이미 설계 사상의 중심. auto_zoning·design·feasibility 모듈이 같은 컨텍스트를 공유하는 구조를 확장.

### 2. 38종 세금 통합 세후 IRR/NPV 디시전 엔진 ("한국판 ARGUS")
- **근거**: 글로벌 SOTA(ARGUS)는 세후 DCF가 표준이지만 한국 세제를 모르고, 한국 8개사 중 세금을 현금흐름에 통합한 곳은 **0개**.
- **실현 가능성**: 매우 높음 — 38종 세금 4단계(취득A/공사B/분양C/양도D) 엔진 보유. `/api/v2/feasibility` 현금흐름 타임라인에 시점별 주입만 하면 됨. 단, 선결 과제: 엔진 이원화(tax/* vs tax_ai_service 세율 불일치)와 종부세 flat 0.5% 오류 교정.

### 3. 법령 시행일 버전드 룰엔진 + 생성 결과 조항 인용
- **근거**: 랜드북조차 "법규가 연 수회 개정"을 한계로 자인. 세율·구간·특례를 (시행일, 종료일) 메타데이터로 외부화해 거래일 기준 자동 선택하는 경쟁사는 전무 — 2026-05-09 양도세 중과배제 종료 같은 한시조항을 코드 수정 없이 반영.
- **실현 가능성**: 높음 — 기존 법규 엔진·세금 엔진의 룰 데이터를 effective-dated 스키마로 리팩토링하는 작업. verify-agent가 버전 정합성 검증을 담당 가능.

### 4. 몬테카를로 확률 수지분석 (P10/P50/P90 + 손실 확률)
- **근거**: 전 조사 대상 중 EstateMaster만 보유(해외 세제), 한국 플랫폼은 전무. 분양가·공사비·금리·분양률 분포 입력 → 손실 확률 산출은 PF 심사 언어로 직결되는 **국내 유일 기능**.
- **실현 가능성**: 높음 — 결정론적 수지 엔진이 이미 있으므로 입력 파라미터를 분포로 확장해 시뮬레이션 래퍼만 추가. 건설공사비지수 KOSIS API가 공사비 변동성의 실데이터 근거 제공.

### 5. 엔티티 구조 옵티마이저 (개인/공동/법인/지주택조합/리츠/PFV 병렬 비교)
- **근거**: 택스아이(세금계산 SOTA)는 디벨로퍼 맥락이 없고 ARGUS는 한국 엔티티를 모름. 동일 프로젝트를 6개 사업 구조로 병렬 세무계산해 총세부담·세후수익 순위를 제시하는 제품은 시장에 없음.
- **실현 가능성**: 매우 높음 — 38종 세금 엔진의 가장 자연스러운 확장(엔티티별 세율·중과 규칙 분기 추가).

### 6. 한국 중소규모 개발의 "비전문가 대화형 가설계 + 편집" 루프
- **근거**: Maket(단독주택, 편집 가능)과 랜드북(공동주택 규모검토, **편집 불가 열람형**) 사이의 정확한 공백 — 다세대·오피스텔·근생을 비전문가가 대화+슬라이더로 생성하고 편집까지 하는 제품 부재. Hypar 철회로 검증된 하이브리드 UX(구조화 입력+대화 편집+항상 편집 가능 산출물)를 적용.
- **실현 가능성**: 중상 — auto_zoning·법규 엔진이 생성 제약을 제공, 4-2 아키텍처(LLM→JSON→파라메트릭 엔진) 신규 구축 필요하나 학계 실증 코드(HouseDiffusion·MaskPLAN) 활용 가능.

### 7. 평면↔수지 실시간 루프를 유닛플랜 레벨로 (한국 데이터)
- **근거**: TestFit의 yield-on-cost 연동은 매스 레벨·미국 데이터·연 $10K+. 평면 변경이 전용률·분양가·공사비·IRR에 즉시 반영되는 유닛플랜 레벨 통합은 해외 상용에도 드물고 국내 부재. 가격은 TestFit의 1/5로 이식 가능.
- **실현 가능성**: 높음 — 수지 엔진 + 실거래·청약 데이터 연동이 기존 자산. 설계 모듈과의 이벤트 연결(DAG 재계산)만 추가.

### 8. 진짜 BIM 산출물: 웹에서 IFC/DXF 내보내기 + 세움터 인허가 연동 지향
- **근거**: 랜드북·하우빌드 등 국내 프롭테크는 매스 결과를 이미지·수치로만 제공. web-ifc 쓰기로 설계사무소 Revit 워크플로에 직결되는 IFC를 내보내면 **국내 최초**. 인허가 제출(세움터)까지는 SWAPP·qbiq 등 글로벌도 못 감 — 2026 Autodesk Neural CAD GA 전 선점 시 방어 해자.
- **실현 가능성**: 중 — 4-1 스택(web-ifc·maker.js·@tarikjabiri/dxf, 모두 MIT/MPL)으로 기술 경로 확보. 세움터 연동은 단계적 접근(DXF 표준 레이어 자동화 → 도서 자동화).

### 9. LLM 표준품셈 매핑 + "정밀도 사다리" 공사비 엔진 (개산 ±15% → BIM QTO → 상세 ±5%)
- **근거**: "물량→어떤 표준품셈 항목인가" 매핑은 업계 최대 미해결 난제(온톨로지 연구 정체, MDPI 2026이 LLM 실현 가능성 입증). 콘엑스(반자동)·Conpa(품셈 미정합)를 모두 추월하고, 디벨로퍼가 설계 전 단계에서 공사비를 받는 개산 모드는 어떤 적산 SW도 수지분석으로 연결하지 못함. 오차범위 명시("정직한 정확도")로 98% 류 검증 불가 주장과 차별화.
- **실현 가능성**: 중상 — LLM 인프라·verify-agent 보유. 조달청 표준공사코드 공공데이터 + KOSIS 공사비지수 API는 무료 연동. 단가 DB(한국물가정보)·실계약 공사비(하우빌드류)는 제휴 필요.

### 10. 필드 단위 Provenance + DAG 재계산 + 이벤트소싱 Audit Trail → 분 단위 Bank-Ready 리포트
- **근거**: 국내 프롭테크 중 필드 provenance UX 보유사 **0곳**(랜드북 포함). 글로벌 최고 사례(Power Apps)도 수락 후 출처 이력이 소멸 — 영구 audit trail은 공백. 이를 시나리오별 세후 IRR diff·법령 조문 근거와 묶은 bank-ready PDF 자동 생성은 Feasibly의 "$10,000·3일" 대비 "분 단위·구독가" 가격 파괴.
- **실현 가능성**: 높음 — verify-agent(검증)·bank_ready_report(산출물)·버전관리가 기존 자산. 필드 5상태 머신 + 의존성 DAG + 불변 로그 {이전값, 새값, 행위자, 근거, 시각}은 자체 폼 계층 구현으로 해결(기성 라이브러리 미내장이 오히려 진입장벽=해자).

### 우선순위 제언
- **즉시 (기존 자산 직결)**: #2 세후 IRR → #5 엔티티 옵티마이저 → #4 몬테카를로 → #10 provenance/리포트 (수지·신뢰 축 완성)
- **단기 (차별화 전선)**: #3 버전드 룰엔진 → #7 평면↔수지 루프 → #1 전주기 파이프라인 골격
- **중기 (해자 구축)**: #6 대화형 가설계 → #8 IFC/세움터 → #9 적산 사다리

---

## ⑥ 출처 목록

### 트랙 1 — AI 건축설계 자동화
- https://www.testfit.io/pricing
- https://aecmag.com/news/testfit-generative-design-targets-building-optimisation/
- https://www.autodesk.com/products/forma/overview
- https://adsknews.autodesk.com/en/news/autodesk-design-and-make-intelligence/
- https://www.snaptrude.com/pricing
- https://www.designboom.com/architecture/snaptrude-ai-generate-editable-3d-architecture-models-simple-text-descriptions-archdaily-10-10-2025/
- https://aecmag.com/bim/arcol-unleashed-bim-2-0/
- https://aecmag.com/ai/hypar-text-to-bim-and-beyond/
- https://hubspot.finch3d.com/pricing-4
- https://www.maket.ai/pricing
- https://arkdesign.ai/pricing/
- https://www.landbook.net/

### 트랙 2 — 수지분석·사업성 플랫폼
- https://deepblocks.com/
- https://deepblocks.com/blog/zoning-glossary/2019-1-29-financial-outputs-the-back-of-envelope/
- https://www.businesswire.com/news/home/20251202514806/en/Feasibly-Transforms-Real-Estate-Feasibility-Analysis-With-Multi-Agent-AI-Software
- https://www.altusgroup.com/solutions/argus-developer/
- https://www.altusgroup.com/solutions/argus-estatemaster/
- https://www.landbook.net/service/ai-analytics
- https://m.dnews.co.kr/m_home/view.jsp?idxno=202503102255455410537
- https://www.venturesquare.net/788840
- https://www.valueupmap.com/tech
- https://www.e-science.co.kr/news/articleView.html?idxno=111337
- https://www.nextunicorn.kr/content/f2242f229c489fd9
- https://www.drbuild.co.kr/board/boardNewsDetail?bd_no=147

### 트랙 3 — 웹 CAD/BIM 오픈소스
- https://github.com/ThatOpen/engine_web-ifc
- https://github.com/ThatOpen/engine_components/releases
- https://github.com/ThatOpen/engine_fragment
- https://thatopen.github.io/engine_web-ifc/docs/classes/ifc_schema.IFC4X3.IfcEnergyConversionDevice.html
- https://ocjs.org/docs/about
- https://github.com/xiangechen/chili3d
- https://github.com/mlightcad/cad-viewer
- https://github.com/Microsoft/maker.js/
- https://github.com/specklesystems/speckle-server
- https://speckle.systems/integrations/ifc/
- https://medium.com/toonsquare-tech/building-a-real-time-collaborative-editor-with-crdt-and-durable-objects-01fb69258197
- https://github.com/gdsestimating/dxf-parser

### 트랙 4 — AI 평면생성 연구
- https://arxiv.org/abs/2103.02574 (RPLAN/HouseGAN++ 계열)
- https://arxiv.org/abs/2004.13204 (Graph2Plan)
- https://github.com/HanHan55/Graph2plan
- https://dl.acm.org/doi/10.1145/3528223.3530135 (WallPlan)
- https://github.com/aminshabani/house_diffusion
- https://github.com/HangZhangZ/MaskPLAN
- https://arxiv.org/abs/2411.12279 (HouseTune/HouseLLM)
- https://arxiv.org/abs/2605.14117 (LLM-RLVR)
- https://arxiv.org/html/2509.00543v1 (Text-to-Layout)
- https://arxiv.org/abs/2604.04859 (FMLM)
- https://github.com/ChatHouseDiffusion/chathousediffusion
- https://www.buildit.co.kr/

### 트랙 5 — 적산·공사비 자동화
- https://www.rib-software.com/en/rib-costx/bim
- https://www.rib-software.com/en/rib-costx
- https://itcon.org/papers/2024_24-ITcon-Pishdad.pdf
- https://www.togal.ai/
- https://www.kreo.net/
- https://ddusul.com/ (콘엑스)
- https://conpa.ai/en
- https://xcost.me/bbs/board.php?bo_table=product&wr_id=5
- https://www.koreasoft.co.kr/m/pub/product/ems.asp
- https://m.dnews.co.kr/m_home/view.jsp?idxno=202604301909410880360 (건설공사비지수 동향)
- https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART001663662
- https://www.mdpi.com/2075-5309/16/3/485

### 트랙 6 — AI 자동입력·폼 워크플로 UX
- https://learn.microsoft.com/en-us/power-apps/user/form-filling-assistance
- https://carbondesignsystem.com/components/ai-label/usage/
- https://www.shapeof.ai/patterns/auto-fill
- https://www.notion.com/help/autofill
- https://support.airtable.com/docs/using-airtable-ai-in-fields
- https://docs.n8n.io/advanced-ai/human-in-the-loop-tools/
- https://blog.n8n.io/human-in-the-loop-automation/
- https://admin.salesforce.com/blog/2025/revolutionize-record-pages-ai-powered-agent-shortcuts-are-here
- https://docs.retool.com/forms/guides/fields
- https://fenrisd.com/property-insurance/
- https://www.landbook.net/service/ai-analytics
- https://macabacus.com/blog/improving-model-readability-with-color-formatting
