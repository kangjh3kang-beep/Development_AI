# 157 프론트 2버그 수정 (crash + FAR 환각)

대상: `apps/web/app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx`, `apps/web/components/design/DesignStudio.tsx`, `apps/web/lib/ai-prompts.ts`
원칙: 무목업(값 없으면 "—") · push/배포 없음 · import 보존(diff 확인) · 최소 diff

## 버그1: site-analysis 크래시 (undefined.toLocaleString)
- 근본원인: `formatPriceKr(amount10k: number)`가 입력 undefined/null/NaN이면 `amount10k.toLocaleString()` 크래시. 호출처(평균/최고/최저 등)는 `tx.apt.count>0` 렌더가드만 있고 가격필드 존재 검증 없음.
- 가드:
  - `formatPriceKr` 시그니처 → `number | null | undefined`, 첫줄 `if (amount10k == null || !Number.isFinite(amount10k)) return "—";` (page.tsx:153-154)
  - 인접 무가드 점검: `infra.nearest_subway.distance_m.toLocaleString()` (page.tsx:596-597)도 `distance_m`만 null 가능 → 색상 분기 `?? Infinity`, 렌더는 finite일 때만 `Nm` 아니면 "—".
- 다른 `.toLocaleString()`는 `formatPriceKr` 경유 또는 가드됨. 무목업: 누락 시 "—".

## 버그2: DesignStudio 용적률 LLM 환각 (400%)
- 근본원인: 정량 법정한도(건폐율/용적률/높이/주차/연면적)가 `ai?.X ?? calc.X` 패턴이라 AI 자유응답(일반상업 400% 환각)이 로컬 SSOT(`calc`=kr-building-regulations, 일반상업 1300%)를 덮음 → 카드·체크리스트·BIM 일조볼륨(envelope 1300%) 불일치.
- 단일출처(calc) 고정 (ai 우선순위 제거):
  - 정량 카드 4종(건폐율·용적률·예상층수·주차) → `calc.*` 고정 (DesignStudio.tsx:209-214)
  - 법규 적합 체크리스트 4행(건폐율·용적률·높이·주차) → `calc.*` 고정 (:230-234)
  - 컨텍스트 store payload(totalGfaSqm·floorCount·bcr·far) → `calc.*` 고정 + 주석 (:119-127). useEffect deps에서 미사용 `ai?.*` 제거(:139-144).
  - "최대 연면적" 카드 → `calc.maxGrossArea` 고정 (:263). FAR×면적 = 법정 최대라 3D envelope·store와 정합.
- 정성 항목은 ai 유지: 상태 배지(:204-205), setbacks(:275-277, 명명 범위 외 위치값), massingOptions(:291), summary(:319-326).
- 프롬프트(ai-prompts.ts:94-107) design: 정량 법정한도는 플랫폼 로컬 SSOT 확정·화면표시, "추정/임의생성 금지, 용도지역 범위 내 정성 해석만, summary·massingOptions 집중" 명시. JSON 형식도 정량 필드 제거하고 massingOptions·summary만 요청.

## 검증
- `cd apps/web && npx tsc --noEmit` → EXIT 0
- `git diff` import 라인 변경 없음(린터 import 트랩 회피 확인)
- 3파일 26+/28-, 무목업 유지

## 미진
- setbacks(전면/측면/후면)는 정량 법정한도성격이나 명명 범위(건폐율/용적률/높이/주차) 밖이라 ai 우선 유지. 필요시 동일 calc 고정 가능.
- `ai` 타입(AIDesignResult)에 미사용된 정량 필드 선언 잔존(무해, tsc 통과). 정리 원하면 후속.
- 프롬프트에 실제 법정한도 수치를 변수로 주입하진 않음(호출 컨텍스트에 용도지역만 전달). 현재는 "추정금지" 지시로 환각 차단.
