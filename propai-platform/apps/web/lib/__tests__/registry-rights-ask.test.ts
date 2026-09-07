import { describe, it, expect, vi, beforeEach } from "vitest";
import fs from "node:fs";
import path from "node:path";

vi.mock("@/lib/api-client", () => ({ apiClient: { post: vi.fn() } }));
import { apiClient } from "@/lib/api-client";
import { askRightsQuestion, MAX_QUESTION_CHARS } from "../registry-rights-ask";

const post = apiClient.post as unknown as ReturnType<typeof vi.fn>;

describe("권리분석 추가질의 — 유료 재구매 금지·무언 실패 금지", () => {
  beforeEach(() => post.mockReset());

  it("★★분석 JSON 을 보낸다 — 주소·PNU 로 **다시 사게** 하지 않는다", async () => {
    post.mockResolvedValue({ ok: true, answer: "a", basis: "b", caveat: "" });
    await askRightsQuestion({ generated: true, ownership: "단독" }, "소유자는?");
    expect(post).toHaveBeenCalledTimes(1);
    const [url, opts] = post.mock.calls[0];
    const body = opts.body;
    expect(url).toContain("/rights/ask");
    expect(body.analysis, "이미 가진 분석을 안 보낸다").toBeTruthy();
    // ★서버가 재조회할 수 있는 키를 보내지 않는다(두 모집단 중 「보내면 안 되는 쪽」)
    for (const k of ["address", "pnu", "unique_no", "unique_number"]) {
      expect(body[k], `재조회 유발 키 \`${k}\` 를 보낸다 — 유료 재발급 위험`).toBeUndefined();
    }
  });

  it("★빈 질문·분석 없음은 **호출 자체를 안 한다**(쿼터·과금 낭비 방지)", async () => {
    expect((await askRightsQuestion({ generated: true }, "  ")).caveat).toContain("질문");
    expect((await askRightsQuestion(null, "질문")).caveat).toContain("권리분석 결과");
    expect(post, "쓰레기 입력으로 서버를 불렀다").not.toHaveBeenCalled();
  });

  it("질문 길이 상한이 실제로 걸린다", async () => {
    post.mockResolvedValue({ ok: true, answer: "a", basis: "", caveat: "" });
    await askRightsQuestion({ generated: true }, "가".repeat(MAX_QUESTION_CHARS + 300));
    expect(post.mock.calls[0][1].body.question.length).toBe(MAX_QUESTION_CHARS);
  });

  it("★실패 사유를 삼키지 않는다 — 무언 실패 금지", async () => {
    // ★`mockRejectedValue` 는 **소비 전에** rejected promise 를 만들어 unhandled 로 잡힌다.
    //   던지는 구현으로 바꿔 «함수가 잡는가»만 태운다.
    post.mockImplementationOnce(() => Promise.reject(new Error("429 Too Many Requests")));
    const r = await askRightsQuestion({ generated: true }, "질문");
    expect(r.ok).toBe(false);
    expect(r.caveat, "사유가 화면까지 안 온다").toContain("429");
  });

  it("★백엔드와 질문 길이 상한이 같다(미러)", () => {
    const be = fs.readFileSync(
      path.resolve(__dirname, "../../../../apps/api/app/services/ai/registry_rights_interpreter.py"),
      "utf8");
    const m = be.match(/^_MAX_QUESTION_CHARS\s*=\s*(\d+)/m);
    expect(m, "백엔드 상한 **선언**을 못 찾았다 — 조회기 사망").toBeTruthy();
    expect(Number(m![1]), "프론트가 자르는 길이와 백엔드가 자르는 길이가 다르다").toBe(MAX_QUESTION_CHARS);
  });
});
