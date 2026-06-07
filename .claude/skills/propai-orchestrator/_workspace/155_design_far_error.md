# 155 설계 심층분석 용적률 오류 진단 — 일반상업 300/400% 화면내 불일치

조사일: 2026-06-07 / 대상: AI 건축 설계(DesignStudio) 심층분석 / 코드 수정 없음(사실+근본원인)

## 1. 증상 요약
- 일반상업지역인데 법규 적합 체크리스트가 **용적률 300% / 한도 400%** 표시
- 같은 화면 "일조·건축가능 볼륨"은 건축가능 연면적 **2,405㎡(대지 185㎡ → 1300%)** 표시
- 화면 내 용적률 기준 불일치(300/400 vs 1300) + "기본분석(부지/법규)과 상이"

## 2. 핵심 결론(근본원인)
**프론트 zone 테이블은 정상(1300%)이다. 400%는 어떤 테이블에도 없는 LLM 환각이다.**
법규 체크리스트의 300/400 값은 정적 테이블이 아니라 **자유형 LLM 호출 응답(`ai.floorAreaRatio`)** 에서 나온다.
화면내 두 블록이 서로 **다른 데이터 출처**를 쓰기 때문에 불일치가 발생한다.
- 법규 체크리스트/메트릭 카드: LLM(`POST /api/v1/ai/llm`, design 도메인 프롬프트) 응답값 우선
- 일조·건축가능 볼륨(SolarEnvelopeCard): 결정론적 백엔드 `POST /api/v1/site-score/envelope`(SSOT 1300%)

## 3. 데이터 출처 분기(파일:라인)

### A. 메트릭 카드/법규 체크리스트 = LLM 우선 (`?? local` 폴백)
- `apps/web/components/design/DesignStudio.tsx:212` 용적률 카드
  `val: \`${ai?.floorAreaRatio?.value ?? calc.floorAreaRatio}%\`, sub: \`최대 ${ai?.floorAreaRatio?.max ?? calc.floorAreaRatio}%\``
- `apps/web/components/design/DesignStudio.tsx:232` 체크리스트 용적률 행
  `v: ai?.floorAreaRatio?.value ?? calc.floorAreaRatio, max: ai?.floorAreaRatio?.max ?? calc.floorAreaRatio`
- `ai`의 정체: `apps/web/components/design/DesignStudio.tsx:112` `const ai = aiResult?.data;`
  → `useAIAnalyze`(`apps/web/lib/ai-analyze-client.ts:50`)가 `POST /api/v1/ai/llm`로 **자유형 LLM 호출**, 응답 텍스트를 `JSON.parse`(`:59`)해서 `ai`로 사용
- LLM이 채울 스키마: `apps/web/lib/ai-prompts.ts:98` `"floorAreaRatio": { "value": 0, "max": 0, "unit": "%" }`
  → **이 프롬프트에는 용도지역별 법정 한도(1300%)를 주입하지 않음.** value/max 둘 다 LLM이 스스로 추정 → 일반상업을 일반 건축물 통념(300/400%)으로 잘못 채움 = 환각

### B. 로컬 결정론 계산(`calc`) = 정상(1300%)
- `apps/web/components/design/DesignStudio.tsx:84-96` `getZoningSpec/calcMaxGrossArea`
- `apps/web/lib/kr-building-regulations.ts:96-107` 일반상업지역 `buildingCoverageMax:80, floorAreaRatioMax:1300` ← **정확**
  → LLM이 응답하지 않거나 파싱 실패 시(`ai`=null)에는 `calc.floorAreaRatio=1300`이 표시되어 정상으로 보임. **AI 분석을 돌린 순간 300/400으로 오염**된다.

### C. 일조·건축가능 볼륨(1300%의 출처) = 백엔드 SSOT
- `apps/web/components/projects/SolarEnvelopeCard.tsx:35` `apiClient.post("/site-score/envelope", { land_area_sqm, zone, ... })`
- 백엔드 `apps/api/app/services/site_score/solar_envelope_service.py:131-133` `lim=_zone_limits(zone)` → `far=lim.max_far/100`
- FAR 소스 `_zone_limits`(`:108`) = `building_code_rules.ZONE_DEFAULTS`(`apps/api/app/services/permit/building_code_rules.py:52`) `일반상업지역 max_far=1300`
- 검증식: 185㎡ × 1300% = **2,405㎡** (증상값과 정확히 일치) → 이 블록은 SSOT대로 정상

## 4. 400%의 근원 추적 결과
- 프론트 테이블(kr-building-regulations.ts): 일반상업 = **1300** (400 아님)
- 준공업지역만 400 (`kr-building-regulations.ts:123`, `building_code_rules.py:54` max_far=400) → 다른 용도지역 값
- 어떤 테이블에서도 "일반상업=400"은 존재하지 않음 → **400은 LLM이 생성한 값(환각).** 코드 폴백/기본값 아님.
- 참고로 폴백 기본값도 400이 아님: `kr-building-regulations.ts:265` 미지정 시 250%, `solar_envelope_service.py:112` 250%.

## 5. 백엔드 SSOT 정합 현황(전부 1300%로 일치 — 프론트 정적 테이블도 일치)
| 출처(파일:라인) | 일반상업 FAR | BCR |
|---|---|---|
| `apps/api/app/services/permit/building_code_rules.py:52` ZONE_DEFAULTS (envelope 소스) | 1300 | 80 |
| `apps/api/routers/building_compliance.py:353` _LEGAL_LIMITS_PCT | 1300 | 80 |
| `apps/api/app/services/legal/alris_service.py:71` | 1300 | 80 |
| `apps/api/app/services/zoning/far_incentive_calculator.py:72` | 1300 | - |
| `apps/web/lib/kr-building-regulations.ts:99` (프론트 정적) | 1300 | 80 |
| **LLM 응답(ai-prompts.ts design)** | **300/400(환각)** | 300대 추정 |

→ **테이블 간 SSOT 위반은 없다.** 유일한 이탈자는 LLM 자유응답이다. "기본분석과 상이"의 정체 = 부지/법규/일조는 전부 결정론 SSOT(1300), 설계 메트릭만 LLM값(400)을 신뢰하는 **출처 이원화**.

## 6. 화면내 1300 vs 400 불일치 원인(한 문장)
같은 DesignStudio에서 메트릭 카드/법규 체크리스트는 **LLM 자유응답(`ai.floorAreaRatio`, 한도 미주입→환각 400)** 을, 일조·건축가능 볼륨은 **백엔드 envelope의 SSOT(`ZONE_DEFAULTS` 1300)** 를 쓰기 때문.

## 7. 수정방향(권고 — 미적용)
우선순위 순:
1. **(권장) 용적률/건폐율/한도는 LLM에서 받지 말 것.** `DesignStudio.tsx:211-214,231-234`에서 `ai?.floorAreaRatio` 우선순위를 제거하고 `calc`(로컬 SSOT 1300) 또는 백엔드 envelope 값을 단일 출처로 고정. LLM은 summary·massingOptions 등 정성 항목만 담당.
2. 또는 LLM을 유지하려면 `ai-prompts.ts`의 design 시스템 프롬프트에 **용도지역별 법정 한도(BCR/FAR)를 컨텍스트로 주입**하고, "한도는 제공된 값만 사용, 임의 추정 금지"를 명시. `handleAIAnalyze`(`DesignStudio.tsx:108-110`) context에 `getZoningSpec(form.zoning)` 한도 동봉.
3. 메트릭 카드와 SolarEnvelopeCard가 **동일 zone·동일 한도**를 쓰도록 envelope 응답(`far_pct`,`far_gfa_sqm`)을 카드의 단일 출처로 통일(이원화 제거).
4. 프론트 정적 테이블(kr-building-regulations.ts)을 백엔드 `ZONE_DEFAULTS`와 1소스화(현재 값은 일치하나 중복 정의 → drift 위험). 조례 한도(일반상업 800~1000%)는 별도 layer로 표기.

## 8. 관련 파일(절대경로)
- /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web/components/design/DesignStudio.tsx (212,232 = 오염 지점 / 252 = SolarEnvelopeCard)
- /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web/lib/ai-analyze-client.ts (50,59 = LLM 자유호출+JSON파싱)
- /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web/lib/ai-prompts.ts (85-107 = design 프롬프트, 한도 미주입)
- /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web/lib/kr-building-regulations.ts (96-107 = 정상 1300 테이블, 263-266 폴백 250)
- /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web/components/projects/SolarEnvelopeCard.tsx (35,70 = envelope 호출/1300 표시)
- /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/api/app/services/site_score/solar_envelope_service.py (108-133 = FAR 소스)
- /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/api/app/services/permit/building_code_rules.py (52 = ZONE_DEFAULTS SSOT 1300)
- /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/api/routers/building_compliance.py (353 = _LEGAL_LIMITS_PCT 1300)
