# Phase 1-D — 고객관리 강화 (백엔드)

분양 현장앱 고객관리: 카드 히스토리·문자/알림톡·업무일지 + 현장별/통합(union) 뷰.

## 1. 기존 자산 조사
- **고객 테이블**: `sales_customers`(contract_crm_ad.py) — `name, phone_e164, source, status(LEAD 기본), grade, assigned_node_id, first_visit_at`. SoftDelete(deleted_at). 단계=status, 온도=grade(A/B/C).
- **CrmPanel 호출 계약**(web/components/sales/CrmPanel.tsx): `GET /crm/grade-suggestions`(views.py, AI 등급예측), `POST /customers`, `PATCH /customers/{id}`, `POST /consultations`. → 전부 유지(무파괴), 신규는 추가형.
- **문자/알림톡**: `app/services/sales/mh/notify.py`(MH 데스크용 FCM/알림톡). 키=`sales_settings.kakao_biz_key/kakao_sender_key`(config_sales.py). 키 미설정 시 graceful skip 패턴. → CRM 발송은 동일 키·패턴 재사용(전용 `_dispatch_message`).
- **멤버십(union)**: `SalesOrgNode(site_id, user_id, active, node_type, deleted_at)`(site_org.py). 내 멤버십 현장목록 = active 노드 site_id 집합 + (시행사/슈퍼/소유테넌트 폴백).
- **컨텍스트/역할**: deps_sales.py — `sales_ctx`(X-Site-Code/X-Site-Token→site_id·role), `resolve_site`, `require_role`. 통합뷰는 단일 site 토큰 전제와 충돌 → **`get_current_user` 전역 로그인으로 멤버십 union 조회**, 현장별 역할범위 적용.
- **커밋패턴**: commission_agreement.py — `_ensure`(멱등 DDL) + raw SQL(text()) + `db.commit()`.
- **기존 `SalesWorkLog`**: 이미 존재(commission_mh_harness.py, `sales_work_logs`: author_node_id/log_date/content/metrics, CRUD `/work-logs` 노출). → 신설 대신 **컬럼 멱등 ALTER**로 user_id/summary/activities/created_at 보강.

## 2. 신규/변경 파일·엔드포인트
- 신규 `app/api/endpoints/sales/crm_enhance.py` (`crm_enhance_router`)
- 변경 `app/api/endpoints/sales/__init__.py` (import + include_router 2줄)

엔드포인트(prefix `/api/v1/sales`):
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/my-customers?scope=all\|site&site_id=&stage=&q=` | 현장별/통합 고객 목록 |
| GET | `/customers/{id}/history` | 카드 타임라인 |
| POST | `/customers/{id}/history` `{kind, content, stage_to?}` | 상담/방문/메모/단계변경(단계변경 시 status 갱신) |
| POST | `/customers/{id}/message` `{channel, template?, body}` | 문자/알림톡 발송(동의가드) |
| POST | `/work-logs` `{log_date, summary, activities[], site_id?}` | 업무일지 작성(활동→고객 history 연계) |
| GET | `/work-logs?from_=&to=&site_id=` | 업무일지 목록(기간/현장) |
| GET | `/work-logs/summary?period=&site_id=` | 실적집계(상담/방문/계약/메시지/일지수) |

## 3. _ensure 테이블 / scope union / 히스토리 / 메시지 동의가드 / 업무일지 집계
- **_ensure**(멱등): `sales_customer_history`(id,customer_id,site_id,actor_user_id,kind,content,stage_from,stage_to,created_at + 인덱스), `sales_message_log`(id,customer_id,site_id,actor_user_id,channel,template,body,status,consent_checked,sent_at), `sales_work_logs` 컬럼 ALTER ADD IF NOT EXISTS(user_id,summary,activities,created_at).
- **scope union**: `_my_site_roles(db,user)` → `{site_id: role}`. scope=site=단일현장(역할범위, 상세 허용), scope=all=멤버십 전현장 union(요약필드만, 연락처 마스킹). 타현장 차단=`_load_customer_in_scope` site 검증.
- **히스토리**: append-only. kind=stage 시 stage_to 검증(_STAGES 화이트리스트)+`sales_customers.status` 갱신+stage_from/to 기록.
- **메시지 동의가드**(3중): ①MARKETING 수신동의(`sales_customer_consents.agreed=true AND withdrawn_at IS NULL`) 없으면 BLOCKED. ②야간(21~08) 광고성 BLOCKED. ③발신번호(kakao_sender_key) 미등록 시 SKIPPED(안전 폴백·기록만). 통과 시 `_dispatch_message`(notify 패턴, alimtalk 키 없으면 SKIPPED, 예외 FAILED). 모든 결과 message_log + history(kind=message) 이중기록. 응답에 opt_out_notice(080).
- **업무일지 집계**: `/work-logs/summary` — 내가 actor인 history를 period(day/week/month/quarter/year) 윈도로 kind별 카운트, stage_to∈{RESERVED,SIGNED,MIDDLE,BALANCE}=contracts. work_logs 작성수 별도. by_site + total.

## 4. 정직성 / 정보통신망법
- 통합(all) 뷰=개인범위 **요약(이름·현장·단계·온도)만**, 연락처는 `_mask_phone`(010****5678)로 마스킹. 민감상세는 현장별(site) 진입(X-Site-Token 2차인증 컨텍스트=`sales_ctx`)에서만 평문 노출.
- 멤버십 검증: `_my_site_roles`에 없는 현장 고객/일지 접근 403. 타현장 무단노출 차단.
- 정보통신망법 제50조: 사전 수신동의(MARKETING) 확인·저장 / 야간 광고성 제한 / 발신번호 사전등록 전제 / 수신거부(080) 안내. 실제 외부발송은 notify 위임, 키 없으면 발송 안 하고 기록만(할루시네이션 발송 방지).
- RLS 정합: 신규 `sales_customer_history`/`sales_message_log` 모두 site_id 보유 → 기존 sales_ 접두 RLS 부트스트랩 자동매칭(강제 추가코드 불필요, 확인만).

## 5. 로컬 검증
- `.venv py_compile` crm_enhance.py + __init__.py → OK.
- 전체 앱 부팅(`app.main:app`) → 5개 라우트 `/api/v1/sales` 마운트 확인(my-customers/history/message/work-logs/work-logs/summary).
- DDL/ALTER/SELECT `sqlalchemy.text()` 파싱 OK.
- 단위: night_guard(21/23/07=block, 08/12=allow), _mask_phone(010****5678/None/***), _activity_metrics(consult2 visit1 stage1), _json(한글 ensure_ascii=False), _STAGES/_KINDS 멤버십. 프로덕션DB·외부발송 미수행.

## 6. 커밋
- `feat(sales-crm): Phase1-D 고객관리 강화 — 카드 히스토리·문자/알림톡·업무일지·현장별/통합뷰`
- 해시: (commit 단계에서 기입)

## 7. 프론트 계약 / 미진점
- **CrmPanel 확장 포인트**: [현장별]/[통합] 토글 → `GET /my-customers?scope=site|all`. 통합은 `masked=true`(phone_masked만), 현장칩=`sites[]`. 카드 클릭 → `GET /customers/{id}/history` 타임라인 렌더. 기록버튼 → `POST /customers/{id}/history`(kind=consult/visit/note/stage). 문자버튼 → `POST /customers/{id}/message`(응답 status BLOCKED/SKIPPED/SENT + blocked_reason 토스트). 업무일지 화면 → `POST/GET /work-logs`, 대시보드 → `GET /work-logs/summary`.
- 민감상세(연락처)는 통합뷰에서 마스킹 — 프론트는 "현장 진입 후 열람" 유도(X-Site-Token 발급=site_auth).
- 미진점: ①수신동의(MARKETING) 입력 UI는 기존 `/consents` CRUD 사용(본 작업 미포함). ②발신번호 발신프로필 등록 관리화면 미구현(키만 전제). ③실거래 alimtalk 템플릿 사전승인은 운영 외부절차. ④work-logs 목록 쿼리파라미터명 `from_`(파이썬 예약어 회피) — 프론트는 `?from_=` 사용.
