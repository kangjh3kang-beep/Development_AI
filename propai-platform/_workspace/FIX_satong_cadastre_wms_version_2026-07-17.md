# FIX: 사통맵 지적타일 실패 근본원인 — WMS VERSION 1.1.1 (2026-07-17)

## 증상

사통맵에서 지적도 레이어 토글 시 타일이 뜨지 않고
"지적 타일 조회 실패 — 키 미설정 또는 VWorld 응답 오류" 노트 표시.
사용자는 관리자 화면에서 VWorld 키를 등록했으나 무효과.

## 진단 (라이브 그라운드 트루스)

1. 프로덕션 A/B: 같은 키·domain·Referer로 **WMTS(Base/Satellite)는 200 정상,
   WMS(연속지적도)만 503** — 키 자체는 살아있음(키 미설정 아님).
2. VWorld 직접 호출 채증(로컬):
   - `version=1.1.1` → `<ServiceException code="INVALID_RANGE">VERSION 파라미터의 값이
     유효한 범위를 넘었습니다. 유효한 파라미터 값의 범위 : [1.3.0], 입력한 파라미터 값 :
     1.1.1</ServiceException>` — **키 검증보다 먼저 거부**된다.
   - `version=1.3.0` → 파라미터 통과(로컬 .env 키는 INVALID_KEY — 로컬 키가 미등록 더미일
     뿐, 프로덕션 컨테이너 키는 WMTS 실측으로 유효).

## 근본원인

`SatongMultiMap.tsx`의 지적 레이어 `L.tileLayer.wms(...)`에 `version` 옵션이 없어
**Leaflet 기본값 1.1.1**이 전달 → VWorld WMS는 **1.3.0만 허용** → INVALID_RANGE XML →
프록시 분류기(coverage/auth 이분법)가 이를 auth로 승격 →
"키 미설정 또는 VWorld 응답 오류" **오해 메시지**.

즉 관리자 키 등록과 무관한 순수 코드 버그. (직전 tracer 추정이던 "VWorld 콘솔 WMS
미승인/도메인 불일치" 가설은 원본 XML 채증으로 기각 — code가 접근권한 계열이 아니라
INVALID_RANGE 파라미터 오류였음.)

## 수정

1. **지적 레이어 `version: "1.3.0"` 명시** (SatongMultiMap.tsx) — 1.3.0에서 Leaflet은
   SRS 대신 CRS를 전송(정상, VWorld 수용).
2. **오류 표면화 정직화(전파방지 공용화)**: `vworld-xml-exception.ts`에
   `extractVWorldXmlExceptionDetail()`(ServiceException code·메시지 추출) 추가,
   WMS·WMTS **두 프록시 모두** 503 메시지·로그에 code 표면화
   (`(auth/unknown)` → `(INVALID_RANGE)`/`(INVALID_KEY)`/...) — 같은 뭉뚱그림 오독 재발 차단.
   ※정규식 함정: `<ServiceException[^>]*>`는 `<ServiceExceptionReport>`(접두 동일)도
   매칭 → `(?:\s[^>]*)?>` 경계 강제(테스트 고정).
3. **Base/gray 라벨 오버레이 포팅**(메인 워크트리 미커밋 초안): 일반/회색 지도에서도
   Hybrid 라벨 타일을 labelPane(450)에 얹어 폴리곤이 지명 텍스트를 가리지 않게.

## 검증

- vitest: vworld-wms-proxy(+1 INVALID_RANGE 회귀·auth code 단언) · vworld-wmts-proxy ·
  vworld-xml-exception(+4 추출) · satong-map-layers — **32 passed**
- tsc --noEmit — 통과
- 라이브검증(배포 후): 사통맵 지적 토글 → 필지 경계선 타일 표시 + 오류노트 미표시.
  실패 시 web 컨테이너 로그의 `[vworld-wms-proxy]` code 필드로 원인 즉시 판별
  (INVALID_KEY면 서버 .env 키, UNREGISTERED_DOMAIN이면 VWorld 콘솔 도메인).

## 별도 확인된 구조 결함 (본 PR 범위 밖 — 후속)

**관리자 platform_secrets → apps/web 미배선**: `secret_store.load_into_env()`는
apps/api에만 호출된다. web(Next.js) 프록시의 `VWORLD_API_KEY`(+AI chat 라우트의
ANTHROPIC/OPENAI 키)는 컨테이너 기동 시 .env로만 주입 — **관리자 화면에서 키를
갱신해도 web에는 영원히 미반영**(이번 사용자 혼란의 2차 원인). 해법 후보:
(a) web 타일 프록시를 api로 이관(관리키 자동 반영), (b) web에 api 경유 키 조회 채널,
(c) 배포 스크립트가 admin 키를 .env로 동기화. → 사통맵 UX 리팩토링 PLAN의 WS로 편입.

## 패턴 일반화 (전역 스윕 결과)

- `L.tileLayer.wms` 소비처는 지적 레이어 1곳뿐(용도지역은 별도 경로) — 동일 버그 없음.
- XML 오류 뭉뚱그림 패턴은 WMS·WMTS 두 프록시 공통이었고 이번에 공용 추출 헬퍼로 동시 수정.
