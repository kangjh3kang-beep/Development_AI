# 106 — PropAI 프로덕션 배포 전 코드리뷰 (2026-06-07)

리뷰어: code-reviewer (Opus 4.8) · 읽기전용 · 코드 수정 없음
범위: 이번 세션 변경 전체(git diff + git diff --cached + 신규 untracked 코드파일)
검증: tsc --noEmit(프론트 전체 0 에러) · py AST 파싱(백엔드 변경 9파일 OK) · alembic head 분석 · 의존성 정합

---

## 배포 차단(BLOCKER) 판정

**HIGH 신뢰도 Critical/High 차단항목: 없음.**
기능 회귀를 일으키는 빌드/타입/임포트 차단요소는 확인되지 않았다(tsc 0에러, py 파싱 OK, NextStageCta·types·locale 키 모두 존재).

단, **배포 운영자가 반드시 확인해야 할 High 1건(마이그레이션 멀티헤드)** 이 있다. 코드 자체 결함이 아니라 마이그레이션 적용 경로의 사전 조건이다(아래 H1).

---

## 심각도 요약
- CRITICAL: 0
- HIGH: 1 (H1 마이그레이션 멀티헤드 — 사전조건)
- MEDIUM: 4
- LOW: 5
- Open Questions(저신뢰): 2

---

## HIGH

### H1. alembic 멀티헤드 — `alembic upgrade head` 실패 위험 (사전조건)
- 파일: `apps/api/database/migrations/versions/023_user_subscription_columns.py:24`, `024_project_analysis_snapshot.py:17`, `scripts/db_reset_and_migrate.sh:33`
- 신뢰도: HIGH
- 근거: 023→024 체인은 `v62_4_p6_tables`에 정상 연결돼 단일 선형이다. 그러나 리포지토리 전체 head를 집합연산으로 산출한 결과 head가 5개다:
  `015_patch_s06_backup_logs / 019_spatial / 021_v62_design_tables / 022_user_project_store / 024_project_analysis_snapshot`.
  4개(015/019/021/022)는 이번 세션 이전부터 존재한 댕글링 head이며, 024가 이번 세션 신규 head다.
  배포 스크립트는 `alembic upgrade head`(단수)를 호출하므로 멀티헤드 상태에서는
  `Multiple head revisions are present ... please specify a specific target` 로 **실패**한다.
- 완화 정황: 메모리/주석에 따르면 실제 과금·스냅샷 컬럼은 `billing_service.ensure_schema()`의 런타임 raw DDL(ADD COLUMN IF NOT EXISTS)로도 적용되며, 023/024는 멱등(IF NOT EXISTS)이라 적용 안 돼도 런타임이 보완한다. 즉 마이그레이션이 사실상 "정식화 문서" 성격이고 컬럼 자체는 런타임에 보장됨.
- 권고:
  1) 배포 전 `alembic heads`로 head 수 확인. 멀티헤드면 `alembic upgrade <revision>` 으로 명시 적용하거나 `alembic merge` 로 병합 리비전 추가.
  2) 또는 스크립트를 `alembic upgrade heads`(복수)로 변경.
  3) 이번 세션 023/024가 멀티헤드를 "악화"시키진 않으나(기존 4개에 1개 추가), 배포 시 명시 적용 경로가 없으면 마이그레이션 단계가 깨진다 — 운영자 확인 필수.

---

## MEDIUM

### M1. 디지털트윈 빈 parcel.ring_enu → NaN 지오메트리(고도제한/정북사선 면)
- 파일: `apps/web/components/digital-twin/DigitalTwinScene.tsx:341`(`parcelBboxEnu`), `:367`(`HeightLimitPlane`), `:393`(`NorthLightEnvelope`)
- 백엔드 근거: `apps/api/app/services/digital_twin/scene_service.py:126` — `ring_enu = _ring_to_enu(ring, ...) if ring else []` → 빈 배열 가능.
- 신뢰도: MEDIUM
- 근거: 프론트는 `payload.parcel && ...` 로만 가드한다. `{ring_enu: []}` 도 truthy다. 빈 배열이면 `parcelBboxEnu`의 min/max가 `Infinity/-Infinity`로 남고 → `Math.max(4, maxX-minX)` = `Math.max(4, -Infinity)` = NaN → `PlaneGeometry(NaN, NaN)` / 위치 `[NaN, baseY+h, NaN]` / `NorthLightEnvelope`의 Float32Array에 NaN. R3F는 보통 하드크래시까진 안 가나 캔버스 일부가 사라지거나 WebGL 경고가 반복될 수 있다.
- 발생조건(동시 충족 필요): ①parcel geometry 미확보로 ring_enu=[] AND ②해당 zone이 절대높이 한도 있음(주거지역) AND ③사용자가 고도제한/정북사선 토글 ON. 좁은 경로지만 부지분석 핵심 화면.
- 권고: 면 생성 컴포넌트 진입부에서 `if (!parcel.ring_enu || parcel.ring_enu.length < 3) return null;` 가드 추가. 또는 `parcelBboxEnu` 결과가 유한값인지(`Number.isFinite`) 검사 후 미생성.

### M2. 디지털트윈 항공 레이어 기본 ON — 알려진 정합 미해결(WARN-1) 상태로 노출
- 파일: `apps/web/components/digital-twin/DigitalTwinScene.tsx:680`(`aerial: true`), 백엔드 `scene_service.py:_aerial_cover_m` 독스트링(가로/세로 cos(lat) 스케일 불일치 명시)
- 신뢰도: MEDIUM
- 근거: 백엔드가 EPSG:4326 정사각 항공이미지의 세로(위도) 커버폭은 가로 대비 1/cos(lat)배(한국 ≈+25%) 큰데, 프론트가 cover_m(가로) 단일 스케일로 정사각 평면 드레이프 시 위도방향 압축. 코드 주석 스스로 "WARN-1: 정합 처리 중 — 육안 어긋나면 토글로 끄기"라고 인정. 기본 ON이라 첫 진입에 어긋난 텍스처가 바로 노출.
- 권고: 정합 완료 전까지 `aerial: false`(기본 OFF) 권장, 또는 프론트가 `cover_lon_m`/`cover_lat_m`(백엔드가 이미 제공) 분리 적용해 평면 가로/세로 스케일 차등. 차단은 아님(토글 제공).

### M3. 분석 스냅샷 복원→즉시 재push 에코(중복 PUT 1회/로드)
- 파일: `apps/web/components/projects/ProjectContextBinder.tsx:68`(`applyRemoteSnapshot`) → `apps/web/lib/projectSync.ts:140`(setState) → `ProjectSyncProvider.tsx:20`(subscribe→scheduleSnapshotSync)
- 신뢰도: MEDIUM(루프 아님 확인됨)
- 근거: 프로젝트 진입 시 `applyRemoteSnapshot`이 `setState`로 store를 갱신 → contextStore.subscribe 발화 → `scheduleSnapshotSync`(1.5s 디바운스) → `pushSnapshot`이 방금 받은 값을 그대로 서버에 PUT. 무한루프는 아니다(push 응답을 store에 안 씀, 값 동일). 다만 로드마다 불필요한 PUT 1회 발생. `applyRemoteSnapshot`의 `localTs > backendTs` 가드가 있어 값 변형은 없으나 네트워크 낭비.
- 권고: `applyRemoteSnapshot` 직후 `pulled`와 유사한 "방금 복원함" 플래그로 다음 1회 push 스킵, 또는 setState 시 updatedAt을 백엔드값 그대로 유지해 dedup.

### M4. site-analysis auto-AVM useEffect — 중복 analysisResults 누적 가능성(현재는 안전)
- 파일: `apps/web/components/projects/ProjectSiteAnalysisWorkspaceClient.tsx:357~`(auto useEffect, deps `[autoMode, canUseLiveApi, autoAddress, autoPnu, autoArea]`)
- 신뢰도: MEDIUM
- 근거: 성공 시 `addAnalysisResult({completedAt: new Date().toISOString(), ...})`로 append. effect가 재실행되면 매번 결과가 누적된다. 현재는 effect가 받은 `autoAddress/autoArea/autoPnu`를 그대로 다시 `updateSiteAnalysis`로 쓰므로 deps 값이 안정 → 재실행 안 됨(안전). 단 상위 `siteData`가 다른 경로로 address/area를 바꾸면 재실행+중복 append 위험. `eslint-disable exhaustive-deps`로 의존성을 수동 관리 중이라 깨지기 쉬움.
- 권고: append 전에 동일 module+address 결과 존재 시 교체(upsert) 처리, 또는 "1회만 실행" ref 가드.

---

## LOW

### L1. 루트 package.json에 dev 도구가 production dependencies로 오염
- 파일: `package.json:+dependencies`(eslint/prettier/eslint-plugin-* 13종), `+"main":"index.js"`, `+"license":"ISC"`, 빈 author/description
- 신뢰도: HIGH
- 근거: `npm init`/IDE 자동주입 흔적. pnpm 워크스페이스 루트에 lint 도구를 runtime `dependencies`로 선언 → 프로덕션 이미지 의존성 비대. `index.js`/ISC 라이선스는 의미 없는 잔재.
- 권고: 이 블록을 제거하거나 `devDependencies`로 이동, `main`/`license`/`author`/`description` 잔재 정리. 빌드 차단은 아님.

### L2. Dockerfile.web 선두 빈 줄 4개
- 파일: `Dockerfile.web:1-4`
- 근거: `FROM` 앞 빈 줄. Docker가 첫 명령 전 빈 줄은 허용하므로 빌드는 됨. 위생 문제.
- 권고: 빈 줄 제거.

### L3. glb GET 라우트 ETag가 생성 후 계산 — 서버측 생성비용 절감 없음
- 파일: `apps/api/app/routers/design_v61.py:585`(etag = sha1(glb) after build)
- 근거: ETag를 glb 바이트로 생성하므로 매 요청 IFC→glTF 변환을 끝낸 뒤 ETag를 만든다. `If-None-Match` 304 분기도 없어 동일요청 재변환 비용 그대로. `Cache-Control: max-age=300`로 클라 캐시만 절감.
- 권고: design_version_id+매스 해시로 ETag 선계산 후 `If-None-Match` 매칭 시 304 반환(변환 스킵). 또는 결과 메모이즈.

### L4. glb GET 라우트 무인증(라우터 전체 패턴과 동일 — 회귀 아님)
- 파일: `apps/api/app/routers/design_v61.py:547`
- 근거: 신규 GET `/{design_version_id}/bim/model.glb`에 auth 의존성 없음. 단 design_v61 라우터의 모든 기존 라우트가 무인증이라 일관(회귀 아님). raw SQL은 파라미터 바인딩(`:vid`)+UUID 검증으로 인젝션 안전.
- 권고: 라우터 전반 인증 정책을 차후 일괄 검토(이번 변경만의 문제 아님).

### L5. LandIntelligencePanel transaction 데이터 fetch 잔존(표시 제거됐는데 호출 유지)
- 파일: `apps/web/components/projects/LandIntelligencePanel.tsx:186-280, 482`
- 근거: transaction 탭 표시는 지도 CTA로 대체됐으나 `txData/txLoading/setTx*` fetch 이펙트는 그대로 남음. 결과는 `txError`(status dot, :482)에만 쓰이고 `txData`는 사실상 미표시. 불필요한 실거래 API 호출 1회/로드.
- 권고: status dot에 transaction 의존이 꼭 필요한지 검토 후, 불필요하면 fetch 제거. (린터가 unused로 잡지는 않음 — setter들이 참조됨.)

---

## Open Questions (저신뢰 — 차단 아님, 운영 확인 권장)

### Q1. environment_service `max(p["altitude_deg"] for p in sun_positions)` 빈 시퀀스 ValueError
- 파일: `apps/api/app/services/environment/environment_service.py:241`
- 신뢰도: LOW
- 근거: `sun_positions`가 비면 `max(...)`가 ValueError. 시각 루프(09~15시)가 항상 항목을 만들면 비지 않으나, 위도/계산 분기에 따라 빈 케이스가 가능한지 미확인. 빈 케이스 발생 시 /environment/analyze 500.
- 권고: `max((p["altitude_deg"] for p in sun_positions), default=0.0)` 로 방어. 런타임 라이브 1회로 빈 케이스 가능성 확인 요망.

### Q2. 주변 실높이 병렬 보강 배치 타임아웃과 SCENE_TIMEOUT 합산 여유
- 파일: `apps/api/app/services/digital_twin/scene_service.py:36-39, _enrich_neighbor_heights`
- 신뢰도: LOW
- 근거: 개별 8s × 동시발사, 배치 상한 14s. asyncio.gather 동시실행이라 정상은 ~8s 내 수렴, 배치 14s가 상한. `build_scene` 전체가 SCENE_TIMEOUT_S=88s 가드 내인지(지형60+항공20+주변보강14 직렬합산 시 여유) 라이브 확인 권장. 코드상 주변보강은 _build_neighbors 내부라 병렬구조 양호하나, 국외IP차단 시 8s씩 대기 후 폴백되는 동작 1회 측정 권장.
- 권고: 라이브에서 국외IP/차단 환경 1회 측정해 88s 가드 내 안정 확인.

---

## 긍정적 관찰(좋은 패턴 — 유지 권장)

- **과금게이트 회귀 안전**: `enforce_llm_quota`(billing_deps.py)는 ①uid 없으면 즉시 통과 ②`is_blocked` 예외는 swallow 후 통과 ③blocked=True일 때만 402. 정상/무료/비로그인 사용자를 막지 않음 — 회귀 위험 없음 확인.
- **use_llm 명시실행 일관성**: esg/permits/regulation/feasibility/pipeline 전부 `use_llm` 플래그로 LLM 생략 시 규칙기반 폴백을 반환. permit `_multi_parcel_fallback` 추출로 LLM실패·미사용 폴백을 단일화(DRY) — 좋은 리팩토링.
- **마이그레이션 멱등·무손실**: 023/024 모두 `ADD COLUMN IF NOT EXISTS`+nullable+백필없음, downgrade에서 DROP 안 함(데이터 보존). 런타임 ensure_schema와 멱등 공존 설계 우수.
- **UserSubscription 이중매핑 회피**: 동일 `users` 테이블을 독립 `BillingBase(DeclarativeBase)` 위에 매핑해 메인 Base와 registry 분리 → SQLAlchemy mapper 충돌 회피. 설계 의도가 명확하고 정확.
- **court_scraper 재구현**: requests(미설치)→httpx(기존 의존) 전환으로 의존성 변경 0, 세션쿠키 선취득·보안헤더·ipcheck 차단 정직노출·전 구간 예외처리·to_thread 동기래핑 정합. 무목업 원칙 준수.
- **projectSync 가드 충실**: UUID 정규식 가드(비-UUID 500 회피), `pulled` 게이트(빈 로컬로 서버 덮어쓰기 방지), updatedAt 타임스탬프 충돌해소, 디바운스. 무한루프 없음 확인.
- **환경분석 season refetch 무한루프 차단**: `lastSeasonRef` + `!res||busy` + `lastSeasonRef===season` 3중 가드로 계절 자동재요청 루프 방지. 정확.
- **무목업·정직표기 일관**: 디지털트윈 "건물 매스 없음" 안내·고도제한 "FAR기반 절대높이 없음" 배지·AnalysisSummary "자료 없음" 표기 등 가짜데이터 금지 철학 유지.
- **감사로그 blob 제외**: projects update_project가 analysis_snapshot 대용량 blob을 after_state에서 제외하고 `analysis_snapshot_updated:true` 플래그만 기록 — 좋은 처리. `model_dump(exclude_unset=True)`로 부분 PUT이 스냅샷을 None으로 덮어쓰지 않음 확인.

---

## 검증 증거
- `tsc --noEmit`(apps/web 전체): 변경 파일 포함 0 에러.
- py AST 파싱: 백엔드 변경 9파일 전부 OK.
- alembic head 집합연산: 5 head 확인(024 신규 + 기존 4 댕글링).
- NextStageCta.tsx 존재·tracked 확인, locale 3종(ko/en/zh-CN) modulePlaceholders["feasibility"/"site-analysis"] 키 전부 존재.
- 스크롤 앵커 `#nearby-transactions-map` site-analysis/page.tsx:926 존재.
- TerrainResult/SunPosition/EnvironmentResult 타입 필드 정합 확인.

## 최종 권고: REQUEST CHANGES (배포는 H1 운영확인 + M1 가드 추가 후 진행 권장)
- H1(마이그레이션 멀티헤드)은 코드결함이 아닌 적용경로 사전조건 — 운영자가 명시적용/병합 확인 시 배포 가능.
- M1(빈 ring_enu NaN 가드)은 부지분석 핵심화면 안정성 — 배포 전 3줄 가드 추가 강력 권장.
- 나머지 M/L은 배포 후 후속 정리 가능(차단 아님).
