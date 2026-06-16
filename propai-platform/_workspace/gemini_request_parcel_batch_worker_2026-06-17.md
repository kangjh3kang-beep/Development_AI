# [제미나이 인프라트랙 업무요청] 대량 다필지 배치(parcel_batch) Celery 워커 운영화

## 1. 배경
부동산개발 플랫폼(PropAI)에 **대량 다필지 비동기 배치(F-Parcel ParcelBatchJob)** 를 구현·배포 완료했습니다. 구역(주소+반경/bbox/PNU목록)으로 수백~수천 필지를 한 번에 해석·집계합니다.
- API: `POST /api/v1/parcels/batch`(제출) · `GET /api/v1/parcels/batch/{job_id}`(폴링) · `POST .../cancel`
- 코어: `apps/api/app/foundation/parcel/`(contracts/region_normalizer/job_runner/aggregator/batch_service/job_store) + DB 3테이블(parcel_batch_job/batch_item_result/batch_aggregate, prod 적용완료)
- 라이브검증: 의정부동224 반경 300m→200필지, 500m→1000필지 해석·집계 정상

## 2. 문제(현재 한계)
현재 잡 실행은 **FastAPI BackgroundTasks(웹 프로세스 인프로세스)** 로 처리됩니다.
- 1000필지 처리에 ~2분 소요(VWorld 호출 1,000~2,000회), 웹 요청 처리와 자원 경합
- 웹 컨테이너 재시작/배포 시 진행 중 잡 유실 위험
- 동시 다발 대량 요청 시 웹 워커 포화 위험

## 3. 요청(인프라트랙 범위)
**`parcel_batch` 전용 Celery 워커를 운영 배포**해 주세요. 애플리케이션 코드는 이미 준비돼 있습니다:
- Celery 앱: `apps/api/app/tasks/celery_app.py` (브로커=Redis, `autodiscover_tasks(["app.tasks"])`)
- 태스크: `apps/api/app/tasks/parcel_batch_task.py` → `run_batch(job_id)` (queue=`parcel_batch`, `asyncio.run(BatchService(DbJobStore).run(job_id))`)

### 구체 작업
1. **워커 컨테이너/프로세스 기동**: 백엔드 A1(168.110.125.89)에 `celery -A app.tasks.celery_app worker -Q parcel_batch,celery --concurrency=N` 상시 가동(systemd 또는 docker-compose 서비스). 동시성 N은 VWorld 레이트리밋(권장 동시 5~10) 고려해 산정.
2. **Redis 브로커 확인**: `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`(기본 redis://localhost:6379) 가용성·영속(AOF) 점검. (현 /health에서 redis degraded 표기 건과 연계 확인 요망.)
3. **라우터 인큐 전환 협의**: 현재 라우터(`apps/api/app/routers/parcel_batch.py`)는 BackgroundTasks + Celery enqueue를 병행 시도합니다. 워커 가동 후 **Celery 경로 우선**이 되도록 라우터의 enqueue 분기를 확인/조정(이 1줄 조정은 제가 해도 됩니다 — 워커 준비되면 알려주세요).
4. **모니터링**: 워커 큐 적체/실패율/처리시간 메트릭(Flower 또는 Prometheus) 노출.
5. **스케일 가드**: 단일 잡 max_count=1000 캡 외에, 동시 잡 수·1일 처리량 상한 정책 제안.

## 4. 비범위(앱트랙=클로드 담당, 건드리지 마세요)
- 배치 비즈니스 로직(해석/집계/부분성/멱등/이상치/과금)·DB 스키마·API 계약·프론트(BulkParcelBatchPanel)는 완료·검증됨. 변경 불요.
- 과금: `service_fees.bulk_parcel_per_unit`(기본 0=무료, 관리자 설정 시 과금) 완료.

## 5. 수용 기준(DoD)
- `parcel_batch` 워커 상시 가동(재시작 자동복구)
- 1000필지 잡이 웹 프로세스 부하 없이 처리되고, 진행 중 배포에도 잡 유실 없음(워커가 처리)
- 단일 필지 동기 검색 SLA 무영향(경로 분리 INV-M1 유지)
- 큐 적체/실패 가시화

## 6. 참고
- 배포: 백엔드 A1 무중단 `bash ~/deploy.sh`(블루그린, /health 게이트). 워커는 별 프로세스라 deploy.sh와 별개 기동 필요.
- SSH키 `~/.oci.key`. 한국 리전 유지(공공데이터 국외IP 차단 회피).
- 관련 메모리: project_parcel_batch_foundation / project_scaling_infra / project_oracle_deploy