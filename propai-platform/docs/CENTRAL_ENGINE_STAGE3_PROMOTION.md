# 중심엔진 수렴 — Stage 3 (authoritative 승격) 설계

> 전제: Stage 2(shadow 관측)는 완료·gate 통과(design_audit·building_compliance 배선, `feature/deliberation-integration`).
> 본 문서는 shadow divergence 데이터를 근거로 **플랫폼 자체 산출 → 엔진 산출(authoritative)** 로 도메인별 전환하는 기준·메커니즘·롤백을 규정한다. 코드 변경 전 SSOT.

## 0. 원칙
- **데이터 게이트**: 승격은 운영 divergence 관측 후에만. 데이터 없이 cutover 금지(거짓 신뢰·운영 리스크).
- **도메인 단위**: 전역 일괄 금지. 도메인별로 독립 승격·독립 롤백.
- **무중단·가역**: 승격은 feature flag로 토글, 즉시 롤백 가능. 합성 결과 금지(엔진 미연결 시 기존 플랫폼 산출 유지).
- **정직성**: 승격 후에도 degrade/무결성/감사 불변식 유지(Phase 1 BFF 계약 그대로).

## 1. 관측 — divergence 데이터
- 적재: `shadow_comparison`(033). 후킹: design_audit `_execute_run`, building_compliance `/check`(기본 off `deliberation_shadow_enabled`).
- 집계: `shadow_service.divergence_stats(domain=, tenant_id=, min_n=)` →
  `{domain, n, matched_n, match_rate, avg_divergence, avg_quant_rel_err}`.
- 운영 활성화: 배포 + `deliberation_shadow_enabled=on` + 엔진 토큰/URL. 충분 기간 트래픽 누적.

## 2. 승격 게이트(도메인별 정량 기준)
도메인 D를 authoritative로 승격하려면 **전부** 충족:
| 기준 | 임계(초기 권장) | 근거 |
|---|---|---|
| 관측수 n | ≥ 500 (도메인 트래픽 따라 조정) | 통계적 유의 + 희소 케이스 포함 |
| match_rate | ≥ 0.99 | verdict 불일치 1% 이하 |
| avg_divergence | ≤ 0.01 | 잔여 불일치도 경미 |
| 미해결 불일치 분류 | 100% 원인규명 | 남은 1%가 알려진·수용가능 사유(예: scope 한계)인지 |
- 정량 도메인(향후 면적 등): match_rate 대신 `avg_quant_rel_err ≤ 0.005`.
- ⚠️ 현재 shadow는 sanity 성격(엔진이 입력 rule echo) — **진정 승격 가치는 엔진이 독립 산출(reg_graph 한도·geometry_area)을 노출한 뒤**. 그 전 승격은 "엔진 경유"라는 경로 통일 효과만 있고 판정값은 동일. 따라서 우선순위: (a) 엔진 독립 산출 노출(엔진 트랙) → (b) 그 출력으로 shadow 재관측 → (c) 게이트 통과 시 승격.

## 3. 승격 메커니즘
- flag: `deliberation_authoritative_domains: list[str]`(기본 []) — 승격된 도메인만 엔진 결과를 권위본으로 사용.
- 도메인 핸들러: `if domain in authoritative_domains and engine_result_valid: return engine_view else: return platform_view`(+shadow 계속 적재). 엔진 미연결/무결성 실패 → 플랫폼 fallback(무중단)·degrade reason 표면화.
- 엔진 결과 view 변환: 엔진 `report.items/legal_quantities/cross_validations/reg_graph` → 도메인 응답 스키마 매핑(§6 evidence). 평탄화 금지.
- 롤백: flag에서 도메인 제거 → 즉시 플랫폼 산출 복귀(코드 변경·재배포 불요).

## 4. 도메인별 계획(승격 순서)
1. **building_compliance** — 위반 판정(rules) 단순·검증 용이. 엔진 reg_graph 한도 노출 후 1순위.
2. **design_audit** — rules8 기하 subset부터(비수치 parking 등은 플랫폼 유지·부분 승격).
3. comprehensive/drawing — 엔진 독립 정량(reg_graph·geometry_area) 노출 후 재평가(현재 verdict 부재로 보류).

## 5. 단계 체크리스트
- [ ] 엔진: reg_graph 독립 한도 + 산출 정량을 결과에 노출(엔진 트랙·#엔진).
- [ ] shadow 재관측(독립 산출 기반) → divergence_stats 게이트 충족 확인.
- [ ] `authoritative_domains` flag + 도메인 view 변환 + fallback/degrade + 감사.
- [ ] 도메인별 회귀테스트(엔진 view == 기대, 미연결 fallback, 롤백).
- [ ] 9.5 적대리뷰 gate(HIGH 0) 통과 후 도메인 1개 카나리 → 확대.

## 6. 불변식(승격 후에도 유지)
테넌트 격리(#8a·binding), 멱등, 무결성 parity, 감사 fail-closed, degrade 무음0, circuit-breaker. 본 문서는 [CENTRAL_ENGINE_INTEGRATION_DESIGN.md](../services/deliberation-review/docs/CENTRAL_ENGINE_INTEGRATION_DESIGN.md) §5~§9를 승격 단계로 확장한다.
