# 인수인계 — 조례 경사도 완결 · MOLEG 프로비저닝 · 파서 실버그 (2026-07-03)

> 세션 ID: 7546d046 · 작성: Claude Opus 4.8 · 대상: 다음 세션
> 한 줄: **자연녹지/임야 개발행위허가 "조례 경사도" 검토가 전량 폴백되던 근본원인(프로비저닝 2관문 + T2 파서 실버그 2건)을 추적·수정해 용인시 17.5도가 end-to-end 라이브로 부지분석에 도달**시켰다.

---

## 1) 지금 상태 (전부 배포·라이브 검증 완료)

- **origin/main = `31212cc9`** (PR#169). 프로드 api=`propai-platform_api_1` healthy, web=200/api=200.
- **조례 경사도 라이브 작동**: 용인시 임야 부지 종합분석 → `special_parcel.forest_preliminary_assessment.slope.criteria_deg = 17.5`(국가기준 25도 아님), `criteria_source="용인시 도시계획 조례(개발행위허가 경사도, verified=api_parsed)"`. 게이트(developability=NEEDS_OFFICIAL_SURVEY) 불변.
- **검증 커맨드(재현용)**: 프로드 api 컨테이너에서
  `resolve_slope_criteria("용인시", force_refresh=True)` → `{slope_deg:17.5, all_values_deg:[17.5,20.0], verified:"api_parsed"}`.

### 이번 세션 머지된 PR (origin/main)
| PR | 커밋 | 내용 |
|----|------|------|
| #164 | 320f755e | 다필지 통합면적 서버권위 SSOT(F4) |
| #165 | 5757ddce | ★링크 클릭 이동불가 근본수정(sw.js RSC network-only v377) |
| #166 | 4d0096f7 | #162 특이토지 심층검토(경사도·임목·부담금·조문11)+조문정정 |
| #168 | cee62bbc | T2/T3 dead-path 배선(조례경사도·임목축적→종합분석) |
| #169 | 31212cc9 | ★조례경사도 파서 실버그 2건 정정(자치법규ID·평균경사도 파서) |

---

## 2) MOLEG(법제처 law.go.kr) 프로비저닝 — ★영구 기억할 것

조례 경사도/용적률의 실시간 법제처 조회는 **2개 관문이 모두 충족돼야** 동작한다:

1. **프로드 .env에 `MOLEG_API_KEY`** — 이번에 클린 동기화 완료(값 10자, `k3…f3`). `.env`는 gitignore라 배포 전파 안 됨 → 프로드는 별도 .env. **로컬 .env(`propai-platform/.env` 114행)엔 인라인 주석 오염**(`MOLEG_API_KEY=<10자키> # …(국가법령정보센터)`) — 진짜 키는 앞 10자.
2. **법제처 OpenAPI 서버 IP/도메인 등록** — open.law.go.kr(국가법령정보 공동활용) 마이페이지에 프로드 egress IP `158.179.174.207` 등록 완료(사용자 수행). 미등록 시 어떤 OC로도 `"사용자 정보 검증 실패 — 서버 IP/도메인 등록 요망"` 반환(카카오 "ip mismatched"와 동일). ★프로드 IP 변경 시 재등록 필요.

- **주의**: `apps/api/.env`에 MOLEG 더미키(`dum…key`, 19자)가 있어 config가 CWD=apps/api면 더미를 로드(로컬 shadowing). 프로드엔 apps/api/.env 없음(안전). 참고 [[project_g2b_env_key_loading]].
- **법제처 API는 무료 쿼터/불안정** — 단시간 다수 호출 시 `"필수입력요소 검증 실패"`/`"IP 검증 실패"`를 상반되게 반환. 디버깅 시 **호출 간격을 둘 것**(레이트리밋).

---

## 3) ★배포 사고 교훈 (반드시 준수)

- **프로드 docker-compose는 v1** → BuildKit 이미지 recreate 시 `KeyError: 'ContainerConfig'` 버그. **수동 `docker-compose up -d --force-recreate` 절대 금지** — 옛 컨테이너 Exited·신규 Created로 멈춰 **api 다운(502)**. 이번 세션 2회 outage 발생·복구.
- **api 재기동/env리로드는 오직 `scripts/safe-deploy.sh api main`** (블루그린·BUILDKIT=0 빌드·헬스게이트·자동롤백). safe-deploy는 "옛 컨테이너 선제거 후 fresh-create"로 v1 버그를 우회한다.
- **컨테이너명 정규성 필수**: safe-deploy의 선제거는 정규명 `propai-platform_api_1`을 stop/rm한다. 수동 force-recreate가 `<hash>_propai-platform_api_1`로 이름을 망가뜨리면 선제거가 헛쳐 recreate로 빠져 실패한다. 복구법: `docker rename <hash>_propai-platform_api_1 propai-platform_api_1`(무중단) 후 safe-deploy 재실행.
- 응급 복구: 정규명 컨테이너가 Exited(0)면 `docker start propai-platform_api_1`로 즉시 서비스 복원(구 env).
- 참고 [[project_a1_safe_deploy]] [[project_oracle_deploy]].

---

## 4) 이번에 수정한 T2 파서 실버그 2건 (PR#169, `ordinance_service.py`)

라이브 그라운드 트루스(용인시 조례 실데이터)로 확정:

1. **`_parse_ordin_id`** — 자치법규(target=ordin) 본문조회(lawService.do)의 `ID` 파라미터는 `<자치법규ID>`(라이브 확인: 2152625로 본문 64KB 수신, `<자치법규일련번호>`2102461로는 "일치 없음"). 종전 코드는 법령(target=law)용 `<법령일련번호>`만 찾아 **자치법규 응답에서 항상 None → 조례 본문 미조회**(경사도 전량 폴백 + FAR/BCR 라이브조회 무력화의 진원 — FAR/BCR은 persist로 가려져 있었음). 수정: `<자치법규ID>` 우선 + region_name·"도시계획 조례"(시행규칙 배제) 근접페어링.
2. **`_parse_slope_criteria_from_text`** — 종전 정규식 `경사도\s*조사\s*N도`는 붙은 표현만 매치 → 실조례 `평균경사도의 경우 처인구 지역은 20도 이하, 기흥구 17.5도`처럼 사이에 지역명이 끼면 전량 놓침. 수정: `경사도` 앵커 뒤 탐색창에서 `N도` 다중값 수집, **구별 상이 시 안전측 최소(=최엄격) 채택** + `all_values_deg`·변동 caveat. **오탐 방어(리뷰 2R)**: 앵커배제(직전 6자에 종단/도로/진입/옹벽/구조물 → '종단경사도' 등 스킵), 탐색창 절단(도(度)단위 명사 도로/종단/진입/온도/방위에서 절단 → 도로종단 12도·기준온도 20도 미삼킴; 미터명사 표고/높이/폭은 절단어 제외).
   - 리뷰가 잡은 회귀: "평균경사도 25도 + 진입도로 종단경사도 12도" → **25 채택(12 아님)**. 회귀테스트 있음.

---

## 5) 다음 할 일 (우선순위)

### P0 — ★폴리곤 클립 개선 (사용자가 짚은 평균경사도 정확도 후속)
- **문제**: `terrain_service.py`의 경사도 격자(11×11=121점)가 부지 **폴리곤이 아니라 bbox(외접 사각형)** 에 깔려([terrain_service.py:491,509]), 비정형 필지는 **이웃 지형까지 평균경사도에 혼입**. point-in-polygon 클립 미적용.
- **수정 방향**: bbox 격자점 중 **폴리곤 내부 점만 마스킹**해 mean_pct 산출(shapely 있으면 `Polygon.contains`, 없으면 ray-casting 순수함수). 폴리곤 내부 점이 너무 적으면(<N) confidence 낮추고 note. SRTM 30m 자체 한계(소필지 미분해)는 무료소스 제약상 잔존하나 이미 정직 고지됨.
- **주의**: 법정 평균경사도는 국토계획법 시행규칙 산정방식(수치지형도 조밀격자)이라 DEM 근사는 여전히 **예비판정(참고용)** — developability 불변 원칙 유지(무날조).

### P1 — 리뷰 잔여 should-fix (fail-safe, 비블로킹)
- `_parse_ordin_id` 필드순서(명→ID) 가정 방어(엔트리 블록 단위 페어링). 현재 라이브 통과·폴백 있음.
- `_parse_slope_criteria_from_text`: 절단어 뒤라도 '지역은/의 경우/구' 마커 동반 시 절단 보류(더 정교한 구별 나열 보호).

### P2 — 로컬 dev 위생 (선택)
- 로컬 `propai-platform/.env` 114행 MOLEG 인라인 주석 제거(값만 남기기).
- `apps/api/.env`의 MOLEG 더미키 제거(로컬 shadowing 해소).

### P3 — 기존 백로그
- **Cycle 4**: 도시개발 가능성 심화(면적게이트→구역지정·기반시설 신호). [[project_green_zone_dev_coverage]] P3.
- **#148 lint**(546파일 stale): 기능변경 정착 후 rebase 재추진.
- **#162 should_fix**: 임목축적(get_forest_facts) 산림청 API 키 미프로비저닝 → 배선돼 있으나 키 확보 전엔 정직 None(무날조 의도). 산림청 FOREST_API_KEY/BASE/FIELD_MAP 확보 시 자동 동작.

---

## 6) 작업 환경·규약 (필수)

- **전용 워크트리**: 이번 작업은 `/home/kangjh3kang/My_Projects/Development_AI_forestwire`(feat/forest-slope-wiring, #169 머지됨). 공유 메인 `Development_AI/`(feat-tmp)에서 feature 브랜치 checkout 금지.
- **origin/main 기준 작업**: #162~#169 코드는 feat-tmp에 없음. 새 작업은 origin/main 기준 워크트리에서.
- **py3.12 venv**: 스크래치패드가 세션마다 지워짐 → `/usr/bin/python3.12 -m venv` 재생성 + `pip install -r requirements.txt`(★gdal 제외: `grep -ivE "^gdal|rasterio|fiona"`). 테스트: `PYTHONPATH=. pytest`(JWT_SECRET_KEY=x APP_SECRET_KEY=x).
- **성장루프**: executor(author) → code-reviewer(별도 레인, 적대적) → 머지 → safe-deploy → 라이브검증. author/review 반드시 분리.
- **비협상**: main 직접푸시 금지(PR 경유) · 무목업·무날조(정직 폴백) · 완결게이트 · 동일패턴 전역스윕 · 근거+링크(evidence) · 한국어 보고 · 재구현금지(기존자산 확장).

관련 메모리: [[project_moleg_law_api_provisioning]] [[project_green_zone_dev_coverage]] [[project_tojieum_legal_engine]] [[project_special_parcel_detect]] [[project_a1_safe_deploy]] [[project_oracle_deploy]] [[project_kakao_login]]
