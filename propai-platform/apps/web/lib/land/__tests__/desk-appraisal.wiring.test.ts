/**
 * 탁상감정 "표본 0 사유" 표면 배선 불변식.
 *
 * ## 왜 이 파일이 있는가
 *
 * 백엔드가 `comparable_skipped_reason` 을 채우기 시작한 뒤에도 **화면 소비처가 0개**여서
 * 사용자가 겪는 침묵은 그대로였다(R1 리뷰 M-6). 그 뒤 두 표면을 배선했지만 이번엔
 * **배선 락이 0건**이라 지우면 조용히 통과한다 — 정확히 M-6 상태로 되돌아간다(R2 리뷰 M-5).
 *
 * ★그리고 R2 는 표면이 **넷**임을 밝혔다: 모달 · 보고서 클라이언트 · 부지분석 워크스페이스 ·
 *   PDF/PPTX/DOCX 어댑터(백엔드). 정직성 결함은 소비처마다 복제돼 **국소 수정이 원리적으로
 *   불충분**하다는 것이 이 저장소에서 3연속 실증됐다 — 그래서 넷을 한 파일에서 함께 잠근다.
 *
 * ★"타입에만 있고 렌더가 없으면 배선이 아니다" — 렌더 JSX 안에서 그 필드를 읽는지 본다.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, it, expect } from "vitest";
import { assertWiredThrough } from "@/lib/source-invariant";

const SURFACES = [
  { label: "탁상감정 모달", file: "components/operations/DeskAppraisalModal.tsx" },
  { label: "탁상감정 보고서 화면", file: "components/operations/DeskAppraisalReportClient.tsx" },
  { label: "부지분석 워크스페이스", file: "components/projects/ProjectSiteAnalysisWorkspaceClient.tsx" },
];

describe("표본 0 사유 표면 배선", () => {
  for (const s of SURFACES) {
    it(`${s.label} — 사유를 실제로 렌더한다`, () => {
      // ★스코프를 **멤버 접근**(`.comparable_skipped_reason`)으로 좁힌다 — 타입 선언 줄
      //   (`comparable_skipped_reason?: string | null;`)은 접근이 아니라서 걸리지 않는다.
      //   "이름이 어딘가 있다"와 "그 값을 읽는다"는 다르다(이 저장소에서 반복 실증).
      // ★R3 리뷰(F-3) — 종전 `mustContain` 은 `scope` 가 이미 함의해 **위반이 원리적으로
      //   불가능**했고(공허), 실질 판별력이 `minMatches: 2` 하나였다. 게다가 그 매치는
      //   `{/* … comparable_skipped_reason … */}` JSX 주석으로 **패딩**되어 렌더를 지워도
      //   초록이 됐다(공용 도구 `stripLineComment` 를 함께 고쳤다).
      //   ★★R4 리뷰(M-5) 표기 정정 — 개선을 만든 것은 `mustContain` 이 아니라 **`scope`**
      //   다. `mustContain` 이 `scope` 에 함의되면 위반이 원리적으로 불가능해(공허) 판별력이
      //   `scope` + `minMatches` 에만 있다. 그러니 함의된 `mustContain` 을 쓰는 대신,
      //   **렌더 형태**를 `scope` 로 잡고 그 줄이 **가드 안**에 있는지를 별도로 확인한다.
      //   ★그리고 이 락의 실효는 공용 도구가 **여러 줄 JSX 주석**을 벗기는 데 달려 있다
      //   (R4 H-1 — 그전엔 렌더를 여러 줄 주석에 넣으면 초록이었다).
      assertWiredThrough({
        file: s.file,
        scope: /\{\s*\w+\.comparable_skipped_reason\s*\}/,
        // 렌더 줄은 반드시 값 표현이어야 한다 — 타입 선언·주석은 여기 걸리지 않는다.
        mustContain: /\.comparable_skipped_reason\s*\}/,
        minMatches: 1,
      });
      // 조건부 가드가 **따로** 있어야 한다 — 값이 없을 때 빈 문단을 그리지 않는다.
      // (`minMatches: 1` 이 실질 판별자다. 가드가 사라지면 0건이 되어 실패한다.)
      assertWiredThrough({
        file: s.file,
        scope: /\.comparable_skipped_reason \?/,
        mustContain: /\?\s*\(/,
        minMatches: 1,
      });
    });
  }

  it("PDF/PPTX/DOCX 보고서 어댑터도 사유를 싣는다", () => {
    // 은행 제출용 산출물에서 방법이 그냥 사라지면 읽는 사람은 "거래가 없다"로 오독한다.
    const src = readFileSync(
      path.resolve(__dirname, "../../../../api/app/services/report/render/appraisal_adapter.py"),
      "utf-8",
    );
    expect(src).toMatch(/data\.get\("comparable_skipped_reason"\)/);
    expect(src).toMatch(/NarrativeBlock\(\s*paragraphs=\[str\(data\["comparable_skipped_reason"\]\)\]\s*\)/);
  });
});
