# 사통팔땅 지도·법령엔진 구현 기록

## 2026-06-30 구현 완료

### 1. 사통팔땅 지도 기반 통합 시스템

- 커밋: `85fa11b1 feat(web): introduce satong map workspace`
- 범위:
  - `/ko/precheck`를 지도 중심 필지 입력 화면으로 재구성
  - 지번·주소 검색, 엑셀 다필지 등록, 지도 선택을 한 화면의 동일 파이프라인으로 통합
  - 지도 우측 레이어 콘솔, 선택 필지 패널, 산출물 도크를 하나의 작업면에 배치
  - 데스크톱과 모바일에서 가로 넘침 없이 동작하도록 검증

### 2. 법령엔진 보완 및 CAD 설계 배선

- 커밋: `3b391a73 fix(api,web): propagate effective zoning limits`
- 범위:
  - 자연녹지지역·계획관리지역 등 한글 표준 용도지역을 설계 커널에 직접 전달
  - 부지분석 SSOT의 실효 용적률·건폐율을 `auto-design`, `design-alternatives`, `design-operate` API에 전파
  - 법정, 조례, 실효, 목표 한도를 `min()` 경로로 합성해 법정 초과 상향이 발생하지 않도록 보강
  - CAD 생성 패널의 용도지역 목록을 전체 표준 용도지역 목록으로 확장
  - 법규 슬라이더가 법정 한도뿐 아니라 실효 한도도 캡으로 적용하도록 수정

## 검증 결과

- API targeted tests: `102 passed`
- API lint: `ruff check --select F,E9` 통과
- Web lint: `0 errors` 통과, 기존 warning 유지
- Web tests: `685 passed`
- Web type-check: 통과
- Web build: 통과
- Browser smoke:
  - `/ko/precheck` 데스크톱 통과
  - `/ko/design-studio` 데스크톱 통과
  - `/ko/precheck` 모바일 통과
  - 기존 "설계엔진 코드가 없어" 경고 미노출 확인

## 배포 상태

- GitHub push 완료:
  - `codex/dashboard-ia-ui-20260629`
  - 최신 커밋: `5aed72b9`
- 운영 URL 응답:
  - `https://4t8t.net/ko`: `200`
  - `https://4t8t.net/ko/precheck`: `200`
  - `https://4t8t.net/ko/design-studio`: `200`
  - `https://4t8t.net/health`: `200`
- 배포 대상 정정:
  - 프론트 UI 배포 대상은 `ubuntu@158.179.174.207` (`~/.oci.key`, hostname `4t8t`)이다.
  - `ubuntu@168.110.125.89`는 백엔드/API A1이며, 프론트 지도시스템 배포 확인 대상이 아니다.
  - 이전의 `168.110.125.89 Permission denied (publickey)` 판단은 프론트 배포 경로 오인으로 기록 정정한다.
- 2026-06-30 20:35 KST:
  - 프론트 A1 접속 확인: `FRONT_A1_SSH_OK`, hostname `4t8t`
  - 프론트 배포 시작: `/tmp/codex-safe-deploy.sh web codex/dashboard-ia-ui-20260629`
  - 배포 시작 상태: `BUILD web @ 5aed72b9 docs: record satong map and legal engine validation`
- 2026-06-30 20:52 KST:
  - 프론트 A1 배포 완료: `/tmp/deploy_status.txt` = `DONE web=200 api=200 @ 5aed72b9 docs: record satong map and legal engine validation 11:52:30`
  - 라이브 smoke:
    - `https://4t8t.net/ko/precheck`: HTTP `200`
    - `https://4t8t.net/ko/design-studio`: HTTP `200`
    - `https://4t8t.net/health`: HTTP `200`, `postgres/redis/qdrant=healthy`
  - 라이브 HTML 확인:
    - `/ko/precheck`에서 `지도 위에서 입력부터 산출물 생성까지 이어갑니다`, `통합 필지 입력`, `사통팔땅 멀티지도` 문자열 확인
    - `/ko/design-studio`에서 `AI 설계도면(CAD)`, `프로젝트를 선택하면 AI 자동설계` 문자열 확인
  - 비로그인 Playwright 브라우저는 인증 정책에 따라 로그인 화면으로 리다이렉트됨. 로그인 세션에서 지도 작업면을 확인해야 한다.

## 다음 배포 명령

프론트 Oracle A1에 접속 가능한 터미널에서 실행:

```bash
ssh -i ~/.oci.key ubuntu@158.179.174.207
cd ~/Development_AI
VERIFY_BASE_URL=http://localhost:80 \
  bash /tmp/codex-safe-deploy.sh web codex/dashboard-ia-ui-20260629
```

배포 후 상태 확인:

```bash
cat /tmp/deploy_status.txt
tail -120 /tmp/deploy.log
curl -I http://localhost:80/ko
curl -I http://localhost:80/health
```

## 2026-06-30 21:20 KST 지도 레이어 미작동 원인 확인

- 상세 보고서: `_workspace/SATONG_MAP_LAYER_ROOT_CAUSE_2026-06-30.md`
- 결론:
  - `/ko/precheck`의 레이어 버튼은 `enabledLayers`/`activeLayerId` 상태와 설명 팝업만 변경한다.
  - 실제 지도 렌더러인 `ParcelPickerMap`에는 레이어 상태가 props로 전달되지 않는다.
  - `ParcelPickerMap`은 Leaflet + OSM 기본 타일과 `/zoning/parcel-at-point` 클릭 조회만 수행한다.
  - 실제 지적도·용도지역·공시지가·노후도 기능은 `ParcelBoundaryMap`, 실거래·분양 기능은 `NearbyTransactionsMap`, 지형·교통·로드뷰·측정 기능은 `KakaoMapControls`에 분산되어 있고 신규 사통팔땅 지도 OS에 통합되지 않았다.
- 근본 원인:
  - “통합 지도 UI”와 “실제 GIS/시장/로드뷰 레이어 엔진” 사이의 기능 계약 및 데이터 배선 부재.
- 다음 구현 원칙:
  - `SatongUnifiedMap` + `MapLayerRegistry`를 만들고 레이어 버튼 클릭이 실제 지도 인스턴스의 타일, 폴리곤, 마커, 오버레이 변화로 이어지게 한다.
  - 기능 소스가 없는 레이어는 활성처럼 표시하지 않고 disabled/needs-data 상태로 명확히 구분한다.
