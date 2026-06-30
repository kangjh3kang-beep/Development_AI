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
  - 최신 커밋: `3b391a73`
- 운영 URL 응답:
  - `https://4t8t.net/ko`: `200`
  - `https://4t8t.net/ko/precheck`: `200`
  - `https://4t8t.net/ko/design-studio`: `200`
  - `https://4t8t.net/health`: `200`
- Oracle SSH 배포 차단:
  - `ubuntu@168.110.125.89: Permission denied (publickey)`
  - 원격 서버의 `safe-deploy.sh` 실행은 SSH 공개키 승인 후 가능

## 다음 배포 명령

Oracle 서버에 접속 가능한 터미널에서 실행:

```bash
cd ~/Development_AI
VERIFY_BASE_URL=http://localhost:80 \
  bash propai-platform/scripts/safe-deploy.sh both codex/dashboard-ia-ui-20260629
```

배포 후 상태 확인:

```bash
cat /tmp/deploy_status.txt
tail -120 /tmp/deploy.log
curl -I http://localhost:80/ko
curl -I http://localhost:80/health
```
