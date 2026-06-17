# 세션 기록 — 대량 다필지 + 입지분석 고도화 + 심의엔진 편입 (2026-06-16~17)

> 원칙: 모든 과정·결과·특이사항 기록·공유. 무목업·라이브검증·완결게이트. main HEAD=08f421d1, 프론트 sw=v221.

## 0. 한눈에
- **대량 다필지(F-Parcel) 전구간**(Wave 0~5) + **전 플랫폼 주소입력 다필지+엑셀+지번직접검색 전환** + **입지분석 고도화(Kakao Local POI·통합점수·실소요시간·공원)** + **버그 2건 근본수정** + **trust-infra 9커밋 머지** + **심의분석엔진 모노레포 편입**.
- 전부 origin/main 푸시·배포. 백엔드 A1(168.110.125.89) blue-green, 프론트 A1(158.179.174.207) sw v221.

## 1. F-Parcel 대량 다필지 배치 파운데이션
- 백엔드 `apps/api/app/foundation/parcel/`(contracts/region_normalizer/job_runner/aggregator/batch_service/job_store) + DB 3테이블(parcel_batch_job/batch_item_result/batch_aggregate, **prod 적용완료**) + 라우터 `/api/v1/parcels/batch`(submit/poll/cancel) + Celery 태스크.
- 불변식 INV-M1~M5(경로분리·부분성1급·스냅샷·완결성·집계보류). pytest 13 passed.
- 버그수정: DbJobStore flush 선행(FK위반)·region 멱등·bbox PNU 중복제거(완결성 고착)·폴링 종료조건(terminal PARTIAL)·submit 정규화 run 이전(20s→0.9s)·Celery enqueue env게이트(브로커 블록).
- 커밋: b30327c4·6386886f·13af97a5·7e85b397·017b3e33·8b958a84·ca8124b2.

## 2. 대량필지 웨이브(전 플랫폼 확장)
- **Wave0** 병목: `vworld.get_parcel_by_pnu` 프로세스 캐시 + `merge_parcels_gis_union` 동시성 gather (f872436b).
- **Wave1** 공통바 multi/엑셀 + 인허가AI(1c2c49aa). **Wave2** 종합·수익성 multi+통합카드(7e15b2ed).
- **Wave3** VWorld 레이트리밋 재시도(백오프)+엑셀 동시성(dcbed1e5).
- **Wave4a** 대량 구역 일괄분석 패널 `BulkParcelBatchPanel`(300a885b). **Wave4b** 주소+반경 구역선택+미리보기지도(733d20c2·26e07a50).
- **Wave5** 신뢰루프 면적 이상치 플래그(f64a2127) + 다필지 과금게이트 `bulk_parcel_per_unit`(기본0=무료, bfc89a0d).
- **전면 교체**: `ProjectAddressInput`(14개 워크스페이스) 항상 다필지 UI(fab0b2f5) + 다필지 안내 헤더(ea9493e4).
- **지번 직접검색(VWorld)**: `POST /zoning/geocode` + GlobalAddressSearch '📍 지번 직접입력' 행 — Daum 미검색 지번·산·농지 대응(55e8d5f4). 라이브: "의정부동 224"·"상도동 산65" 해석 OK.

## 3. 입지분석 고도화 (Kakao Local 기반)
- **판단**: Daum 우편번호 검색은 입지분석 부적합(주소 선택기). **Kakao Local 장소 API**가 인프라 조사에 효과적. 최적=VWorld(좌표·규제)+Kakao Local(POI)+공공데이터(인구·상권)+거리감쇠 점수화.
- `KakaoLocalService`: 좌표 반경 카테고리 13종(지하철·학교·학원·병원·약국·마트·편의점·은행·공공기관·문화·관광·음식·카페) + 공원(키워드) + 실소요시간(Mobility 자동차).
- `POST /site-score/poi-infra`: 주소→VWorld 좌표→POI 인벤토리+거리감쇠 접근성점수, context 제공 시 **통합 입지점수**(POI 55%+site_score 45%).
- `SiteInfraPoiCard`(종합분석 패널). 라이브: 강남 역삼동 통합 91.1·POI 93.6·역삼역 차량 1.8분·공원 21개·병원 669(29m) 등.
- 커밋: 2d8bbd96·752d406e·9609437f·90600e9d.

## 4. 버그 근본수정 — 새 입력 정합성(SSOT)
- **v220**(0a4b1e1f): 엑셀 업로드 시 이전 검색주소 잔류 — `handleExcelUpload`가 분석 미재실행+store 미갱신+업로드를 뒤에 append. → 업로드 필지 앞배치 + `updateSiteAnalysis`+`triggerComprehensiveAnalysis` 재실행.
- **v221**(61db10cf): 종합분석·수익성 패널이 주소 변경 시 이전 result/추천 미무효화. → 주소 변경 시 stale 결과 무효화(새 주소엔 '분석 시작' 프롬프트).

## 5. trust-infra 9커밋 머지(다른 클로드 작업)
- 시크릿 export 스크립트(`export_scoped_secrets.py`, `_HARD_DENY`로 SECRET_STORE_KEY·ENCRYPTION_KEY 하드차단·평문미노출·0600) + 심의분석 라이브 콘솔·비전배너. 보안검토 통과·머지·프론트배포(v219, 640efaf3).

## 6. 심의분석엔진 모노레포 편입 (옵션 c)
- 별도 repo(리모트 미설정) propai-review → `propai-platform/services/deliberation-review/`(08f421d1).
- **소스 327파일만**(시크릿 .env/.env.secrets/.venv/.git/캐시 제외, 스테이징 시크릿 0). 독립 마이크로서비스(DB review 스키마)·플랫폼 빌드 미포함(co-locate). **향후 심의엔진 작업은 이 경로에서**(원본은 사용자 보관).

## 7. 제미나이 인프라트랙
- 요청서 `_workspace/gemini_request_parcel_batch_worker_2026-06-17.md`. 제미나이 celery+flower deps 추가(3f81dbec).
- **대기**: parcel_batch 전용 Celery 워커 운영 → 준비 시 `PARCEL_BATCH_USE_CELERY=1` 컷오버.

## 8. 미해결·특이사항(정직 고지)
- **백엔드 배포 게이트 슬로부팅**: deploy.sh health 게이트(신 컨테이너 localhost/health 180s)에서 trust-infra 머지 배포가 타임아웃 중단. **prod(8001) healthy·모든 기능 라이브**, 머지 백엔드분은 유틸 스크립트(런타임 무관)뿐이라 기능영향 0. 게이트 윈도/부팅시간 = 제미나이 인프라 트랙.
- **헤드리스 agent-browser**: React 제어입력 onChange/제출 클릭 발화 불가(테스트 하네스 한계). 데이터경로는 브라우저 컨텍스트로 검증, 일부 시각 스크린샷 미캡처.
- **공공데이터(학교알리미/의료)**: Kakao Local이 이미 개수 제공 → 보강은 선택(활성화·쿼터 이슈). 공원은 키워드로 보강 완료.
- **Kakao Local/Mobility 쿼터**: 대량 사용 시 일한도 모니터링 권장.

## 9. 배포·검증 상태
- origin/main `08f421d1`. 프론트 sw `propai-v221-stale-invalidation`. 백엔드 A1 활성 8001 healthy(/health 200).
- 라이브검증: parcels/batch(200/1000필지)·geocode·poi-infra(통합91.1)·상도동 geocode 전부 OK.
