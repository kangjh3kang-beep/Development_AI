import { describe, it, expect } from "vitest";
import { isAnalyzed, rowReason, summarizeBatch, type BatchOutcome } from "@/lib/registry-analyze";

/**
 * 일괄 등기분석이 **왜 멈췄는지** 말하게 하는 계약 — 실장애에서 나왔다(2026-08-24).
 *
 * ## 무엇이 있었나
 *
 * 사용자가 77필지를 일괄 분석했는데 수십 건 성공 후 나머지가 전부 실패했다.
 * 실제 원인은 **하이픈 민원캐시(선불 잔액) 소진**이었고 **충전하자 즉시 복구**됐다.
 * 그런데 화면은 개수(`N/M`)만 보여 주고 **사유가 없었다** — 행은 조용히 비어 있었다.
 *
 * ★사유는 응답의 `message` 에 **들어 있었다.** UI 가 그것을 **존재 여부로만** 썼다:
 *     `b.result?.message ? "미확보" : "실패"`
 * 그래서 *"잔액이 부족합니다"* 라는 문장이 **"미확보" 두 글자로 뭉개졌다.**
 *
 * ★사용자가 원인을 알아야 스스로 조치한다(충전이면 충전, 주소 오류면 수정).
 *   개수만 보여 주면 "시스템이 고장났나" 로 읽고 **기다리게 된다** — 그게 이번 장애의 시간이었다.
 */

const ok = (jibun: string): BatchOutcome => ({ jibun, result: { status: "ok", ai: { generated: true } } });
const fail = (jibun: string, message?: string, status = "empty"): BatchOutcome => ({
  jibun,
  result: { status, ...(message ? { message } : {}) },
});

describe("summarizeBatch — 왜 멈췄는지 한 줄로 말한다", () => {
  it("★실장애 재현 — 잔액 부족이 대표 사유로 올라온다", () => {
    const s = summarizeBatch([
      ok("434-1"), ok("434-2"), ok("434-3"),
      fail("434-4", "등기 발급 잔액(민원캐시)이 부족합니다 — 충전하면 즉시 재개됩니다."),
      fail("434-5", "등기 발급 잔액(민원캐시)이 부족합니다 — 충전하면 즉시 재개됩니다."),
      fail("434-6", "틸코 주소검색 오류(HTTP 500)"),
    ]);
    expect(s.ok).toBe(3);
    expect(s.total).toBe(6);
    expect(s.failed).toBe(3);
    expect(s.topReason).toContain("잔액");
    expect(s.reasons[0].count).toBe(2);
    expect(s.reasons).toHaveLength(2);
  });

  it("★`status:\"ok\"` 도 `ai` 의 **존재**도 성공이 아니다 — `ai.generated` 만 성공이다", () => {
    // ★이 케이스는 처음에 `ai: {}` 를 성공으로 셌다. 그 픽스처가 **옛 계약을 굳혀** 두는 바람에
    //   폴백(`generated:false`)이 성공으로 잡히는 실장애를 잠그지 못했다(2026-08-24 448-2).
    const s = summarizeBatch([
      { jibun: "a", result: { status: "ok" } },                        // ai 없음 → 실패
      { jibun: "b", result: { status: "ok", ai: {} } },                // ai 있으나 미생성 → 실패
      { jibun: "c", result: { status: "ok", ai: { generated: true } } }, // 생성됨 → 성공
    ]);
    expect(s.ok).toBe(1);
    expect(s.failed).toBe(2);
  });

  it("★사유가 없으면 **없다고** 센다 — 지어내지 않는다", () => {
    const s = summarizeBatch([fail("a"), fail("b")]);
    expect(s.topReason).toContain("사유 미제공");
    expect(s.reasons[0].count).toBe(2);
  });

  it("★요청 자체가 실패한 것(result=null)과 사유 미제공을 구분한다", () => {
    const s = summarizeBatch([
      { jibun: "a", result: null },
      fail("b"),
    ]);
    const set = new Set(s.reasons.map((r) => r.reason));
    expect(set.size).toBe(2);
    expect([...set].some((r) => r.includes("요청 실패"))).toBe(true);
    expect([...set].some((r) => r.includes("사유 미제공"))).toBe(true);
  });

  it("★긴 숫자(고유번호·PNU)를 지워 같은 사유를 하나로 묶는다", () => {
    const s = summarizeBatch([
      fail("a", "고유번호 41370110001043400010 조회 실패"),
      fail("b", "고유번호 41370110001043400020 조회 실패"),
    ]);
    expect(s.reasons).toHaveLength(1);
    expect(s.reasons[0].count).toBe(2);
  });

  it("★대조군 — 전부 성공이면 사유가 없다(없는 경고를 만들지 않는다)", () => {
    const s = summarizeBatch([ok("a"), ok("b")]);
    expect(s.failed).toBe(0);
    expect(s.topReason).toBeNull();
    expect(s.reasons).toHaveLength(0);
  });

  it("빈 입력도 안전하다", () => {
    const s = summarizeBatch([]);
    expect(s).toMatchObject({ ok: 0, total: 0, failed: 0, topReason: null });
  });

  it("★사유가 많은 순으로 정렬한다(대표 사유가 맨 앞이어야 화면이 옳다)", () => {
    const s = summarizeBatch([
      fail("a", "B사유"), fail("b", "A사유"), fail("c", "A사유"), fail("d", "A사유"),
    ]);
    expect(s.reasons.map((r) => r.count)).toEqual([3, 1]);
    expect(s.topReason).toBe("A사유");
  });
});

/**
 * 배선 락 — 화면이 **실제로 이 요약을 쓰는가**.
 *
 * ★한계를 정직히 적는다: 이것은 **소스 검사**이지 렌더 검사가 아니다.
 *   `RegistryAnalysisWorkspaceClient` 는 store·apiClient·자식 다수에 얽혀 있어 렌더 테스트
 *   비용이 크다. 대신 **주석·문자열을 제거한 실행 라인만** 보아 "주석 처리 + 임포트 유지"
 *   변이에 뚫리지 않게 한다(이 저장소가 2회 데인 형태).
 *   ★렌더 경로 자체는 아직 무잠금이며 아래 `it.todo` 로 부채를 남긴다.
 */
/**
 * ★2026-08-24 2차 실장애 — **발급은 됐는데 권리분석만 실패한 건**.
 *
 * 오산 내삼미동 448-2·347-8 은 PDF 가 **정상 발급**됐다(`status:"ok"`). 그런데 화면은
 * "안전성 주의 · 분석 불가"라고 말했다. 그 두 문구는 백엔드 `_llm()` **폴백에서만** 나온다
 * (본문 미확보 경로는 `ai:null` 이라 등급 자체가 없다) — 즉 실패한 층은 **LLM 권리분석**이다.
 *
 * 두 결함이 겹쳤다:
 *  1. 폴백도 `ai` 를 dict 로 돌려주므로 **`ai` 존재로 성공을 세면 실패가 성공으로 잡힌다.**
 *  2. 폴백은 `ai.failure_reason` 에 **사유를 실어 보내는데** 화면이 한 곳도 읽지 않았다.
 *
 * 아래 픽스처는 그 두 모집단(성공/폴백)이 **실제로 다른 값**을 내게 만든다 —
 * 차가 0인 픽스처는 배선을 끊어도 통과하므로 잠금이 아니다.
 */
describe("발급은 됐는데 권리분석만 실패한 건(ai.generated=false)", () => {
  const 성공: BatchOutcome = {
    jibun: "내삼미동 357-2",
    result: { status: "ok", ai: { generated: true } },
  };
  const 폴백: BatchOutcome = {
    jibun: "내삼미동 448-2",
    result: {
      status: "ok",
      ai: { generated: false, failure_reason: "JSONDecodeError: Unterminated string starting at" },
    },
  };

  it("★`ai` 가 있어도 `generated` 가 아니면 성공이 아니다", () => {
    expect(isAnalyzed(성공)).toBe(true);
    expect(isAnalyzed(폴백)).toBe(false);
  });

  it("★성공 집계가 두 모집단을 가른다 — 1/2 이지 2/2 가 아니다", () => {
    const sum = summarizeBatch([성공, 폴백]);
    expect(sum.total).toBe(2);
    expect(sum.ok).toBe(1);
    expect(sum.failed).toBe(1);
  });

  it("★사유는 `ai.failure_reason` 에서 온다 — '분석 불가' 네 글자로 뭉개지 않는다", () => {
    const r = rowReason(폴백);
    expect(r).toContain("JSONDecodeError");
    // 성공 건과 **다른 문자열**이어야 한다(둘이 같으면 배선을 끊어도 통과한다).
    expect(r).not.toBe(rowReason(성공));
  });

  it("★대표 사유가 LLM 실패 사유를 집는다", () => {
    const sum = summarizeBatch([성공, 폴백, { ...폴백, jibun: "내삼미동 347-8" }]);
    expect(sum.topReason).toContain("JSONDecodeError");
    expect(sum.reasons[0].count).toBe(2);
  });

  it("★발급 실패(message)와 권리분석 실패(failure_reason)는 **다른 사유로** 집계된다", () => {
    const 발급실패: BatchOutcome = {
      jibun: "내삼미동 100-1",
      result: { status: "error", message: "하이픈 민원캐시 잔액이 부족합니다" },
    };
    const sum = summarizeBatch([폴백, 발급실패]);
    expect(sum.failed).toBe(2);
    expect(sum.reasons).toHaveLength(2);
  });

  it("사유가 하나도 없으면 **지어내지 않고** 그 사실을 말한다", () => {
    const 무사유: BatchOutcome = { jibun: "x", result: { status: "ok", ai: { generated: false } } };
    expect(rowReason(무사유)).toContain("사유 미제공");
    expect(rowReason({ jibun: "y", result: null })).toContain("요청 실패");
  });
});

describe("배선 — 화면이 요약을 실제로 소비한다", () => {
  const readExecutable = async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { __stripCommentsForScan } = await import("@/lib/source-invariant");
    const rel = "components/operations/RegistryAnalysisWorkspaceClient.tsx";
    const src = fs.readFileSync(path.resolve(__dirname, "../..", rel), "utf8");
    return __stripCommentsForScan(src, rel);
  };

  it("★요약 함수를 호출한다(임포트만 남기고 주석 처리하면 죽는다)", async () => {
    const src = await readExecutable();
    expect(src).toMatch(/summarizeBatch\s*\(/);
  });

  it("★대표 사유를 렌더한다 — 개수만 보여 주던 것이 이번 장애의 시간이었다", async () => {
    const src = await readExecutable();
    expect(src).toMatch(/sum\.topReason/);
    expect(src).toContain("batch-top-reason");
  });

  it("★행을 전용 컴포넌트로 그린다 — 그 컴포넌트가 사유·등급 락을 갖는다", async () => {
    // 행은 `RegistryBatchRow` 로 분리했고 그 렌더 락은
    // components/operations/__tests__/RegistryBatchRow.test.tsx 에 있다.
    // 여기서는 **화면이 그 컴포넌트를 실제로 쓰는지**만 잠근다(임포트만 남기면 죽는다).
    const src = await readExecutable();
    expect(src).toMatch(/<RegistryBatchRow\b/);
  });

  it("★행 판정을 화면이 스스로 다시 하지 않는다(판정자는 lib 하나)", async () => {
    const src = await readExecutable();
    // 종전: `const grade = b.result?.ai?.safety_grade` — 폴백의 "주의"까지 칠했다.
    expect(src).not.toMatch(/ai\?\.safety_grade/);
  });

});
