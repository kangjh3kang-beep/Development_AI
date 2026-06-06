# Phase F-2 — 모델하우스 데스크 방문객 개인정보 동의팝업 보강 (풀스택)

## 1. 기존 자산 조사 (중복신설 회피)
- **백엔드 모델**: `apps/api/database/models/sales/commission_mh_harness.py`
  - `MhDesk`/`MhVisitor`/`MhVisitConsent`(`mh_visit_consents`)/`MhStaffMatch`/`MhNotification`/`MhVisitStat` 보유.
  - `MhVisitConsent` 기존 컬럼: `visitor_id, consent_type, items(JSONB), agreed, esign_uri, agreed_at`. → **고지이력(이용목적·보유기간·버전·IP) 컬럼 부재**.
- **방문 등록 라우트**: `apps/api/app/api/endpoints/sales/mh.py` `POST /mh/visitors/checkin` → `app/services/sales/mh/checkin.py:checkin()`.
  - 기존 checkin: consents 배열을 그대로 저장(필수동의 강제 없음, 고지문 없음).
  - `marketing_allowed()` 로 마케팅 분리는 이미 존재.
- **프론트 데스크 패널**: `apps/web/components/desk/DeskCheckin.tsx`
  - 인라인 체크박스 3종(REQUIRED/MARKETING/THIRD_PARTY) + 서명캔버스 + 직원매칭/호출. → **수집항목·이용목적·보유기간 고지 부재**(라벨만 존재).
- 결론: 테이블/엔드포인트/패널 전부 존재 → **신설 금지, 멱등 보강 + 동의팝업 신설**.

## 2. 신규/변경 파일 · 엔드포인트
### 백엔드
| 파일 | 변경 |
|------|------|
| `database/models/sales/commission_mh_harness.py` | `MhVisitConsent` 에 `site_id, purpose, retention, version, consent_ip` 컬럼 추가(nullable, 무파괴) |
| `app/services/sales/mh/consent.py` (신규) | 고지문 템플릿(CONSENT_TEMPLATE, 버전 `2026-06-v1`), `ensure_consent_columns()`(멱등 ALTER…IF NOT EXISTS 5건), `has_required_consent()`, `enrich_consent()`, `template()`, `REQUIRED_TYPES` |
| `app/services/sales/mh/checkin.py` | 필수동의 미충족 시 `HTTPException(422)` 차단, `ensure_consent_columns()` 호출, 동의 레코드에 site_id/purpose/retention/version/consent_ip 보강 저장, `consent_ip` 파라미터 추가 |
| `app/api/endpoints/sales/mh.py` | `GET /mh/consent-template` 신설, `desk_checkin` 에 `Request` 주입 + `_client_ip()`(X-Forwarded-For 우선) → checkin 전달 |

**엔드포인트**
- `GET  /api/v1/sales/mh/consent-template` — 동의 고지문(수집항목·이용목적·보유기간 + 필수/선택 분리) 반환.
- `POST /api/v1/sales/mh/visitors/checkin` — 동의 페이로드 통합(consents[]). 필수 미동의=422 차단, 동의IP 기록.

### 프론트
| 파일 | 변경 |
|------|------|
| `components/desk/ConsentModal.tsx` (신규) | 동의팝업 모달. 수집항목·이용목적·보유기간 고지(dl/dt/dd), 필수/선택 분리 체크, 필수 미동의 시 "동의하고 등록" 버튼 비활성, 폴백 고지문 내장 |
| `components/desk/DeskCheckin.tsx` | 인라인 체크박스 제거 → 체크인 버튼이 동의팝업 오픈. `GET /mh/consent-template` 사전로드, 확인 시 구조화 consents + 서명결합 호출. 기존 직원매칭/명함OCR/호출 흐름 무파괴. `salesApi`/`apiClient` import 보존 |

## 3. 동의팝업 · 필수/마케팅 분리 · 고지문 · 이력
- **고지문(template)**: 3종(REQUIRED/MARKETING/THIRD_PARTY) 각각 `items`(수집항목)·`purpose`(이용목적)·`retention`(보유기간)·`deny_notice`(미동의 안내) 명시. 백엔드 SSOT, 프론트 폴백 동일 골격.
  - REQUIRED 보유기간: "상담종료 후 1년", MARKETING: "철회 시 또는 2년", THIRD_PARTY: "목적 달성/철회 시까지".
- **필수/마케팅 분리**: `REQUIRED_TYPES={'REQUIRED'}`. 마케팅·제3자는 `required:false` → 미동의여도 등록 허용, `marketing_allowed()` 로 발송만 차단(기존 유지).
- **필수 차단**: `has_required_consent()` False면 checkin 422. 프론트는 모달에서 버튼 disabled로 1차 차단.
- **이력**: 각 동의 레코드에 `version`(동의서 버전), `agreed_at`(시각), `consent_ip`(IP), `purpose`/`retention`/`items`(고지내용 스냅샷) 저장 → 어떤 고지문에 언제·어디서 동의했는지 추적.

## 4. 법적 정직성 (개인정보보호법)
- **제15조(수집·이용 동의)**: 수집항목·이용목적·보유기간 명확 고지 후 동의. 필수 미동의=수집 불가(등록 차단 + 안내문).
- **제22조(동의 받는 방법)**: 필수와 선택(마케팅·제3자) 분리 동의. 선택 미동의권 보장(방문등록은 가능).
- **동의이력**: 버전·시각·IP·고지내용 스냅샷 저장. 허위/강제 일괄동의 금지(체크박스 기본 false, 사용자 명시 동의).
- 과장·미구현 자동화 없음. 실제 차단 로직과 이력 저장으로 구현.

## 5. 로컬 검증
### 백엔드
- `py_compile`: consent.py / checkin.py / mh.py / commission_mh_harness.py → **OK**.
- DDL 파싱: `sqlalchemy.text()` 5건 ALTER…IF NOT EXISTS → **DDL_PARSE_OK**.
- 단위검증: 필수게이트(마케팅-only 차단/필수거부 차단/필수동의 통과), 마케팅분리(필수+마케팅거부=등록허용), enrich(purpose/retention/items/version 채움), template(3종·필드 완비) → **전부 PASS**.
- 앱 부팅: `apps.api.app.main:app` 717 라우트, `/api/v1/sales/mh/consent-template` + `/api/v1/sales/mh/visitors/checkin` 마운트 확인 → **ROUTES_OK**. (PYTHONPATH=repo:apps/api, 프로덕션DB·외부호출 없음)

### 프론트
- `npx tsc --noEmit` → **EXIT 0**.
- `npx eslint ConsentModal.tsx DeskCheckin.tsx` → **EXIT 0** (set-state-in-effect 경고는 lazy useState 초기값으로 해소).
- import 보존: `git diff` 결과 `salesApi`/`apiClient` 유지, 추가는 `useEffect` + ConsentModal import만. 기존 직원매칭/명함OCR/호출 흐름 무파괴.

## 6. 커밋
- 메시지: `feat(sales-desk): F-2 방문객 개인정보 동의팝업 — 수집항목/목적/보유기간 고지·필수/마케팅 분리동의·이력저장`
- (해시는 커밋 후 본 보고 하단/반환 메시지에 기재)

## 7. 미진점 / 후속
- **DB 컬럼 실적용**: `ensure_consent_columns()` 는 첫 checkin 호출 시 멱등 적용(단일워커 가정). Alembic 정식 마이그레이션 미생성(기존 sales 도메인 패턴이 `_ensure` 런타임 DDL 사용 → 동일 노선). 다중워커 동시최초호출 시 IF NOT EXISTS로 안전.
- **서명(esign)**: 프론트는 캔버스 서명을 esign_uri(dataURL)로 전송하나, 별도 스토리지 업로드는 미연결(checkin은 dataURL 그대로 저장). 대용량 시 uploads 연계 후속 가능.
- **동의 철회 UI**: 마케팅/제3자 동의 철회(opt-out) 화면 미구현(법 제37조). 후속 Phase 권장.
- **GET consent-template 캐싱**: 정적 템플릿이라 프론트 단순 1회 로드. 다국어/현장별 커스텀 고지문은 미지원(단일 표준문안).
