# D3 — 설계변경 사전예측 + 보완방안 (백엔드)

착공 전에 설계변경을 유발할 리스크(법규초과·필수요소 누락·정량 정합성 모순)를
미리 예측하고 보완방안(절감 포함)을 제시한다. 룰기반 우선, AI 보조(use_llm시만).

## 1. 변경/신규 파일·엔드포인트·마운트

| 구분 | 경로 |
|------|------|
| 신규 서비스 | `apps/api/app/services/design_risk/design_change_predictor.py` (본체) |
| 신규 패키지 | `apps/api/app/services/design_risk/__init__.py` |
| 신규 라우터 | `apps/api/app/routers/design_risk.py` (prefix `/api/v1/design-risk`) |
| 마운트 | `apps/api/main.py` (design_v61 블록 직후 독립 try/except로 격리 마운트) |
| 엔드포인트 | `POST /api/v1/design-risk/predict` |

재사용(무파괴):
- `building_code_rules.ZONE_DEFAULTS / PARKING_REQUIREMENTS` — 법정 한도·주차 기준
- `auto_zoning_service.ZONE_LIMITS` — 용도지역 한도(height None=무제한 권위 소스)
- `auto_zoning_service.AutoZoningService.analyze_by_address` — 좌표→용도지역·대지면적 보강
- `cost_monte_carlo.RISK["design_chg"]` (0.00,0.05,0.15) → 설계변경비 정성 표기(+5~15%)
- `ai/base_interpreter.BaseInterpreter._invoke` — AI 보완전략(캐시·그라운딩·90초 가드)

## 2. 3종 예측 로직·임계

### A. 법규초과 예측 (`_predict_overrun`)
현 설계(건폐율/용적률/높이) vs 법정 한도.
- **초과**(current > limit) → severity `high`, 축소율·완화 인센티브 보완안 + est_impact(설계변경비)
- **근접**(current ≥ limit × 0.95, `_NEAR_LIMIT_RATIO`) → severity `warn`, 안전마진 권고
- height는 ZONE_LIMITS의 `max_height_m`(None=무제한 = 상업지역 등)면 미적용

### B. 누락 예측 (`_predict_missing`) — 룰기반 체크리스트
- **법정주차**: `PARKING_REQUIREMENTS` 기준 산정(세대×per_unit 또는 GFA÷per_sqm).
  미입력→`high`(미계획), 부족→`high`(부족 대수·보완)
- **직통계단 2개소**: 5층↑ 또는 층당면적(GFA/floors)>200㎡ → `warn` (건축법 시행령 §34)
- **특별피난계단**: 16층↑ → `warn` (§35)
- **승강기**: 6층↑ → `info` (건축법 §64)
- **장애인 편의시설**: 공동주택 20세대↑ / 근생·오피스텔 500㎡↑ → `warn` (장애인등편의법 §4)
- **부대복리시설**: 공동주택 150세대↑ → `info` (주택건설기준)

### C. 간섭/정합 예측 (`_predict_consistency`) — 정량 정합만(3D clash 범위 외)
- **높이-층수 불일치**: 입력 height < floors×floor_height × 0.9 → `warn` (입력오류 추정)
- **세대-면적 모순**: units×avg_unit > GFA(전용률>100% 물리적 모순) → `high`;
  전용률>90% → `warn`(코어 과소 추정)
- **건폐율-면적 불일치**: |건축면적/대지 − 입력 bcr| > 5%p → `warn`

각 리스크: `{category, item, severity, current, limit?, detail, remedy, est_impact?}`.
remedy는 "착공 전 저비용 조치 vs 착공 후 고비용 위험" 대비로 작성.

## 3. 보완방안·AI 폴백
- **룰기반 remedy**: 모든 리스크에 항상 결정적으로 부착(LLM 불필요).
- **AI 통합전략**(`generate_ai_remedies`, use_llm시만): `_RemedyInterpreter(BaseInterpreter)`로
  `priority_actions / savings_opportunity / expert_review_note` 생성.
  asyncio.wait_for·90초·캐시·그라운딩(base_interpreter `_invoke`) 그대로 사용.
- **폴백 보장**: 키 미설정·예외·부분응답 시 룰기반 dict로 폴백, 누락 키는 setdefault로 채움.

## 4. 로컬 시나리오 검증 (`.venv`)
- AST OK / 풀앱 import·라우트 마운트 OK (`/api/v1/design-risk/predict`)
- **S1 과밀**(bcr75/far320 vs 제2종일반 60/250): 건폐율·용적률 초과 high 2건 ✓
- **S2 주차부족**(20/50세대): 법정주차 부족 high ✓
- **S3 세대-면적 모순**(30×60=1800㎡ > GFA 1000㎡): 간섭정합 high ✓
- **S4 정상**(소규모 다세대, 층당180㎡<200): high 0 / warn 0 ✓
  (4층·층당450㎡는 §34 직통계단 warn이 **정상** 발생 — 룰 정확)
- **AI 폴백**: 키 없이 3키 폴백 dict 반환 ✓
- **엔드포인트 E2E**: A(과밀→ok·high 3) / B(빈입력→ok:false) ✓
- **실주소**(강남 테헤란로 152): 좌표→auto_zoning 용도지역(제2종일반)·높이 층수추정 보강→예측 ✓

## 5. 커밋
`feat(design-risk): D3 설계변경 사전예측 — 누락·간섭·법규초과 + 보완방안(절감)`
(해시는 커밋 후 본 문서 하단 갱신)

## 6. 프론트/QA 정합 — 응답 스키마
```jsonc
{
  "ok": true,
  "address": "…",
  "zone_type": "제2종일반주거지역",
  "summary": { "high": 3, "warn": 2, "info": 1, "total_predicted_impact_note": "…정성·추정" },
  "risks": [
    { "category": "법규초과|누락|간섭정합", "item": "건폐율 초과",
      "severity": "high|warn|info", "current": "75.0%", "limit": "60%",
      "detail": "…", "remedy": "…보완방안", "est_impact": "…정성(공사비/공기)" }
  ],
  "ai_remedy": { "priority_actions": "…", "savings_opportunity": "…", "expert_review_note": "…" } | null,
  "badges": { "note": "사전예측·확정아님·전문가검토필요…3D 간섭 범위 외", "data_basis": "룰기반…(+AI 보조)" },
  "limits_used": { "max_bcr": 60, "max_far": 250, "max_height_m": null },
  "data_gaps": ["…미입력/추정 보강값"],
  "sources": ["auto_zoning_service(VWorld/NED)", "…"]
}
```
- 카테고리값(법규초과/누락/간섭정합)·severity(high/warn/info)는 프론트 배지/필터 키와 1:1.
- `ok:false`는 `{ok, error, badges}` (좌표·설계 둘다 불가 시).
- 정직성: `badges.note`에 "확정아님·전문가검토필요·3D clash 범위 외" 항상 명시.
