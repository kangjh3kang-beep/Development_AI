# 인계 프롬프트 — field_audit 자가검증 캠페인 (다음 세션에 붙여넣기)

---

PropAI 부동산개발 플랫폼의 **신경-기호 자가검증(field_audit) 캠페인**을 이어받아 마무리해줘. 이전 세션이 Phase0 코드를 전량 완성·머지·배포했고, **라이브검증에서 "완성됐다 믿은 자가검증 레이어가 프로덕션에서 안 돌고 있음"을 발견**해 통합자 게이트에서 멈춘 상태다.

## 현재 상태
- **완료(전량 main 머지)**: field_audit W0~W3-2 = 10PR(#483~#493 + 가드 #497). 6모듈·8규칙 — G1 보호구역리스크·G2 학교POI dedup·G3 관리지역커버리지·PROV_UNKNOWN/PROV_STALE(provenance)·MARKET_PRICE_METHODOLOGY(시세방법론)·TERRAIN_SLOPE_COLLECTION_GAP(경사도)·SALE_PRICE_POINT_ESTIMATE(분양가). `comprehensive_analysis_service.analyze()` :1103에 관측전용 배선. + 배포가드 #497(`GET /api/v1/data-integrity/field-audit-status` 무인증 공개 + `scripts/smoke_field_audit.sh`) + #500(safe-deploy 롤백자산).
- **★미결(통합자 유일 게이트)**: field_audit이 프로덕션에서 **미활성**. 공개 `https://4t8t.net/openapi.json`에 `field-audit-status` 라우트가 **없음** = 공개 활성 168이 **#497 이전 구코드**를 서빙 중(통합자가 11:30 배포한 10493616은 git상 #497 포함이나, blue-green/Caddy가 공개 트래픽을 신규 이미지 인스턴스로 전환하지 못함).

## STEP 1 — 게이트 해소됐는지 확인 (제일 먼저)
```bash
curl -s https://4t8t.net/api/v1/data-integrity/field-audit-status
```
- **404 / {"detail":"Not Found"}** → 통합자가 아직 공개 인스턴스 미전환. `scripts/coord.sh status`로 통합자 배포 note 확인·대기. ★SSH 168(134.185.104.167/.168)은 에이전트 환경서 네트워크 차단(Oracle 보안리스트)이라 진단 불가 — 통합자 도메인.
- **{"enabled":true,"rules_registered":8,...}** → **활성!** STEP 2 진행.

## STEP 2 — 게이트 해소 시 라이브검증 마무리
1. agent-browser 세션 복원(로그인 상태 유지됨): `npx agent-browser --session-name propai open https://4t8t.net`. 인증키=localStorage `propai_access_token`. (테스트계정 test@4t8t.net·**비밀번호는 채팅이력에만·파일/커밋 저장금지·출력금지**.)
2. 인증 브라우저 컨텍스트에서 analyze API 직호출 — ★**fire-and-poll 패턴**(분석 ~130초·CF 524 주의·동기 eval 타임아웃): `window.fetch('/api/v1/analysis/comprehensive', {method:POST, headers:{Authorization:'Bearer '+localStorage.propai_access_token}, body: JSON.stringify({address:"경상북도 포항시 남구 호미곶면 대보리 100", parcels:[{pnu,address,area_sqm,zone_type}]})})` 를 window에 저장 후 폴링.
3. **검증 항목**: (a) `result["field_audit"]` 부착 + `is_valid` + `rules_registered` (b) 골든 대응 필지로 예상 8규칙 findings (c) ★호미곶(군사보호구역 임야) **종합 리스크 낮음→높음**(G1 protection_zone_severity 실제수정 라이브 확증). 관리지역(G3)·분양가(점추정)·경사도(G6)도.

## 참조·규율
- **인계문서**: 옵시디언 `AI-Sessions/conversations/2026-07-30_field_audit_campaign_handoff.md`
- **런북**: repo `_workspace/RUNBOOK_field_audit_prod_inactive_2026-07-29.md`
- **정본계획**: repo `_workspace/PLAN_neuro_symbolic_selfaudit_integration_2026-07-24.md`
- **★교훈**: 배포검증은 반드시 **공개 endpoint/openapi**로(localhost·이미지ID는 Caddy 라우팅 미반영). **검증 도구도 적대검증 필수**(이 캠페인서 가드 masking·가짜 G5골든·워치 스크립트 버그 연속 재발). `/insight-loop` 규율(ground-truth→다렌즈→dispose→loop) 적용.
- **사용자 결정**: **토대 우선** — field_audit 프로덕션 활성·검증 전엔 새 웨이브(W3-1 LLM auditor·W4 퍼저) 미착수.
- **멀티세션**: 배포는 통합자 단일 담당·main 직접 push 금지·전용 워크트리(`scripts/new-worktree.sh`)·`scripts/coord.sh` claim/release. venv=`propai-platform/.venv`(py3.12). 커밋 서명 `Co-Authored-By: Claude Fable 5`.

## 게이트 해소·검증 완료 후 후속 (사용자 스티어링 필요)
W3-1(LLM auditor·첫 LLM티어·과금/비결정성 결정점) / W4(Proactive Fuzzer·자가치유) / CF524 동기분석 타임아웃 개선.
