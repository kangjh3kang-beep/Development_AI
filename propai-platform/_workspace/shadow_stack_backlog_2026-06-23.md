# 백로그: deliberation-integration shadow 관측 스택 재배선 (전용 후속작업)

출처: origin/feature/deliberation-integration (behind=349, CHERRY_PICK 권고)
처리됨: ceil 버그픽스(a4891172) → main 체리픽 완료(28fdfb83).
보류(이 백로그): shadow divergence / reg-divergence 관측 스택 — 비-clean 통합이라 분리.

## 가져올 파일(브랜치에 존재, main 미보유 = 신규)
- apps/api/app/services/deliberation/shadow_service.py (self-contained, raw SQL via async_session_factory)
- apps/api/app/services/deliberation/shadow_integration.py
- apps/api/app/services/deliberation/shadow_mappers.py
- apps/api/app/services/deliberation/reg_reconcile.py
- apps/api/database/migrations/versions/033_shadow_comparison.py (★DB 마이그레이션 — 라이브 실행 필요)
- apps/web/components/deliberation/ShadowConvergenceCard.tsx (+ .test)
- apps/web/components/deliberation/RegDivergenceCard.tsx (+ .test)
- apps/api/tests/test_deliberation_shadow.py

## 재배선 필요(브랜치의 코어 4파일은 폐기·main 버전 유지)
- apps/api/app/routers/deliberation.py — 브랜치/​main 둘 다 수정(충돌). shadow 엔드포인트를 **main 현행 라우터에 추가**(브랜치 라우터 통째로 가져오지 말 것 — 코어 BFF는 main d9d83973가 정본).
- apps/web/app/[locale]/(dashboard)/deliberation-review/page.tsx — 브랜치/​main 둘 다 수정(충돌). main page.tsx에 `<ShadowConvergenceCard /><RegDivergenceCard />` 2줄 + import 2줄 **추가**.

## 폐기(main이 흡수, superseded)
- _engine_contract.py, binding_service.py (브랜치 버전) — main d9d83973가 독립 풀통합으로 이미 보유.

## 절차(권장)
1. shadow 신규파일 7종 checkout → 2. 033 마이그레이션을 엔진/메인 DB 정합 확인 후 실행 →
3. main deliberation.py에 shadow 엔드포인트 후킹 → 4. main page.tsx에 카드 2개 마운트 →
5. test_deliberation_shadow 통과 → 6. 빌드/배포 → 라이브검증(shadow 수렴/규제괴리 카드 렌더).
