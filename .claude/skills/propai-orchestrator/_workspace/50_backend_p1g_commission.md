# Phase 1-G — 수수료 더치페이 (합의기반 분배 + 다자동의 + 변경재동의 + 해시체인) 백엔드

루트: `propai-platform/apps/api`. SSH배포·push·프로덕션DB 변경 없음. 구현+로컬검증+commit 완료.

## 1. 기존 수수료 구조 조사 · 재사용 범위

기존 모델(`database/models/sales/commission_mh_harness.py`, `commission_ext.py`):

| 테이블 | 용도 |
|--------|------|
| `sales_commission_master` | 현장 수수료 총액 기준(basis: FIXED/RATE/POOL) |
| `sales_commission_distribution` | 조직노드별 분배 규칙(distributor→target, FIXED/RATE) |
| `sales_commission_events` | 계약별 수수료 발생 이벤트 |
| `sales_commission_splits` | event 기준 **계산 결과**(node·rate·amount) |
| `sales_commission_claims` / `_approvals` | 청구 → 승인 1단 결재 |
| `_payouts` / `_clawbacks` / `_settlements` / `_payout_schedule` / `_holdback` | 지급·환수·정산·스케줄·유보 |

**재사용 판단**: 기존 `splits`는 event 기준 "산출값" 저장용이고, `approvals`는 claim 1건당 단일 승인자 결재다. **더치페이가 요구하는 "참여자 다자 합의 + 참여자별 서명 + 변경 시 전원 재동의 + 합의 상태머신"** 개념(pending/confirmed/rejected, 동의 무효화, 버전)이 없다. 따라서 합의/동의 전용 2테이블을 멱등 신규 생성(기존 무파괴). 검증 헬퍼·SalesCtx·해시체인은 기존 패턴을 그대로 재사용.

재사용한 인프라:
- `app/api/deps_sales.py` — `SalesCtx`(site 격리), `sales_ctx`(인증·역할·RLS set_config), 역할상수
- `app/services/ledger/analysis_ledger_service.append_analysis()` / `get_latest()` — 해시체인 원장
- `site_auth.py`의 `_ensure(_DDL)` 멱등 테이블 패턴 그대로 차용

## 2. 신규/변경 파일 · 엔드포인트

**신규**: `app/api/endpoints/sales/commission_agreement.py` (`commission_agreement_router`)
**변경**: `app/api/endpoints/sales/__init__.py` (import + `include_router`)

prefix `/api/v1/sales`:
| 메서드 | 경로 | 기능 |
|--------|------|------|
| POST | `/commission/agreements` | 합의 생성(참여자·비율/금액·계약·총수수료) → pending |
| POST | `/commission/agreements/{id}/consent` | 본인 동의 → 전원 시 confirmed |
| POST | `/commission/agreements/{id}/reject` | 본인 거부 → rejected |
| PATCH | `/commission/agreements/{id}` | 분배 변경 → 동의 전부 리셋·재동의 필요(pending) |
| GET | `/commission/agreements?contract_id=` | 목록(계약별) |
| GET | `/commission/agreements/{id}` | 상세(상태·동의현황·해시) |

신규 멱등 테이블(`_ensure`, CREATE TABLE IF NOT EXISTS):
- `sales_commission_split_agreements` — id·site_id·contract_id·total_amount·basis(RATIO/AMOUNT)·status·version·created_by·timestamps·confirmed_at
- `sales_commission_split_consents` — agreement_id(FK CASCADE)·participant_seq·user_id·node_id·ratio·amount·status·decided_at·decided_round

## 3. 다자동의 · 변경재동의 · 해시체인 로직

- **생성**: 검증 통과 후 agreement(status=pending, version=1) + 참여자별 consent(pending) 적재.
- **동의**: `UPDATE consents SET status='consented', decided_round=version WHERE agreement_id AND user_id` → rowcount=0이면 비참여자(403). 직후 `count(consented)==count(*)` 이면 agreement status=confirmed + confirmed_at.
- **거부**: 본인 consent=rejected + agreement status=rejected.
- **변경(재동의 강제)**: consents 전체 DELETE 후 새 명단 재적재(전원 pending), agreement total/basis 갱신 + `version+1` + status=pending + `confirmed_at=NULL`. → 기존 동의 전부 무효화되어 전원 재동의해야 재확정. 일방 변경 차단(상태가 pending으로 되돌아감).
- **해시체인**: created/consented/confirmed/amended/rejected 각 이벤트를 `append_analysis(analysis_type="commission_agreement", project_id=agreement_id, payload={event, 분배스냅샷})` best-effort 기록(실패해도 본 흐름 무영향). GET 상세에서 `get_latest`로 최신 content_hash 부착(변조탐지·분쟁증거).

## 4. 비율/금액 검증 (`_validate_participants`)

- 빈 참여자/총액≤0 거부. 각 참여자 user_id|node_id 필수.
- ratio와 amount **혼용 금지**(둘 다 있으면 400).
- RATIO: 전원 ratio 필수·음수금지·**합=100%(±0.01)**.
- AMOUNT: 전원 amount 필수·음수금지·**합=total_amount(±1원)**.
- 통과 시 basis('RATIO'|'AMOUNT') 반환.

## 5. 로컬 검증 (.venv, 프로덕션DB·외부호출 없음)

- AST 구문 OK (신규 + `__init__`).
- 라우트 등록 OK — agreement 6개 라우트 mount, 전체 app import OK(11 agreement routes, mlflow 경고는 기존 무관).
- 단위(스텁) — 비율합100 OK / 비율합≠100 거부 / 금액합=총액 OK / 금액합≠총액 거부 / 혼용 거부 / id없음 거부 / 빈참여자 거부 / 총액0 거부 / 음수비율 거부 / 오차범위(99.9~100.01) 통과. `_is_participant`·`_hash_inputs` OK.
- 상태머신(SQLite 재현) — 생성(pending)→u1동의(pending)→비참여자 동의차단(rowcount0)→u2동의(confirmed)→변경(동의리셋·version2·pending)→재동의 전원(confirmed)·decided_round=2 추적 OK.

## 6. 커밋

`feat(sales-commission): Phase1-G 수수료 더치페이 — 합의기반 분배·다자동의·변경재동의·해시체인`
(해시는 보고 본문 참조)

## 7. 프론트/QA 정합 (응답 스키마)

모든 합의 응답(생성/동의/거부/변경/상세)은 동일 구조:
```jsonc
{
  "id","site_id","contract_id","total_amount","basis","status","version",
  "created_by","created_at","updated_at","confirmed_at",
  "participants":[{"seq","user_id","node_id","ratio","amount","status","decided_at","decided_round"}],
  "consent_progress":{"consented","total","all_consented"},
  "ledger":{"version","content_hash","created_at"}  // GET 상세만, 있을 때
}
```
목록: `{"items":[<agreement>...], "count"}`.
- status: `pending|confirmed|rejected`, participant status: `pending|consented|rejected`, basis: `RATIO|AMOUNT`.
- 요청 바디: create `{contract_id, total_amount, participants:[{user_id?|node_id?, ratio?|amount?}]}`, patch `{participants, total_amount?}`. consent/reject 바디 없음(본인=현장토큰 사용자).
- 권한: 생성/변경=현장 관리자(SUPERADMIN/DEVELOPER/AGENCY/GM_DIRECTOR/DIRECTOR) 또는 변경은 참여자도 가능(전원 재동의 강제), 동의/거부=참여자 본인. site 격리(SalesCtx.site_id)·RLS set_config 정합.
