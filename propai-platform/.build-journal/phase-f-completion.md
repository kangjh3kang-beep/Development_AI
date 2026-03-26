# Phase F 완료 보고서

> 작성일: 2026-03-21
> 담당: Claude Code (백엔드)

---

## Phase F: v30.0 명세서 갭 해소 + 기능 고도화

### F-1: BIM Three.js 라우터 + IFC 자동 생성

- `GET /api/v1/bim/threejs/{project_id}` 엔드포인트 추가
- `POST /api/v1/bim/generate-ifc` 엔드포인트 추가
- `generate_ifc_from_design()` 메서드: ifcopenshell로 IFC 파일 자동 생성
  - IfcProject → IfcSite → IfcBuilding → 층별 IfcSlab + 4면 IfcWall
  - MinIO 업로드 + DB 저장

### F-2: 평면도 이미지 고도화 (ControlNet/DALL-E 3/Claude Vision)

- `_generate_image_with_controlnet()`: Replicate ControlNet img2img 참조 이미지 기반
- `_generate_image_dalle3_fallback()`: OpenAI DALL-E 3 폴백
- `_validate_with_claude_vision()`: Claude Vision 방 개수 검증
- `generate()` 폴백 체인: ControlNet → SDXL → DALL-E 3, Vision 검증 후 불일치 시 최대 3회 재생성

### F-3: AVM CTGAN 콜드스타트 합성 데이터

- `_generate_synthetic_comparables()`: 비교사례 3건 미만 시 CTGAN 합성 30건 생성
- 통계 분포 기반 폴백 (CTGAN 실패 시)
- `estimate()` 메서드에 콜드스타트 탐지 + 합성 보강 통합

### F-4: Evidently 데이터 드리프트 리포트

- `_generate_drift_report()`: Evidently DataDriftPreset 리포트 생성
- `run_retrain_avm()` 내 재학습 후 드리프트 감지 호출
- drift_detected 결과를 반환값에 포함

### F-5: v2 API 라우터 (auth, projects, design)

- `apps/api/routers/v2/` 디렉토리 생성 (auth.py, projects.py, design.py)
- v1 라우터를 래핑하여 v2 스키마 호환 (향후 브레이킹 변경 시 분기)
- main.py에 v2 라우터 등록: `/api/v2/auth`, `/api/v2/projects`, `/api/v2/design`

### F-6: MQTT 드론 구독자

- `apps/worker/tasks/mqtt_subscriber.py` 신규 생성
- `MQTTDroneSubscriber` 클래스: paho-mqtt 기반 MQTT 구독
- 토픽 `propai/drone/+/image` 구독 → arq 태스크 큐잉
- 워커 main.py startup/shutdown에 MQTT 연동

### F-7: Dockerfile (API 서비스)

- `apps/api/Dockerfile` 신규 생성
- Python 3.12-slim, non-root propai:1001
- HEALTHCHECK, uvicorn 4 workers
- 불필요한 도구 제거 (curl, wget)

### F-8: WebSocket 에이전트 진행률

- `@router.websocket("/analyze/ws/{project_id}")` 엔드포인트 추가
- JWT 토큰 인증 (WebSocket 메시지로 수신)
- 오케스트레이터 SSE → WebSocket JSON 브릿지
- 기존 SSE 엔드포인트 유지 (공존)

### F-9: 전세 서비스 등기부 조회 연동

- `_check_mortgage_priority()`: CourtClient 연동 근저당/압류 조회
- 선순위 근저당 + 전세금 합산 위험도 경고
- 소유권 이전 이력 확인 (3회 이상 시 경고)
- `analyze()` 메서드에 registry_number 파라미터 추가

---

## 테스트 현황

| 테스트 파일 | 테스트 수 | 검증 대상 |
|-----------|---------|----------|
| test_bim_threejs.py | 10 | Three.js 라우터 + IFC 생성 |
| test_floor_plan_advanced.py | 12 | ControlNet/DALL-E/Vision |
| test_avm_ctgan.py | 5 | CTGAN 콜드스타트 |
| test_v2_routers.py | 7 | v2 라우터 등록 |
| test_mqtt_subscriber.py | 9 | MQTT 구독자 구조 |
| test_websocket_agents.py | 7 | WebSocket 에이전트 |
| test_evidently_drift.py | 5 | Evidently 드리프트 |
| test_jeonse_court.py | 6 | 전세 등기부 조회 |
| test_dockerfile.py | 7 | Dockerfile 보안 |

---

## 품질 게이트

| 항목 | 결과 |
|-----|------|
| ruff | All checks passed |
| mypy | Success: 0 errors in 100 files |
| pytest | 701 passed, 3 skipped |

---

## 변경 요약

| 유형 | 수량 |
|-----|------|
| 신규 파일 | 13개 (v2 라우터 4, Dockerfile, mqtt_subscriber, 테스트 9) |
| 수정 파일 | 8개 (bim.py, bim_ifc_service.py, floor_plan_image_service.py, avm_service.py, mlops.py, main.py, agents.py, jeonse_risk_service.py) |
| 추가 테스트 | +67개 (634 → 701) |
