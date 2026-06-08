# PropAI 업그레이드 로그 — 2026-06-08 세션

> 모든 과정·결과를 실시간 기록(사용자 요청). 각 항목 = 배포 단위(sw CACHE_NAME), 라이브 검증 완료.

## 배포 이력 (프론트 sw 버전 기준)
| 버전 | 내용 | 검증 |
|------|------|------|
| v95 | 무거운 분석 영속 캐시(지형·환경·AVM·디지털트윈) — 입력 불변 시 재사용, 변경 시 재분석 제안 | tsc·edge |
| v96 | 대시보드=체험(부지+약식수지) vs 프로젝트=전체분석 차별화(이력분리·잠금·승격CTA) | edge |
| v97 | 경매 물건상세 보강(PNU 토지면적·용도지역·공시지가)+사안별 미제공 사유+항공뷰 폴백 | 라이브 |
| v98 | 경매 공고물건정보(getPbancCltrInf2) 연동 — 유찰횟수·재산유형·처분방식·용도분류 | 라이브 |
| v99 | 경매 물건상세정보(getRlstDtlInf2) — 실제 물건 사진·이용현황·동영상 | 라이브 |
| v100 | 경매 입찰정보 섹션(getCltrBidInf2) + 등기부등본 권리분석 건당 과금 | 라이브 |
| v101 | 등기 발급·열람 과금 + 권리분석 2,000원 상향 + 공·경매 모니터링 구독자 전용 | preview-charge 검증 |
| v102 | 경매 물건 사진 갤러리(다중·반응형 object-contain) + 순위 감정가 누락 보강 | 5장 검증 |
| v103 | 필지정보 근본수정(getLandCharacteristics+주소→PNU 폴백) + 필지구획도 스크롤 줌 | 38-63 라이브 |
| v104 | 카카오 로그인 활성화(login-url 엔드포인트+버튼+서버 REST키) | login-url 검증 |
| v106 | 디지털트윈 실사 항공뷰 정합(bbox 맞춤 항공영상+UV 보정) + 현장앱 비밀번호 설정(목록) | cover_lon_m 299.9 |
| v107 | 분양현장 '설정·요약' 핵심 허브 탭(기본 진입, 비번설정+12메뉴 이동) | edge |
| (백엔드) | 동적 환경설정 — 관리자 .env 키 카탈로그 확대(인증·소셜 5 + 스토리지·기타 4, 총 31키) | 5그룹 검증 |
| v108 | 선택기 슬라이스1 — 계약 목록 GET + 수납 패널 계약 선택기(UUID 수기→드롭다운) | 라이브 |
| v109 | 선택기 슬라이스2 — 대출(계약·협약·약정)·전매(계약) 선택기 | 라이브 |
| v110 | 액션 에러 피드백 — 세금·수수료 패널 동작 실패 시 무반응 해소 | 라이브 |
| v111 | 로딩 스켈레톤 — 청약·수납·대출·수수료 패널 첫 로드 자리표시(빈 깜빡임 해소) | edge OK |
| v112 | 로딩 스켈레톤 마무리 — 세금·전매·조직도 패널 + 전매 액션 에러 피드백 | edge OK |
| v113 | 계약 체결(최초 생성) 연결 — 세대→계약→수납/대출/전매 전주기 단절 복구(create_contract+POST /contracts+Unit360 버튼) | 백엔드 라이브(/api/v1/sales/contracts) |
| v114(BE) | 자동 CRUD가 /contracts 라우트를 섀도잉 → 액션 라우터 우선 등록. v108/v109 선택기 빈 라벨·v113 계약 상태전환 누락 동시 해소 | ✅ E2E 검증 |
| v115(BE) | 도메인 라우터 전체를 CRUD보다 먼저 등록 — /work-logs/summary·POST /work-logs·/units/board 섀도잉 일괄 해소 | ✅ 라이브 검증(200, 회귀 없음) |

## Phase A — 무결점 코드리뷰(멀티에이전트 3관점) + Critical 수정(v116)
3개 `code-reviewer`(opus)로 ①백엔드 워크플로우/상태머신 ②보안·RBAC·라우팅 ③프론트연동·외부데이터 리뷰.
발견 Critical/High를 v116으로 일괄 수정:
| ID | 결함 | 수정 |
|----|------|------|
| S1 | 자동 CRUD `/{id}` GET/PATCH/DELETE 테넌트 격리 부재(타 현장 누출/변조, ~50 엔드포인트) | CRUDBase.get/update/delete `site_id` 강제 + 라우터가 ctx.site_id 전달 |
| S2 | 계약 취소 후 세대 CANCELLED 고착 → 재분양 불가 | cancel 시 세대 AVAILABLE 복귀 |
| S3 | 계약 체결 시 `member_node_id` 미설정 → 수수료 split 빈 체인 early-return(전원 미배분) | create_contract·POST /contracts에 member_node_id 플럼 |
| S4 | 입금 webhook 멱등성 부재 → 중복 이중충당 | raw_ref 중복 무시 + 음수금액 거부 + manual_match 멱등·site격리 |
| S5 | `/units/{id}/hold` 중복 라우트(actions+units_live) | actions 제거·units_live 일원화(+감사행 이전) |
| H-3 | sign_contract 재서명 시 회차·수수료 중복생성 | RESERVED/ACTIVE만 서명 허용(409) |
| C-3 | va_issue를 MEMBER도 호출 | AGENCY+ 권한 상향·입력검증 |
| M-3 | decide_transfer 타 현장 명의변경 가능 | site_id 격리 |
| S6 | 프론트 CRM 고객목록/상세 전면 단절(필드명·site_code→422·timeline 키) | customer_id/stage/site_name 정합, site_id 미전송(헤더위임), timeline 키 |
후속(미포함): 초과입금 선수금 적재, overdue 멱등, payments_webhook PG서명 분리.

## 혁신요소 라이브 스폿체크(슬라이스4)
| 기능 | 엔드포인트 | 결과 |
|------|-----------|------|
| 🛡 무결성 가드 | GET /integrity/check | ✅ 200 — 미가격 세대 12건 실시간 적발(작동) |
| 해촉증명 | GET /cert/issuers | ✅ 200 |
| 더치페이(수수료협약) | GET /commission/agreements | ✅ 200 |
| AI 고객예측 | GET /crm/grade-suggestions | ✅ 200 |
| 영업일지 실적집계 | GET /work-logs/summary | ✅ v115 후 200(집계 정상) |
| 구인구직/추천 | GET /referral/stats | 422(code 파라미터 필수=정상 설계) |

### 라이브 검증 중 발견(중요)
- POST /contracts E2E: 계약 행은 생성됐으나 응답이 **원시 ORM**(내 dict 아님)+세대 상태 AVAILABLE 유지 → 자동 CRUD가
  같은 경로를 먼저 잡아 내 핸들러를 가린 것. `(SalesContractExt,"contracts")` REGISTRY 자동생성이 원인.
  ⇒ 이전 세션의 계약 선택기(v108/v109)도 사실상 빈 라벨이었음을 발견·동시 수정(v114).

## ⚠ 인시던트 기록 (2026-06-08 백엔드 일시 중단)
- 원인: 백엔드 재배포 시 잘못된 경로(`-f apps/api/Dockerfile.oracle`, 실제는 루트 `Dockerfile.oracle`)+
  잘못된 env(`apps/api/.env`, 실제는 `propai-platform/.env`) → 빌드/런 실패 후 기존 컨테이너만 제거되어 502.
- 복구: 기존 `propai-api:oracle` 이미지로 즉시 재기동(서비스 회복) → 올바른 명령으로 v113 재빌드 후 스왑.
- ★배포 정정(고정): `cd propai-platform && docker build -f Dockerfile.oracle -t propai-api:oracle .` →
  `docker run -d --name propai-api-8000 --restart always --env-file .env -p 8000:8000 propai-api:oracle`.
  프런트엔드 Caddy(host망)가 `reverse_proxy localhost:8000` 이므로 반드시 `-p 8000:8000`.

## ⚠ 인시던트#2 (v116 배포 시 백엔드 크래시 루프)
- 원인: v116 커밋에서 `git add -A propai-platform/apps/api`가 추적 안 되던 **미완성 WIP 파일
  `system_setting.py`**(+__init__ 등록)를 함께 커밋. 이 파일이 base.py에 없는 `BaseModel`을
  import → 모델 로딩 ImportError로 앱 부팅 실패(8회 재시작). v115는 Docker 레이어 캐시로 가려져
  정상 부팅했으나, v116의 apps/api 변경이 캐시를 무효화하며 표면화.
- 복구: 고아 WIP 제거(어디서도 미사용, 동적설정은 platform_secrets로 이미 동작) → 재빌드·재기동.
- ★교훈(고정): 커밋은 **변경한 파일만 명시적으로 `git add`** 하고 `git add -A <dir>`는 금지
  (추적 안 된 WIP를 쓸어담아 부팅 깨짐). 빌드 후 `health:200`까지 확인 후 다음 단계.

## Phase B — 혁신 디자인 리팩토링 (OMC designer 에이전트)
방향: **프리미엄 데이터 인텔리전스**(Bloomberg/Linear/Vercel 풍). 플래그십: **부지분석(외부데이터 정보서비스)**.
| 버전 | 내용 | 검증 |
|------|------|------|
| v118 | 부지분석 리디자인 — sa-di-* 프리미엄 유틸(헤어라인 블록·metric tile·data table·stats·게이지·token chip), 두꺼운 카드/하드코딩색 제거, 데이터 우선 표현 | ✅ edge 라이브(내부+edge sw v118) |
| v119 | 디자인 언어 확산 — 시장·시세(2)·경매·공매(2) 화면에 sa-di-* 적용(globals.css 무수정 재사용), 하드코딩색 토큰화, 기능 무변경 | tsc 통합 EXIT0·하드코딩0 (v120에 포함 배포) |
| v120 | 경매 물건상세 고도화 — 이미지 과확대/깨짐 근본수정 + 상세 단락별(개요/토지·건물/입찰·진행) 디자인 분류 | ✅ 라이브(edge v120) |
| v121 | 경매 물건상세 사진 클릭 확대(라이트박스) — 전체화면·좌우이동(‹›/←→)·Esc·n/total | ✅ 라이브(edge v121) |
| v122 | 대시보드 애플급 리디자인 1차 — db-* 유틸, 히어로/기능요약/KPI 빈상태/프로모 절제·토큰화 | ✅ 라이브 → critic REVISE |
| v123 | 대시보드 애플급 정제 2차 — critic Top3+High 반영(한글자간·로고중복·네온시안→파랑·KPI빈상태·카드균일) | ✅ 라이브 → critic 재검 ACCEPT(잔여 1건) |
| v124 | 히어로 헤드라인 한글 word-break:keep-all (critic 재검 잔여 MAJOR 해소) → 애플급 ACCEPT | ✅ |
| v125 | 히어로 카피 변경("개발사업의 필수 플랫폼! 주소만 입력하면, 시장조사·사업성·수지 분석을 한 번에.")+반응형 줄바꿈 | ✅ 라이브 |
| (api·web 전체 재빌드) | 사용자 요청 — G2B /detail 재확인(이미 200·7섹션) + api(HEAD)·web(HEAD) 전체 재배포 | ✅ health200·/detail200·edge v125 |
| v126 | 스카이게러지 '팔라트리아' 프리미엄 배너(분양광고 배너 위)+skygarage.net 링크. 골드 럭셔리·왕관·타이포, 사진 슬롯 폴백 | 빌드 중 |
- ※팔라트리아 실사진은 첨부 이미지를 코드가 호스팅 불가 → `apps/web/public/images/palatria-hero.jpg` 업로드 필요(없으면 골드 그라데이션 폴백).

### critic 재검 결과(v123)
- VERDICT: ACCEPT-WITH-RESERVATIONS. C1~C3·H1·H4 = **5/5 해소 확인**. 잔여 = 헤드라인 word-break MAJOR 1건(+ESG 글로우 MINOR=코드상 이미 중립, 저해상 오인). → v124에서 word-break 교정 = ACCEPT.

### 애플급 디자인 반복 루프(designer→critic→designer)
- v122 후 Playwright 스크린샷 → **critic(opus) 적대적 비평**: VERDICT REVISE. 'AI 조립 느낌' 직접원인 3대 발견:
  C1 워드마크 3중 노출, C2 시각언어 2종 충돌(차분 SaaS vs 네온 시안 HUD), **C3 한글 자간 과다(영문 트래킹 오용)**.
- v123에서 Top3+H1/H3 교정. 다음: 재촬영 → critic 재검(ACCEPT 목표).

## 애플급 디자인 고도화 이니셔티브 (방법론)
- 사용자 결정: 시각검증=**Playwright 스크린샷 도구 셋업**(완료, /tmp/shot), 범위=**핵심 화면 1개(대시보드) 완벽부터**.
- 방법: ①디자인 헌법(절제·8pt·타입ramp·accent 1색) ②전역 기반 ③화면별 designer→critic 적대적 리뷰 ④토큰/tsc/슬라이스 커밋 안전장치.
- 진행: v122 대시보드 1차 리디자인 → 배포 후 스크린샷 재촬영 → critic 리뷰 → 반복.
- ★A1 디스크 재발(99%)로 v120 빌드 1회 실패 → `docker system prune -af`(44G→11G) 후 성공. 배포 루틴에 prune 선행 고정(메모리 기록).

### 이미지 깨짐 근본원인(v120)
- 원인: 메인/항공 이미지 `h-full w-full object-contain` → 컨테이너 강제 채움 → 지적도 등 **저해상도 온비드 원본이 과확대돼 뭉개짐**. 백엔드는 onbid `potoUrlList` 원본 URL 그대로(더 높은 해상도 없음)라 프론트 표시 문제.
- 해결: `max-h-full max-w-full`(원본 크기까지만, 작은 건 또렷이 가운데·큰 건 축소). 썸네일 `object-cover`(잘림)→`object-contain`+레터박스.
- 단락 분류: 평면 속성 나열 → 3단락(OVERVIEW/LAND·BUILDING/BID·PROGRESS) eyebrow 소제목, 타일 중복 제거, 빈값 자동 숨김.
- 색 100% 토큰(color-mix 포함). 데이터 배선·로직 보존. sa-di-*는 도메인 비종속 → 시장/경매로 확산 예정.
- 다음: v118 시각검증 후 시장·시세/경매·공매 화면에 동일 언어 반복 적용(고도화 루프).

## 추가 해결(엑셀·등기·경매 API)
- 엑셀 토지조서 LLM 파싱 폴백(병합셀 지번 상속·집계행 제외) — 합성 3행 검증.
- AVM 비상식 단가 근본수정(강남 폴백 제거→PNU 시군구 도출, 92억→9.32억).
- AVM "로그인 필요" 오류(RBAC write→read).

## 분양 ERP 무결점 로드맵(반복 고도화)
- [x] 설정·요약 허브 / 비번 설정 / 선택기 일괄 / 액션 에러 피드백 (High)
- [x] 로딩 스켈레톤(주요 7패널, Medium) — 청약·수납·대출·수수료(v111) + 세금·전매·조직도(v112). CRM은 기존 listLoading 보유
- [x] 전주기 워크플로우 연결성(현장→세대→가격→청약→계약→수납→대출→정산→전매)
  - 발견1: `sales_contracts_ext` 생성 코드 부재 → 계약 드롭다운 항상 빈 단절(v113 create_contract 복구)
  - 발견2: 자동 CRUD가 /contracts 섀도잉 → 선택기 빈 라벨·계약 상태전환 누락(v114 라우터 우선순위 수정)
  - ✅ E2E: POST→{stage:RESERVED,total_price}, GET→{label:"상가동 101호"}, unit→RESERVED, 정리(삭제204/복원200)
  - 잔여: 청약 당첨(draw)→reserve_promote→계약 자동 승격 훅(현재 수동 [계약 체결] 버튼)
- [x] 혁신요소(더치페이·해촉증명·구인구직·무결성가드·AI예측) 라이브 스폿체크 — 모두 200 작동,
      영업일지 실적집계 섀도잉(422) 발견·수정(v115). 무결성 가드는 미가격 세대 12건 실적발 동작 확인.

## 배포 방식(고정)
- 백엔드: Oracle SSH(propai-api-8000, `-p 8000:8000`, KAKAO env 보존) git pull+build Dockerfile.oracle.
- 프론트: A1 `docker-compose build web` → `docker run --network propai-platform_propai-network --network-alias web`(compose v1 ContainerConfig 회피), sw CACHE_NAME bump, edge 검증.
