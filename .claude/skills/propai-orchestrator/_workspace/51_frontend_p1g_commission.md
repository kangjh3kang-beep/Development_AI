# Phase 1-G — 수수료 더치페이 프론트엔드 (합의·다자동의·변경재동의·해시체인)

루트: `propai-platform/apps/web`. push 없음. 구현 + tsc/eslint + 로컬 커밋 완료.

## 1. 신규/변경 파일 · 배치
- **신규** `components/sales-app/CommissionDutchPay.tsx` — 더치페이 합의 UI(타입 동봉).
- **변경** `components/sales-app/SiteWorkspaceClient.tsx` — 수수료 탭(`tab === "commission"`)에
  기존 `CommissionBoard` 아래 구분선 + `CommissionDutchPay`를 추가(무파괴 결합). import 1줄 추가.

배치 근거: 1-B 워크스페이스(`SiteWorkspaceClient`)가 기존 `components/sales/*` 패널을 탭별로
렌더하는 구조. 수수료 탭에 기존 1단/2단 배분(CommissionBoard)과 "더치페이 분배 합의"를 한 탭에 병치.

## 2. 합의생성 · 동의진행 · 변경재동의 · 무결성 표시
- **합의 생성**: 계약 select(`GET /contracts`) + 총 수수료(NumberInput) + basis 토글(비율%/금액원) +
  참여자 추가(`GET /org/tree` 조직노드 → node_id). 참여자별 카드(아바타·이름·비율/금액 입력·제거).
  실시간 합계바: 비율 합 100%(±0.01) / 금액 합 = 총액(±1원) 검증, 불일치 시 rose 경고·제출 비활성.
  "÷ 1/N 균등분배" 헬퍼(잔여 마지막 참여자 보정). `POST /commission/agreements`.
- **동의 진행**: 합의 카드에 status 배지(pending=amber/confirmed=emerald/rejected=rose),
  `consent_progress.consented/total` 진행바(% 폭, 거부 시 rose 100%, 전원동의 시 emerald),
  헤더에 `n/total 동의`. 펼침 시 참여자별 동의상태(동의 emerald·대기 amber·거부 rose 점+라벨).
- **동의/거부**: 펼친 상세에서 "✓ 내 분배에 동의"(`POST /{id}/consent`), "✕ 거부"(`POST /{id}/reject`).
  본인 식별은 백엔드(`_is_participant`, user_id=ctx.user.id)가 담당 → 비참여자 403을 안내문구로 처리
  (프론트는 user_id를 알 필요 없음 = 안전).
- **변경 제안(재동의)**: "✎ 분배 변경(재동의)" → 폼에 기존 참여자/분배 프리필 + amber 배지
  "변경 시 전원 재동의 필요" + notice 안내. `PATCH /{id}` {participants, total_amount} →
  백엔드가 동의 전부 리셋·version+1·pending. (basis는 변경모드에서 잠금 — 백엔드가 분배값으로 basis 재판정)
- **무결성(해시체인)**: 상단 `TrustBadge`(라벨 "합의·변경 이력 위변조 방지(해시체인)") 재사용 +
  상세 하단에 `ledger.content_hash` 24자 + version 봉인 표시. GET 상세에만 ledger가 오므로 펼침 시 노출.
- 로딩(스켈레톤)/에러(rose 배너)/권한(403→"참여자 아님"·"관리자만") 분기 처리.

## 3. site_token 사용
`salesApi(siteId)` 사용 → 저장된 site_token(1-A)이 있으면 `X-Site-Token` 자동 첨부.
모든 호출(contracts/org-tree/agreements/consent/reject/patch)이 sales 프리픽스 경로로 site 격리.
`apiClient` import는 `ApiClientError`(403 분기)용으로만 사용, salesApi가 실제 호출 래핑.

## 4. tsc / eslint
- `npx tsc --noEmit` → **EXIT 0** (전체 web).
- `npx eslint CommissionDutchPay.tsx SiteWorkspaceClient.tsx` → **EXIT 0**(경고/에러 0).

## 5. 커밋
`b281a09` feat(sales-commission): Phase1-G 수수료 더치페이 UI — 합의·다자동의·해시체인 신뢰
(2 files changed, 820 insertions, 1 deletion). 명시경로 add(-A 금지). push 없음.

## 6. 백엔드 정합 (84ec147 스키마 대조)
- 요청: create `{contract_id, total_amount, basis, participants:[{node_id|user_id, ratio|amount}]}` ✓,
  patch `{participants, total_amount?}` ✓, consent/reject 바디 없음 ✓.
- 응답 타입 일치: `Agreement{id,site_id,contract_id,total_amount,basis,status,version,participants[],
  consent_progress{consented,total,all_consented},ledger?{version,content_hash,created_at},created_by,
  created_at,confirmed_at}`, participant `{seq,user_id,node_id,ratio,amount,status,decided_at,decided_round}` ✓.
- 목록 응답 `{items:[],count}` ✓ (GET ?contract_id=).
- enum: status pending|confirmed|rejected, consent pending|consented|rejected, basis RATIO|AMOUNT ✓.
- 검증식 동일: RATIO 합 100%±0.01, AMOUNT 합=total±1 — 프론트 사전검증으로 400 왕복 최소화.

## 7. 잔여/주의
- 참여자 추가는 조직노드(org/tree) 기준. user_id 직접 지정 UI는 미노출(현장 user 목록 API 부재) —
  필요 시 백엔드 user 목록 엔드포인트 추가 후 확장.
- basis 변경(RATIO↔AMOUNT)은 변경모드에서 잠금. 다른 기준으로 재합의하려면 신규 생성 권장.
