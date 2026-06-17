# 심의분석 엔진 — 운영 배포(인프라 상시 가동)

코드/배선은 완료됐고, 아래는 **인프라를 상시 가동**하는 방법이다. 각 어댑터는 인프라 미가동 시
graceful 폴백(mock/eager/결손 표면화)하므로, 하나씩 켜면 자동으로 live로 격상된다.

## 1. 비밀 키 주입(1회 + 갱신 시)
플랫폼(trust_infra)에서 스코프 export → 엔진 `.env.secrets` 생성. 관리자 키 갱신 시 재실행.
```
cd <trust_infra>/propai-platform/apps/api
.venv/bin/python scripts/export_scoped_secrets.py \
  --target <propai-review>/.env.secrets --with-db
```
검증: `curl localhost:8801/api/v1/doctor` → 각 어댑터 live 확인.

## 2. 엔진(FastAPI) 상시 가동
```
ops/run_engine.sh            # 포그라운드
```
systemd 유닛 예시(`/etc/systemd/system/propai-engine.service`):
```ini
[Unit]
Description=PropAI Review Engine
After=network.target postgresql.service redis.service
[Service]
User=kangjh3kang
WorkingDirectory=/home/kangjh3kang/My_Projects/propai-review
ExecStart=/home/kangjh3kang/My_Projects/propai-review/ops/run_engine.sh
Restart=always
[Install]
WantedBy=multi-user.target
```

## 3. 비동기 워커(Celery) 상시 가동 — 진짜 비동기
redis(broker) 가동 필요. `CELERY_TASK_ALWAYS_EAGER=false` 시 redis 큐→워커 처리.
```
ops/run_worker.sh            # 포그라운드(상시는 systemd)
```
systemd 유닛(`propai-worker.service`): ExecStart를 `ops/run_worker.sh`로. Restart=always.
검증: `POST /api/v1/analyze/async` → task_id → `GET /api/v1/analyze/task/{id}`로 결과 폴링.

## 4. 벡터검색(Qdrant) 상시 가동 — 영속 유사사례
`QDRANT_URL` 미설정=in-memory mock, `:memory:`=임베디드(비영속), `http://host:6333`=실 서버(영속).
실 서버:
```
docker run -p 6333:6333 -v ~/qdrant_storage:/qdrant/storage qdrant/qdrant   # Docker
# 또는 바이너리: https://github.com/qdrant/qdrant/releases → ./qdrant
```
그 후 엔진 `.env`에 `QDRANT_URL=http://localhost:6333`. PrecedentSearch가 자동으로 실 Qdrant 사용.

## 5. 의미 임베더(OpenAI) — 유사사례 의미검색
`.env`에 `EMBEDDER=openai`(+ `.env.secrets`의 OPENAI_API_KEY) → 의미 임베딩. 미설정 시 해시 폴백.

## 6. 교차검증 출처(실연동 상태)
| 출처 | 키 | 상태 |
|---|---|---|
| 국가법령정보 law.go.kr | MOLEG_API_KEY(OC) | ✅ 실 200 |
| 국토부 건축물대장 | MOLIT_API_KEY(serviceKey, 1613000) | ✅ 실 200 |
| 국토부 공시지가(1611000) | MOLIT_API_KEY | ⚠️ data.go.kr 활용신청 필요(현재 500) |
| VWORLD 관할/용도지역 | VWORLD_API_KEY | ✅ 실 200 |

## 가동 우선순위(권장)
redis(워커) → Qdrant(영속 검색) → 공시지가 활용신청. 각각 독립적으로 켜도 나머지에 영향 없음.
