# 세션 기록 — 대량 다필지 + 입지분석 고도화 + 심의엔진 편입 (2026-06-16~17)

> 원칙: 모든 과정·결과·특이사항 기록·공유. 무목업·라이브검증·완결게이트.

---
## 🔴🔴 중요도 CRITICAL — 모두 반드시 공유·준수 🔴🔴

1. **[🔴 운영 재발위험] 서버 `.env`(gitignored) 인라인 주석 오염 → 전 백엔드 배포 마비.**
   - 증상: trust-infra 머지 이후 모든 blue-green 배포가 health 게이트서 막힘. 진짜 원인=서버 `~/Development_AI/propai-platform/.env`의 **40개 라인에 `# → fieldname` 인라인 주석 + 22개 값 앞뒤공백**(시크릿 export/오버레이 작업 부작용). `DATABASE_URL=...//postgres  # → ...`→DB명 깨짐(login 500·postgres unhealthy), `VWORLD_API_KEY= E98…`(선행공백)→"등록 안 된 인증키"(geocode 전멸).
   - 조치: .env 전 라인 주석/공백 정리(백업 `.env.bak*`) + Dockerfile.oracle `ENV PYTHONPATH=/app:/app/apps/api` 추가 + config.py 인라인주석 방어 validator.
   - **★재발방지(필수): secrets export 스크립트가 `.env`에 `# →` 주석을 다시 쓰면 즉시 재발. export는 반드시 주석 없는 `KEY=VALUE`만 쓰도록 보장(제미나이/시크릿 트랙 조율).**

2. **[🔴 보안] 마스터키 `SECRET_STORE_KEY`·`ENCRYPTION_KEY`는 env-only·평문 비노출.** export_scoped_secrets는 `_HARD_DENY`로 하드차단(--allow로도 export 불가). 절대 외부서비스/관리자화면/DB/로그 노출 금지.

3. **[🔴 배포] 백엔드·프론트 모두 SSH 수동(Oracle A1).** 백엔드 `bash ~/deploy.sh`(blue-green, 게이트 `curl localhost:NEW/health` 60×3s=180s, 부팅 정상 시 ~15초). 프론트 `bash ~/safe-deploy.sh`(sw CACHE_NAME 올림). GitHub push만으론 반영 안 됨.

4. **[🟠 정확성] 토지조서/대량필지=무목업·정직표기.** 동명이의 오매칭·동일평수는 ambiguous로 강등(가짜 확신 금지). 공동주택은 세대 대지지분 합 = 실토지면적 검증 필수.

---

> main HEAD=08f421d1+, 프론트 sw=v221+. 백엔드 A1 활성 healthy.

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

---
## 10. 공동주택 대지지분(대지권) 분석 + 토지지번검색 자동완성 (2026-06-17)

> 사용자 요구: 토지조서=실토지면적 확보 목적. 공동주택·다세대·집합상가 필지는 세대(동·호)에
> 대지지분 배정 → **Σ세대 대지지분 = 대지(필지)면적**이어야 정확한 토지조서. 건축물대장으로
> 호별 동·호·세대(전유)면적·대지지분 확보·반영, **실별 대지지분을 평으로 환산**, 토지조서에 실반영.
> 추가: 토지지번입력에 다음 주소검색처럼 **토지지번검색(자동완성)**.

### 도메인 메모(사용자 Q&A)
- 대지지분(대지권)이 생기는 건물 = **구분소유가 성립하는 집합건물**(공동주택 아파트·연립·다세대, 집합상가, 오피스텔). 「집합건물법」 적용.
- **비구분(일반)건물**(단독·다가구·근생 통건물)은 대지지분 개념 없음 → 필지면적 자체가 실토지면적.
- 단, 모든 집합건물에 대지권이 등기된 건 아님(대지권 미등기). **정확 대지권비율은 등기부 대지권등록부(유료)**. 건축물대장 전유면적으로는 비례 추정만 가능 → 정직 표기.

### 백엔드
- `building_registry_service.py`: `get_exclusive_units_by_pnu(pnu)` 신규 — getBrExposPubuseAreaInfo(전유공용면적)로 호별 **전유부만** 집계(공용 제외). `_parse_title_items`에 `plat_area_sqm`(platArea=대지면적) 추가.
- `land_share_service.py`(신규): 표제부 대지면적+전유부 → 호별 대지지분 **전유 비례(area-weighted)** 산정 + 평 환산(`PYEONG_SQM=3.305785`). plat_area 폴백(표제부→VWorld 토지특성). **검증 2분리**: `sum_match`(합계=정의상 성립, 정확성 증명 아님) + `count_match`(표제부 hhldCnt/hoCnt vs 전유부 호수 **방향성 교차검증** — 누락만 비신뢰, 근생 초과는 정상). `reliable=sum_match and count_match`.
- `vworld_service.py`: `search_address(query)` 신규 — VWorld 검색API(parcel→road) 후보 목록(주소·PNU·좌표). 키 prefix 로깅 제거(보안).
- `auto_zoning.py`: `POST /zoning/search`(자동완성), `POST /zoning/land-share`(pnu/address). try/except 정직 분기(raw 500 차단)+모듈 logger.
- `registry.py`: 토지조서 엑셀에 대지지분(㎡)·**대지지분(평)**·세대전유면적(㎡) 컬럼, LandRow 스키마에 exclusive_area_sqm/unit_label, import pick에 exclude(대지지분 우선·전유/평 제외), 푸터 스킵 '평' 제거(평창동 오스킵 방지).

### 프론트
- `LandShareModal.tsx`(신규): 호별 동·호·전유면적·지분율·**대지지분(㎡/평)** 표 + 요약(대지면적·세대수 전유부/표제부·전유합) + 검증배지(비례배분 완료 + count_note 교차검증) + "실토지면적으로 반영"/**"세대별 펼쳐 반영"**.
- `LandScheduleClient.tsx`: 행별 '대지지분' 버튼, `expandUnits`(부모 필지행을 세대별 행으로 위치보존 치환: 지번=건물명+동·호·면적=대지지분·지분=대지권비율%·전유면적·unit_label), '세대면적㎡' 컬럼 + 대지지분/세대면적 **평 환산 표기**, 집계에 전유면적 합.
- `GlobalAddressSearch.tsx`: 지번 직접입력 → **토지지번검색 자동완성**(디바운스 350ms·`searchSeq` stale 가드·후보 드롭다운·PNU 직결). useLandScheduleStore에 pnu/exclusive_area_sqm/unit_label.

### 코드리뷰 개선루프
- 1차 **4.1/5**(HIGH-1 modal pnu 미배선·HIGH-2 subscript 500위험·MED-1 검증 tautology·MED-4 자동완성 race) → 수정.
- 2차 **4.4/5**(평 상수 혼용·Excel '평' 푸터·키 prefix 로깅·count_tol 소규모 오경고) → 수정(평 상수 통일·푸터토큰·로깅제거·방향성 교차검증).
- 3차 재채점 진행. 단위테스트: 1000㎡·4세대(84/84/59/59)→Σ=1000.0·101호 88.846평, 누락4→3 reliable=False, 혼합5→6 True, 대규모100→99 True.
