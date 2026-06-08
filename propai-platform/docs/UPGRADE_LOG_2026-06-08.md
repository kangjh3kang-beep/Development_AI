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
- [ ] 혁신요소(더치페이·해촉증명·구인구직·무결성가드·AI예측) 완성도 점검

## 배포 방식(고정)
- 백엔드: Oracle SSH(propai-api-8000, `-p 8000:8000`, KAKAO env 보존) git pull+build Dockerfile.oracle.
- 프론트: A1 `docker-compose build web` → `docker run --network propai-platform_propai-network --network-alias web`(compose v1 ContainerConfig 회피), sw CACHE_NAME bump, edge 검증.
