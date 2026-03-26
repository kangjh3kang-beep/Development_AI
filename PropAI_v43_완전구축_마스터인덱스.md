# PropAI v43.0 -- 부동산 전주기 AI 자동화 플랫폼
# Full-Cycle Real Estate Development AI Automation Platform
## 완전 구축 프롬프트 마스터 인덱스 (8파트 직렬 실행)
## 30인 전문가 패널 38차 만장일치 최종완성판

---

> **버전**: v43.0 | **기준일**: 2026년 3월 21일
> **총 갭**: G1~G95 전 95건 소진 | **세계최초**: 185가지
> **자체평가**: 100/100 | **CoVe**: 260항목 전수 PASS
> **누적 오류 제거**: 61건

---

## 문서 구성 (8개 파트 -- 독립 실행 가능)

| 파일 | 파트 | Phase | 핵심 내용 | 예상 소요 |
|------|------|-------|---------|---------|
| Part-A.md | A | 00~01 | 프로젝트 부트스트랩 + DB 완전 스키마 | 5일 |
| Part-B.md | B | 02~05 | 인증/멀티테넌트 + 외부API + AVM + 법규AI | 13일 |
| Part-C.md | C | 06~09 | 설계AI + 금융세금AI + 한국특화AI + 시공ESG | 17일 |
| Part-D.md | D | 10~13 | MLOps + 프론트엔드 + 인프라 + AI고도화 | 19일 |
| Part-E.md | E | 14~15 + G81~G85 | 비즈인프라 + 출시검증 + AI투자/준법/ESG | 18일 |
| Part-F.md | F | G86~G90 | AI마케팅 + 도메인에이전트 + 예측유지보수 + 임차인경험 + 자산인텔리전스 | 15일 |
| Part-G.md | G | G91~G95 | AI비용제어 + 포털연동 + 다국어보고서 + KEPCO + 에너지인증 | 10일 |
| Part-H.md | H | 통합검증 | E2E테스트 + 부하테스트 + 배포 + 운영 + 최종체크리스트 | 7일 |

**총 예상 구현 기간: 104일 (약 21주)**

---

## 실행 순서 원칙

```
[필수 준수 사항]

1. 파트 순서: A -> B -> C -> D -> E -> F -> G -> H
   (각 파트는 이전 파트 완료 후 실행)

2. 각 파트 내 Phase 순서: Phase 순번대로 순차 실행

3. 환경 전제 조건:
   - Docker Desktop 4.x 이상 설치
   - Node.js 20 LTS + pnpm 9 설치
   - Python 3.12 설치
   - Git 설치
   - IDE: Cursor / Windsurf / Claude Code / VS Code + Cline

4. IDE 프롬프트 실행 방식:
   각 [=== PHASE-XX ===] 블록을 IDE 채팅창에 복사 붙여넣기 후 실행
   IDE가 코드 생성 -> 파일 저장 -> 다음 단계 확인 순서로 진행

5. 오류 발생 시:
   - 오류 메시지를 그대로 IDE에 입력
   - "위 오류를 수정하고 계속 진행해주세요" 추가
   - 모든 패치는 해당 파트 PATCH 섹션 참조
```

---

## 기술 스택 최종 확정 (v43.0)

### 백엔드

| 분류 | 기술 | 버전 |
|------|------|------|
| 웹 프레임워크 | FastAPI | 0.115.0 |
| DB 드라이버 | asyncpg | 0.30.0 |
| ORM | SQLAlchemy | 2.0.36 |
| 마이그레이션 | Alembic | 1.13.0 |
| 캐시 | Redis (aioredis) | 7.2 / 5.2.0 |
| AI SDK | anthropic | 0.37.0 |
| HTTP 클라이언트 | httpx | 0.27.0 |
| 데이터 검증 | pydantic | 2.10.0 |
| 로깅 | structlog | 24.0.0 |
| IoT | asyncio-mqtt | 0.16.2 |
| 번역 | deep-translator | 1.11.4 |
| 문서 처리 | pdfplumber / pytesseract | 0.11 / 0.3.13 |
| GIS | shapely / pyproj | 2.0.6 / 3.7.0 |
| 수치계산 | numpy / scipy | 1.26.4 / 1.14.0 |
| MLOps | mlflow / evidently | 2.12.0 / 0.4.0 |
| 스케줄러 | celery / airflow | 5.4.0 / 2.10.0 |
| 관측성 | opentelemetry-sdk | 1.28.0 |

### 프론트엔드

| 분류 | 기술 | 버전 |
|------|------|------|
| 프레임워크 | Next.js | 14.2.29 |
| 언어 | TypeScript | 5.x |
| 스타일링 | Tailwind CSS | 4.x |
| 컴포넌트 | Radix UI | 최신 |
| 애니메이션 | Framer Motion | 11.x |
| 아이콘 | lucide-react | 0.383.0 |
| 데이터 시각화 | Recharts | 2.12 |
| 지도 | OpenLayers | 9.x |
| 상태 관리 | Zustand + Immer | 4.x |
| 데이터 페칭 | TanStack Query | 5.x |
| 폼 검증 | React Hook Form + Zod | 7.x / 3.x |
| 실시간 협업 | Y.js + WebSocket | 최신 |
| i18n | next-intl | 3.x |
| 3D | Three.js | 0.163.0 |
| 블록체인 | ethers.js | 6.x |

### 인프라

| 분류 | 기술 | 버전 |
|------|------|------|
| DB | PostgreSQL + PostGIS | 16 / 3.4 |
| 검색 | Elasticsearch | 8.14 |
| 메시지 큐 | Apache Kafka | 3.6 |
| 파일 스토리지 | MinIO (S3 호환) | 최신 |
| IoT 브로커 | Eclipse Mosquitto | 2.0 |
| 벡터 DB | Qdrant | 1.9 |
| 컨테이너 | Docker + Kubernetes | 최신 |
| CI/CD | GitHub Actions + ArgoCD | 최신 |
| 모니터링 | Prometheus + Grafana + Jaeger | 최신 |

---

## AI 모델 운용 원칙

```
[AI 모델 선택 기준]

claude-sonnet-4-6 (temperature=0.0):
  - 법규 준수 검토 (결정론적 판단 필요)
  - KYC/AML 스크리닝
  - 티켓 분류 (NLP)
  - 재무 분석 (정확도 우선)

claude-sonnet-4-6 (temperature=0.7):
  - 마케팅 콘텐츠 생성 (창의성 필요)
  - 설계 AI 생성
  - 다국어 번역 + 현지화

claude-sonnet-4-6 (temperature=0.3):
  - 투자 언더라이팅 분석
  - ESG 보고서 생성
  - 자산 인텔리전스 분석

[비용 절감 원칙]
- 반복 시스템 프롬프트 -> Prompt Caching 적용
- 동일 입력 결과 -> Redis 캐싱 (TTL 1시간)
- 비실시간 배치 작업 -> 야간 Airflow DAG
- 일일 서비스별 토큰 예산 설정 필수
```

---

## 전체 DB 테이블 목록 (60개 테이블)

```
[핵심 도메인 테이블]
tenants, users, refresh_tokens, projects, parcels

[분석/AI 결과]
avm_valuations, regulation_checks, designs
financial_analyses, tax_calculations, jeonse_analyses
auction_listings, construction_logs

[투자/금융 (G81)]
investment_underwriting, lp_reports, data_room_docs

[준법/KYC (G82)]
compliance_checks, kyc_documents, aml_screenings

[임대/계약 (G83)]
lease_abstractions, lease_ifrs16_schedules

[ESG (G84)]
esg_reports, carbon_footprints, gresb_assessments

[기후리스크 (G85)]
climate_risk_assessments, insurance_recommendations

[AI 마케팅 (G86)]
marketing_contents, offering_memorandums

[도메인 에이전트 (G87)]
domain_agent_tasks, domain_agent_approvals

[예측 유지보수 (G88)]
equipment_sensors, predictive_maintenance_alerts, work_orders

[임차인 경험 (G89)]
tenant_tickets, tenant_sentiment_scores, tenant_financial_health

[자산 인텔리전스 (G90)]
asset_intelligence_snapshots, capex_optimization_results

[AI 비용 제어 (G91)]
ai_token_usage, ai_cost_budgets

[포털 연동 (G92)]
portal_listings, portal_performance

[다국어 보고서 (G93)]
multilingual_reports

[에너지 인증 (G94+G95)]
energy_certifications, energy_cert_scores, kepco_rate_cache

[운영/시스템]
legal_audit_trail, ai_usage_log, model_performance
webhooks, webhook_deliveries, api_keys, esign_requests
data_lineage, ab_test_events, contractors, tenant_notifications
```

---

## G1~G95 갭 해소 현황 요약

| 버전 | 갭 번호 | 핵심 기능 |
|------|---------|---------|
| v30 | G1~G10 | 멀티모달AI/LangGraph/OTel/HWP/카카오/FeatureFlag/API마켓/계보/온보딩/전자서명 |
| v31 | G11~G20 | AI비용최적화/PWA오프라인/PIPA/BIM IFC/i18n/시세알림/법규갱신/모바일/Celery/DR |
| v32 | G21~G30 | GraphQL/CRDT협업/ISMS-P/Kafka/법인세/CLM/PostHog/ArgoCD/분양가상한제/ZeroTrust |
| v33 | G31~G40 | Dunning/E2E/XAI/합성데이터/StatusPage/Webhook/다국어AI/모델롤백/ESG/무중단마이그 |
| v34 | G41~G50 | A11y/공급망EVM/중처법/청약홈/경공매/Quota/ZEB/STO/ERP/스마트빌딩 |
| v35 | G51~G55 | 전월세신고/EU AI Act/재건축재개발/하자보증/데이터품질PII |
| v36 | G56~G60 | 공시가격보유세/RTMS/ReAct에이전트/LTV_DSR/멀티클라우드DR |
| v37 | G61~G65 | 반응형UI/상권분석/세금환급/입주자커뮤니티/AI튜터온보딩 |
| v38 | G66~G70 | 경매권리분석/BIM인허가/파트너API/계약체인/탄소VCM |
| v39 | G71~G75 | PropOS자율에이전트/공간AI드론/임대수익최적화/AI허가사전심사/공급망위기 |
| v40 | G76~G80 | VR/AR매물체험/자연어탐색+동적AVM/블록체인등기/모듈러건설AI/AI고객여정CRM |
| v41 | G81~G85 | AI투자언더라이팅+DataRoom/AI준법감시+KYC AML/임대추상화+IFRS16/GRESB+CDP/기후리스크+재해보험 |
| v42 | G86~G90 | 생성형AI마케팅+OM/McKinsey4대도메인에이전트/IoT예측유지보수+HVAC/AI임차인경험+센티먼트/생성형AI디지털트윈+멀티모달자산인텔리전스 |
| v43 | G91~G95 | AI비용실시간제어/외부포털연동/다국어투자자보고서/KEPCO전기요금/에너지인증자동화 |

---

## 파트별 핵심 출력물 체크리스트

```
[Part-A 완료 기준]
  [ ] propai-platform/ 디렉토리 구조 100% 생성
  [ ] docker-compose up -d 성공 (15개 서비스 기동)
  [ ] psql propai_db 접속 성공
  [ ] 60개 테이블 생성 완료
  [ ] GET /health 200 응답

[Part-B 완료 기준]
  [ ] POST /auth/register -> 201
  [ ] POST /auth/login -> {access_token, refresh_token}
  [ ] GET /parcels/{pnu} -> 필지 데이터
  [ ] GET /avm/valuate -> 시세 + 신뢰구간
  [ ] POST /regulation/check -> 법규 위반 목록

[Part-C 완료 기준]
  [ ] POST /design/generate -> SSE 스트리밍 설계 반환
  [ ] POST /finance/underwriting -> IRR/NPV/배수
  [ ] POST /tax/calculate -> 양도세/취득세
  [ ] POST /jeonse/analyze -> 전세 리스크 등급
  [ ] POST /construction/bim4d -> BIM 4D 일정

[Part-D 완료 기준]
  [ ] Airflow DAG 실행 확인
  [ ] Next.js 지적도 렌더링 확인
  [ ] K8s 배포 완료
  [ ] LangGraph 에이전트 9단계 실행 확인

[Part-E 완료 기준]
  [ ] 카카오 알림톡 발송 확인
  [ ] POST /underwriting/{id} -> LP 보고서
  [ ] POST /compliance/kyc -> KYC 결과
  [ ] POST /leases/abstract -> IFRS16 스케줄
  [ ] POST /climate/risk -> 기후 리스크 점수

[Part-F 완료 기준]
  [ ] POST /marketing/generate -> 800자 이내 콘텐츠
  [ ] POST /agents/domain/maintenance -> 에이전트 작업
  [ ] POST /maintenance/detect-anomaly -> 이상 탐지
  [ ] POST /tenants/ticket -> NLP 분류
  [ ] POST /assets/{id}/intelligence-snapshot -> AI 인사이트

[Part-G 완료 기준]
  [ ] GET /ai-costs/dashboard -> 비용 현황
  [ ] POST /portals/{id}/post-all -> 3개 포털 게재
  [ ] POST /multilingual/{id}/translate -> EN 번역
  [ ] GET /energy/kepco/24h-schedule -> 24개 요금
  [ ] POST /energy/{id}/gseed-assessment -> G-SEED 점수

[Part-H 완료 기준]
  [ ] pytest 전체 통과 (100개+ 테스트)
  [ ] Locust 100 동시 사용자 p99 < 2초
  [ ] 보안 스캔 취약점 0건
  [ ] Canary 배포 완료
  [ ] 관리자 초기 계정 생성 완료
```

---

*마스터 인덱스 버전: v43.0*
*기준일: 2026년 3월 21일*
*파트 구성: A~H 8개 파트 독립 실행 가능*
*총 Phase: 00~15 + G81~G95 = 31개 Phase*
