# Phase 1-F — 전자 해촉증명서 (백엔드)

루트: `propai-platform/apps/api`. SSH/푸시/프로덕션DB 직접변경 없음. 멱등 신규테이블 + 기존자산 재사용. 로컬검증 완료.

## 1. 조사·재사용
| 용도 | 재사용 자산 | 비고 |
|------|-------------|------|
| 근무기간/현장 | `database/models/sales/site_org.py` `SalesOrgNode(user_id·active·created_at)` + `SalesOrgMembershipHistory(node_id·action·at)` | active·created_at 로 위촉, history.action='LEAVE'(있으면) 로 해촉일. 현재 코드베이스는 action='MOVE'만 기록 → LEAVE 없으면 period_end=None(PDF '-') |
| 소득/원천징수 | `sales_commission_payouts(gross/withholding/net)` (payout→claim→split→event.site, claimant_node.user 매칭) | 폴백: `sales_withholding_statements(payee_node_id→user)` 집계 |
| 직인 이미지 | 기존 `/api/v1/uploads/image`(app/routers/uploads.py → storage_service) | 프론트가 업로드 후 받은 public URL을 issuer 등록 시 `stamp_url`로 전달(백엔드 신규 업로드 0) |
| PDF | reportlab 한글 CID(`HYSMyeongJo-Medium`), `land_intelligence/desk_appraisal_pdf.py` 패턴 | 지연 import(미설치 환경 import 안깨짐) |
| 해시체인 | `ledger/analysis_ledger_service.append_analysis` | best-effort, content_hash → cert.ledger_hash 저장 |
| 컨텍스트/격리 | `deps_sales.sales_ctx` / `require_role`(site·user 격리, RLS 세션변수) | |
| 라우터 패턴 | `endpoints/sales/commission_agreement.py`(_ensure DDL+raw SQL+_ledger) | 동형 패턴 채택 |

## 2. 신규/변경 파일·엔드포인트
- 신규 `app/services/sales/cert/__init__.py`
- 신규 `app/services/sales/cert/termination_cert_pdf.py` — `build_termination_cert_pdf(cert, fetch_stamp)`, `mask_rrn()`
- 신규 `app/api/endpoints/sales/termination_cert.py` — `termination_cert_router`
- 변경 `app/api/endpoints/sales/__init__.py` — import + `include_router(termination_cert_router)`

엔드포인트(prefix `/api/v1/sales`):
| 메서드 | 경로 | 권한 | 설명 |
|--------|------|------|------|
| POST | `/cert/issuers` | 발급주체(SUPERADMIN/DEVELOPER/AGENCY/GM_DIRECTOR) | 발급주체(법인)·직인url 등록 |
| GET | `/cert/issuers` | sales_ctx | 현장 발급주체 목록 |
| POST | `/cert/issue` | 발급주체 | 발급(개별=targets1, **일괄=targets다건**), 근무이력·원천징수 자동채움 → 레코드+해시 |
| GET | `/cert/my-history` | sales_ctx | 내 근무이력(현장·기간 자동) |
| POST | `/cert/request` | sales_ctx | 발급신청(개별/일괄 sites[]), 본인 근무현장만 |
| GET | `/cert/my-requests` | sales_ctx | 내 신청 현황 |
| GET | `/cert/my-certs?year=&site_id=` | sales_ctx | 발급받은 증명서(연도·현장 필터) |
| GET | `/cert/{cert_id}/pdf` | 본인/현장발급관리자 | 개별 PDF(inline) |
| POST | `/cert/bulk-pdf {ids:[]}` | 본인/현장발급관리자 | **일괄 PDF — zip(stdlib zipfile, 신규의존성0)**. 접근불가 항목 조용히 제외 |

## 3. _ensure 테이블·로직
멱등 `_ensure(db)`: `cert_issuers`(site/issuer_type/company_name/biz_reg_no/ceo_name/stamp_url), `termination_certificates`(certificate_no/issuer/site/freelancer/period/payee/income·withholding·net/tax_year/pdf_url/ledger_hash/status), `cert_requests`(site/freelancer/period/status/certificate_id). `gen_random_uuid()` 기본값, 기존 sales 테이블 무파괴.
- 발급: target별 `_work_history`(period 자동)+`_income_for`(소득 자동) → INSERT → `_ledger('issued')` → ledger_hash UPDATE → 동일 user 동일현장 PENDING 신청을 ISSUED 연결. site 격리(현재 컨텍스트 현장으로만).
- 신청: 본인 근무이력 있는 현장만 수락(없으면 skip).
- bulk-pdf: 각 cert `_can_access_cert` 통과분만 zip writestr, 0건이면 403.

## 4. 정직성·마스킹
- 주민번호 `mask_rrn`: 13자리 → `YYMMDD-1******`(성별 1자리만 노출). PDF에만 마스킹 표기, 평문 저장 컬럼 없음.
- "법정 통일양식 아님·연말정산/세무신고 참고용" PDF 본문 명시.
- 직인=전자문서법 준거(이미지 첨부)+무결성 해시체인(ledger_hash, PDF에 표기).
- 격리: `_can_access_cert`=본인(freelancer_user_id) 또는 동일현장 발급관리자만. 발급은 컨텍스트 현장 한정. bulk-pdf 타인 항목 무노출.

## 5. 로컬검증(.venv, 프로덕션DB/외부호출 없음)
- py_compile 4파일 OK.
- 전체 앱 부팅 → cert 라우트 9개 마운트 확인.
- DDL 3종 + 근무이력/소득 SELECT → sqlglot(postgres) 파싱 OK(검증 후 sqlglot 제거).
- PDF: 더미 cert → 4165 bytes `%PDF` 헤더, 한글 렌더 OK. mask_rrn 3케이스 OK.
- 접근격리: owner/현장admin 허용·cross-site/non-owner 차단 OK. bulk zip 3건 멀티 PDF OK.
- reportlab(요구사항 선언됨, 로컬 venv 누락분만 설치=요구사항 정합). sqlglot 테스트용 제거.

## 6. 커밋
`feat(sales-cert): Phase1-F 전자 해촉증명서 — 발급주체/직인·일괄발급·근무이력·PDF·해시체인` (해시는 커밋 후 기재)

## 7. 프론트/QA 정합
- 직인 등록: 프론트가 `/api/v1/uploads/image`로 직인 업로드 → URL을 `POST /cert/issuers {stamp_url}`로 전달.
- 발급 화면(발급주체): 직원목록 선택 → `POST /cert/issue {issuer_id, targets:[{user_id,(period?·payee?·tax_year?)}]}`. 자동채움이라 period/income 생략 가능.
- 프리랜서 화면: `GET /cert/my-history`(현장·기간) → `POST /cert/request {sites:[]}` → `GET /cert/my-certs?year=&site_id=` → 개별 `GET /cert/{id}/pdf`(inline) / 일괄 `POST /cert/bulk-pdf {ids:[]}`(zip 다운로드, blob).
- 응답 키: my-certs item={id,certificate_no,site_id,site_name,period_start/end,income_total,withholding_total,net_total,tax_year,issued_at,issuer_company_name}.
- 모든 cert 라우터는 site 컨텍스트 필요 → 헤더 `X-Site-Code`(또는 경로) + `X-Site-Token` 전달 규약 동일.
- QA: my-certs `year` 필터는 tax_year OR issued_at연도 OR조건. bulk-pdf는 application/zip(타입 분기 주의). reportlab 미설치 시 503.
