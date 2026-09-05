/**
 * `desk_appraisal` → 검증 배지 **output 배선 락** (2026-09-05).
 *
 * ## 왜 이 파일이 생겼나
 *
 * `#993` 은 배지 자체에 락 10건을 걸고 변이 4/4 CAUGHT 를 받았다. 그런데 저장소가
 * **의무화한** `scripts/mutate_changed.py` 를 안 돌렸고, 소급해서 돌리니
 * **`DeskAppraisalReportClient.tsx` 의 `output={apprNarrRaw ?? undefined}` 줄을 지워도
 * 모든 락이 초록**이었다(★생존).
 *
 * ★즉 **배지는 잠갔는데 배선은 무잠금**이었다 — 그 줄이 사라지면 이 화면은 조용히
 * `hasSplit=false` 로 되돌아가 **계산 결과를 자기 자신과 대조**하고, 사용자에게는
 * 「AI 서술 없음 · 판정 안 함」이 **영원히** 뜬다(오작동은 아니지만 기능이 죽는다).
 *
 * ## 한계(정직 바운딩)
 *
 * 이 락은 **소스에 그 배선이 있는지**만 본다 — 렌더 결과가 아니다. 그 컴포넌트는
 * 무거운 클라이언트 화면이라 렌더 태우기가 비싸서, 저장소가 정한 폴백
 * (`__stripCommentsForScan` 경유 소스 검사)을 쓴다. **주석·문자열에 뚫리지 않도록**
 * 주석을 걷어내고 본다. ★「값이 실린다」까지는 증명하지 않는다 —
 * 그 축은 배지 쪽 락(`VerificationBadge.test.tsx`)이 태운다.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const FILE = "components/operations/DeskAppraisalReportClient.tsx";
const code = __stripCommentsForScan(readFileSync(resolve(process.cwd(), FILE), "utf-8"), FILE);

describe("desk_appraisal 이 검증기에 **AI 서술**을 넘긴다", () => {
  it("★공허 진리 방지 — 배지 마운트가 실재한다", () => {
    expect(code).toContain("<VerificationBadge");
    expect(code).toContain('analysisType="desk_appraisal"');
  });

  it("★배선 락 — `output` 을 넘긴다(지우면 조용히 자기대조로 되돌아간다)", () => {
    expect(code).toMatch(/output=\{\s*apprNarrRaw/);
  });

  it("★원본 키를 보존한 쪽을 넘긴다 — 화면용 `apprNarr` 는 키를 한글 라벨로 바꾼다", () => {
    // `apprNarr` 를 그대로 넘기면 검증기가 **어느 필드인지 모른다**.
    expect(code).not.toMatch(/output=\{\s*apprNarr\s*[?}]/);
    expect(code).toContain("setApprNarrRaw");
  });
});
