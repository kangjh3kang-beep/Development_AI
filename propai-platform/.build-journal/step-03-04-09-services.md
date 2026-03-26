# STEP 3+4+9 완료 보고서: AI 서비스 + 외부 API + 라우터

> **완료일**: 2026-03-18
> **담당**: Claude Code
> **상태**: 전체 구조 완료 (외부 API 키 연동 + 단위 테스트 필요)

---

## STEP 3: 핵심 AI 서비스 (12개 파일)

### 3-1. AVM/법규/세금/전세/조합
| 파일 | 핵심 기술 |
|------|----------|
| `avm_service.py` | XGBoost + MLflow + 공공 실거래가 |
| `regulation_service.py` | Qdrant RAG + Claude LLM |
| `tax_ai_service.py` | 규칙 엔진 + LLM 절세 시나리오 |
| `jeonse_risk_service.py` | 전세가율 분석 + LLM 리스크 평가 |
| `union_management_service.py` | 비례율법 분담금 + LLM 시나리오 |

### 3-2. 설계/BIM/이미지/탄소
| 파일 | 핵심 기술 |
|------|----------|
| `bim_ifc_service.py` | ifcopenshell + Three.js geometry |
| `floor_plan_image_service.py` | Replicate SDXL + MinIO |
| `design_ai_service.py` | Claude LLM SSE 스트리밍 보고서 |
| `carbon_calculation_service.py` | 건축자재 탄소 계수 + LLM 저감 방안 |

### 3-3. 드론/블록체인/에이전트
| 파일 | 핵심 기술 |
|------|----------|
| `drone_iot_service.py` | Roboflow YOLOv8 + MQTT(EMQX) |
| `blockchain_service.py` | Web3.py + Polygon Amoy + ABI |
| `agents/propai_orchestrator.py` | LangGraph 7단계 상태 머신 |

---

## STEP 4: 외부 API 통합 (10개 파일)

| 파일 | 대상 | 주요 용도 |
|------|------|----------|
| `base_client.py` | 공통 | Circuit Breaker, 재시도, 캐시, 메트릭 |
| `vworld_client.py` | V-World | 토지/건물 정보, 지오코딩 |
| `molit_client.py` | 국토교통부 | 실거래가, 공시지가 |
| `court_client.py` | 법원등기소 | 등기부등본, 근저당 확인 |
| `nice_client.py` | NICE | 신용평가 |
| `kepco_client.py` | 한국전력 | 전력 사용량 (탄소 산출) |
| `kma_client.py` | 기상청 | 기상 데이터 |
| `hug_client.py` | HUG | 전세보증보험 |
| `lh_client.py` | LH | 공공주택 |
| `roboflow_client.py` | Roboflow | 하자 탐지 |
| `replicate_client.py` | Replicate | SDXL 이미지 생성 |

---

## STEP 9: API v1 라우터 (9개 파일)

| 라우터 | 경로 | 주요 엔드포인트 |
|--------|------|----------------|
| `auth.py` | `/api/v1/auth` | login, refresh, me |
| `projects.py` | `/api/v1/projects` | CRUD |
| `avm.py` | `/api/v1/avm` | POST 시세 추정 |
| `regulation.py` | `/api/v1/regulation` | POST 법규 검토 |
| `tax.py` | `/api/v1/tax` | POST 세금 계산 |
| `design.py` | `/api/v1/design` | 평면도, BIM, SSE 보고서 |
| `drone.py` | `/api/v1/drone` | POST 점검 |
| `blockchain.py` | `/api/v1/blockchain` | POST 에스크로 |
| `agents.py` | `/api/v1/agents` | SSE 오케스트레이션 |

---

## 아키텍처 결정 사항

1. **서비스 계층 분리**: 라우터 → 서비스 → DB/외부API (3-tier)
2. **Circuit Breaker**: 5회 연속 실패 → OPEN, 60초 후 HALF_OPEN
3. **캐시 전략**: Redis TTL (공공 API: 24h, 기상: 1h, 지오코딩: 7d)
4. **SSE 스트리밍**: sse-starlette + StreamingReportEvent/AgentStepEvent
5. **ABI 연동**: `contracts/artifacts/PropAIEscrow.json` 단일 소스

---

## 다음 단계

- [ ] STEP 10: 테스트 구조 (unit/integration/load)
- [ ] 지원 트랙 W: arq 비동기 워커
- [ ] CoVe 벤치마크 테스트 파일 작성
