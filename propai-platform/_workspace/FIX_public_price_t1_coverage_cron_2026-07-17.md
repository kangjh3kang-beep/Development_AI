# FIX: T1 공공단가 분야 커버리지 확장 + 일일 자동 동기화 (2026-07-17)

## 배경 — 메인 워크트리 미커밋 초안의 완결 요청

메인 워크트리(`Development_AI/`, stale main)에 미커밋으로 남아있던 "G2B 가격동기화" 초안
(`g2b_price_sync_service.py` + `g2b_client.fetch_material_prices` + `/g2b/sync-prices` +
worker cron + 루트 라이브 스크립트 2개)의 완결을 요청받음.

## 초안 트리아지 — 그대로 커밋하면 안 되는 이유 (근본 결함 3건)

1. **T2 파괴적 덮어쓰기 (Critical)**: 초안은 조달청 단가를 내부 표준품셈 코드(RC-001/RC-004
   등)에 `ON CONFLICT (material_code) DO UPDATE`로 upsert → `material_code`에 UNIQUE 인덱스
   (`uq_material_unit_prices_code`, cost_tables_bootstrap)가 있으므로 **T2 표준품셈 시드 행을
   노무비=0·price_source='조달청 G2B'로 교체**한다. = ★기존 함정 "T1 노무=0→제비율 소실"의
   재발 + T2 원천 데이터 파괴. (올바른 통로는 별도 네임스페이스 PUB-* — 이미 존재)
2. **기존 T1 통로의 그림자 중복**: `public_price_ingest.py`(T1 주입·분해단가 정합가드·멱등
   upsert·정직 skip)와 `PublicPriceClient`가 이미 동일 API(PriceInfoService)를 커버.
   초안은 이를 모른 채 g2b_client에 유사 기능을 재구현(동명헬퍼 그림자 패턴).
3. **날조 오퍼레이션**: 초안의 `getPriceInfoListFcltyCmmnMtrilTotal`(종합)은 라이브 검증에서
   **HTTP 404 — 실존하지 않음**. (건축/기계설비/전기통신 3개는 실존 확인)

기타: 서비스가 계산한 조회기간(start_s/end_s)을 클라이언트에 전달하지 않는 dead code,
루트 `test_g2b_price*.py`는 pytest가 아닌 라이브 스크립트(수집 0개 테스트) 등.

## 정답 기준선과의 격차 → 완결 방향

정답 기준선 = 기존 `public_price_ingest`(T1 통로). 초안의 **진짜 갭 2개만** 그 통로에 흡수:

| 갭 | 완결 |
|---|---|
| 분야 커버리지(토목 1개뿐) | `PRICE_OPERATIONS` 4분야(토목/건축/기계설비/전기통신) — **2026-07-17 실키 라이브 검증(resultCode 00, 각 1건 호출)** 후 등록. 종합은 404라 미등록(무날조). 4분야 응답 필드 스키마 동일 확인(prdctClsfcNoNm/krnPrdctNm/unit/prce/mtrlcst/lbrcst/gnrlexpns) |
| 주기 동기화 부재(수동 라우트뿐) | arq cron `g2b_sync_public_prices` 매일 20:30 UTC(KST 05:30) — 21:00 낙찰갱신과 시차로 동일 API군 레이트리밋 경합 방지. 태스크는 `sync_public_material_prices`(g2b_sync_task.py) → `ingest_public_prices` 위임 |

부가: `ingest_public_prices(categories=...)` 파라미터(기본=등록 전 분야 순회, per_category
집계 반환, 미등록 분야 즉시 ValueError), 관리자 라우트 `categories` 파라미터(422 검증).

## 검증

- 단위테스트: test_public_price_client(+3) · test_public_price_ingest(+3, FakeClient 분야
  인지형 갱신) · test_unit_price_repository — **41 passed**
- 라이브: 4분야 오퍼레이션 실키 호출 resultCode 00 채증(건축 totalCount 10,749),
  Total 404 채증
- 배포 후 라이브검증 절차: `/api/v1/cost/admin/ingest-public-prices` (admin, body `{}`)
  → per_category 4분야 fetched>0·ingested≥1 확인 → `material_unit_prices`에서
  `material_code LIKE 'PUB-%'` 행의 price_source='표준시장단가 2026상' 확인

## 전역 전파방지 (패턴 스윕)

- 패턴: "이미 있는 공용 통로를 모르고 유사 기능을 다른 계층에 재구현 + 미검증 외부
  오퍼레이션명 등록". 이번 수정으로 가격정보 수집은 PublicPriceClient/-ingest 단일 통로로
  수렴(별도 그림자 클라이언트 초안 폐기). g2b_client에는 가격 관련 코드를 넣지 않음.
- 메인 워크트리의 초안 파일은 아카이브 후 제거 예정(본 PR 머지 시점) — 초안의
  SatongMultiMap.tsx·DESIGN.md 변경은 본 건과 무관한 별도 트랙(사통맵)으로 분리.

## 잔여/후속

- normalize_item의 분해단가(mtrlcst/lbrcst)는 여전히 전 분야에서 빈 문자열(총단가만 제공)
  — 분해 유입 시 T1 가드 자동 통과 설계는 기존 그대로(활성 전 R1 Q1 확인 필요).
- 초안이 의도했던 "품명 키워드→내부 자재코드 확장 매핑"(레미콘/철근/거푸집/방수/창호 외
  추가 공종)은 단가 SSOT 키 6종 확장과 함께 별도 설계 필요(현행 6종 유지).
