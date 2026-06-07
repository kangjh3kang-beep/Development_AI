# 멀티테넌트 분양관리 SaaS — 검증된 구현기획 (2026-06-06)

갭분석(현 플랫폼 vs 제안) + 리서치(권위출처 교차검증) 종합.

## 0. 핵심 결론
- 제안 아키텍처의 **기능적 의도는 현 v62 분양ERP에 이미 ~75-80% 구현**(88개 실테이블·11모듈·WebSocket·동기 아웃박스·시행사 통합 모니터링 `/projection/summary`).
- **가장 큰 차이는 "인프라 격리모델"이고, 제안의 heavy infra 다수는 현 규모/인프라에 과설계(over-engineering)**.
- 정직한 권고: 제안 3요소를 다운그레이드·대체한다 ↓

## 1. 검증된 아키텍처 권고 (제안 일부 반대 — 근거 명시)
| 제안 | 권고 | 근거(출처) |
|------|------|-----------|
| schema-per-tenant(스키마 동적생성) | **❌→ RLS shared-schema + tenant_id** | schema-per-tenant는 수백 테넌트서 pg_catalog bloat·마이그레이션 N배·pgbouncer 붕괴(PlanetScale·Crunchy). RLS=수백만 테넌트, Supabase RLS-native, fail-closed 보안 |
| Kafka | **❌→ Redis Streams**(이미 보유) | 우리 규모(현장 수십~수백, <100M event/day) Kafka 운영부담만. Redis Streams consumer group으로 80% 커버 |
| 풀 CQRS(읽기Replica/쓰기 분산락 전면) | **△→ 부분**: 읽기Replica는 병목 실측시, 분산락은 **동호수 선점에만 국소** | 풀CQRS=YAGNI |
| 동호수 선점 | **✅ Redis 분산락+TTL+Lua(임시선점) + DB 낙관/UNIQUE(확정)** 하이브리드 | 좌석예약형 2025 베스트프랙티스(순수 낙관락=UX최악) |
| 서브도메인(siteA.4t8t.net) | **✅ 와일드카드DNS + 미들웨어 resolve**(코드 훅 이미 존재 deps_sales) | 표준. 격리는 DNS아닌 RLS에서 |
| Socket.io/SSE/알림톡 | **✅ 양방향=WS·단방향=SSE·미접속=알림톡**(Socket.io 별서버 불필요, FastAPI WS 보유) | |
| 2차인증 현장격리 | **✅** | 자금·계약 도메인 정당 |
| 블록체인 타임스탬프 audit | **✅ 우리 해시체인 원장 재사용** + 필요시 Merkle 외부앵커링 | 풀 온체인=과설계 |

★RLS 단서(필수): tenant_id 인덱스 + 정책함수 `(select ...)`래핑(행마다 재평가 방지) + CVE-2024-10976 대비 미들웨어 이중방어 + Postgres 패치최신.

## 2. 11모듈 현황(갭분석)
구현완료: 분양가·조직도(ltree 6단계)·수수료(9테이블)·방문데스크·시행사 통합모니터링. 무결성가드(1호1계약·다중계약·배분초과 적발) 강력.
부분: 세대배치도(선점 0충돌 DB보장 없음)·청약당첨(스키마만,추첨/가점엔진 미확인)·수납(기록·대사만,PG미연동)·중도금대출(기록만,DSR엔진 미확인)·전매신고(규제DB 자동연동 아님)·세금보증(메인 tax엔진과 분리)·AI예측(해시체인 sales 미결합).

## 3. 핵심 미구현/갭(우선순위)
1. ★**RLS 미ENABLE**(rls_generator 보유하나 미강제) = 보안갭. 격리가 app계층 필터에만 의존.
2. ★**v62 88테이블 Alembic 운영DB 실적용 보류**(메모리). "구현됨≠운영DB반영".
3. 서브도메인 와일드카드 실배선(코드 준비, 인프라 미배선).
4. 동기 아웃박스→arq 비동기 소비자 분리(emit_outbox는 유지).
5. **자금 실연동 부재**: 수납/대출이 "기록·대사만" → 가상계좌(헥토) webhook·펌뱅킹·HUG 실연동.
6. 청약홈 OpenAPI(경쟁률·당첨) 미연동, DSR 컴플라이언스 엔진, sales세금↔메인 세법엔진 통합.
7. in-memory WS → worker>1시 Redis Pub/Sub 백플레인.

## 4. 단계별 구현 로드맵(검증된)
- **Phase 0(선결·보안)**: RLS ENABLE+인덱스+이중방어. v62 마이그레이션 운영DB 실적용 결정.
- **Phase 1(동기화·시너지 핵심)**: 동호수 선점 동시성(Redis락+TTL+Lua+DB UNIQUE), 아웃박스→arq, 서브도메인 배선, 시행사 실시간 push(SSE/WS). 메인↔분양 데이터흐름(등기·개발계획→분양앱).
- **Phase 2(자금 실연동)**: 가상계좌 webhook 수납 자동대사, 중도금 LTV/DSR 엔진, 청약홈 OpenAPI.
- **Phase 3(고도화)**: 세법엔진 통합, HUG 추적, AI 분양속도/미분양 예측, 무결성 해시체인 결합.

## 5. 사용자 결정 5가지(선결)
1. RLS ENABLE 시점(보안갭 즉시 vs 통합검증 후) — schema-per-tenant 필요성 자체를 무력화.
2. 동호수 선점: 분산락 vs DB UNIQUE+FOR UPDATE 표준?
3. 자금 실연동(PG/가상계좌/HUG)을 이번 범위 포함? (최대 미구현영역)
4. sales 세금 ↔ 메인 세법엔진 통합 여부?
5. v62 88테이블 운영DB 실적용을 선결 마일스톤으로?

## 6. 혁신기능(리서치 12선 요약)
실시간 동호수 선점보드 / 청약 시뮬레이터(청약홈API) / 가상계좌 자동대사 / LTV-DSR 사전심사 / AI 분양가 책정(AVM+MOLIT) / 전매·실거래 자동화 / HUG 추적 / 무결성가드 해시체인 / 권한격리 비주얼라이저 / 방문데스크 실시간큐 / 수수료 자동정산 / AI 분양속도 예측.

## 출처(핵심)
PlanetScale·Crunchy(schema-per-tenant 한계), AWS/Supabase(RLS), Redis Streams vs Kafka(JusDB), 좌석예약 분산락(DevelopersVoice), 청약홈 OpenAPI(data.go.kr 15098547), 헥토 가상계좌, CVE-2024-10976.
