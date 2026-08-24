import { describe, it, expect } from "vitest";
import { summarizeBatch, type BatchOutcome } from "@/lib/registry-analyze";

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

const ok = (jibun: string): BatchOutcome => ({ jibun, result: { status: "ok", ai: { x: 1 } } });
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

  it("★`status:\"ok\"` 만 보고 성공이라 하지 않는다 — 권리분석(ai)이 있어야 성공이다", () => {
    // 등기 본문을 못 얻으면 `status:"empty"` 인데, 캐시·응답 형태에 따라 ok 가 섞일 수 있다.
    const s = summarizeBatch([
      { jibun: "a", result: { status: "ok" } },            // ai 없음 → 실패로 센다
      { jibun: "b", result: { status: "ok", ai: {} } },     // ai 있음(빈 객체도 산출물) → 성공
    ]);
    expect(s.ok).toBe(1);
    expect(s.failed).toBe(1);
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

  it("★행별 사유를 존재 여부가 아니라 **값으로** 쓴다", async () => {
    const src = await readExecutable();
    // 종전: `b.result?.message ? "미확보" : "실패"` — 값을 버리는 형태.
    expect(src).toMatch(/b\.result\?\.message \|\|/);
  });

  it.todo("렌더 경로 락 — 실패 섞인 일괄 결과를 그려 대표 사유 문구가 DOM 에 뜨는지(무잠금 부채)");
});
