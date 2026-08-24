/**
 * 등기부 PDF **일괄 다운로드**의 계약.
 *
 * 【실측이 만든 요구】2026-08-24 라이브에서 저장된 서명 URL 79건 중 표본 3건을 받아 보니
 * **2건이 `InvalidJWT — "exp" claim timestamp check failed`** 였다. 화면엔 `PDF ↗` 가
 * 멀쩡히 떠 있다. 그냥 묶으면 **누른 건수보다 적은 ZIP** 이 조용히 나온다.
 * 그래서 이 스위트의 중심은 "몇 건 담겼나"가 아니라 **"빠진 건을 말하는가"** 다.
 */
import { describe, expect, it } from "vitest";

import {
  buildRegistryPdfBundle,
  describeBundle,
  type FetchLike,
  type PdfSource,
} from "@/lib/registry-pdf-bundle";

const pdf = (s: string) => new TextEncoder().encode(s).buffer as ArrayBuffer;

/** URL → 응답을 표로 준다. 실제 네트워크를 타지 않지만 **분류 경로는 전부 태운다**. */
function fakeFetch(table: Record<string, { status: number; body?: string; data?: string }>): FetchLike {
  return async (url: string) => {
    const r = table[url];
    if (!r) throw new Error("연결할 수 없습니다");
    return {
      ok: r.status >= 200 && r.status < 300,
      status: r.status,
      text: async () => r.body ?? "",
      arrayBuffer: async () => pdf(r.data ?? ""),
    };
  };
}

const EXPIRED_BODY =
  '{"statusCode":"400","error":"InvalidJWT","message":"\\"exp\\" claim timestamp check failed","code":"InvalidJWT"}';

describe("buildRegistryPdfBundle", () => {
  it("정상 건은 담고 파일명에 지번을 넣는다", async () => {
    const sources: PdfSource[] = [{ jibun: "내삼미동 448-2", pdfUrl: "u1" }];
    const r = await buildRegistryPdfBundle(sources, {
      fetchImpl: fakeFetch({ u1: { status: 200, data: "PDFBODY" } }),
    });
    expect(r.included).toBe(1);
    expect(r.zip).not.toBeNull();
    expect(r.items[0].status).toBe("included");
    expect(r.items[0].fileName).toContain("내삼미동 448-2");
    expect(r.items[0].fileName).toMatch(/^001_/);
  });

  it("★★만료된 링크를 **만료로** 분류한다 — 'PDF 없음'과 섞으면 재발급하면 된다는 걸 모른다", async () => {
    const r = await buildRegistryPdfBundle([{ jibun: "가", pdfUrl: "u1" }], {
      fetchImpl: fakeFetch({ u1: { status: 400, body: EXPIRED_BODY } }),
    });
    expect(r.items[0].status).toBe("expired");
    expect(r.items[0].detail).toContain("만료");
    expect(r.items[0].detail).toContain("다시 발급");
  });

  it("만료가 아닌 400 은 만료라고 하지 않는다(대조군 — 분류가 실제로 갈린다)", async () => {
    const r = await buildRegistryPdfBundle([{ jibun: "가", pdfUrl: "u1" }], {
      fetchImpl: fakeFetch({ u1: { status: 400, body: '{"error":"Bad request"}' } }),
    });
    expect(r.items[0].status).toBe("fetch_failed");
  });

  it("PDF 가 아예 없는 건은 받으러 가지 않고 그렇게 말한다", async () => {
    const r = await buildRegistryPdfBundle([{ jibun: "가", pdfUrl: null }], {
      fetchImpl: fakeFetch({}),
    });
    expect(r.items[0].status).toBe("no_pdf");
    expect(r.included).toBe(0);
  });

  it("★한 건이 실패해도 나머지는 담는다", async () => {
    const r = await buildRegistryPdfBundle(
      [
        { jibun: "가", pdfUrl: "u1" },
        { jibun: "나", pdfUrl: "u2" },
        { jibun: "다", pdfUrl: "u3" },
      ],
      {
        fetchImpl: fakeFetch({
          u1: { status: 200, data: "A" },
          u2: { status: 400, body: EXPIRED_BODY },
          u3: { status: 200, data: "C" },
        }),
      },
    );
    expect(r.included).toBe(2);
    expect(r.items.map((i) => i.status)).toEqual(["included", "expired", "included"]);
  });

  it("네트워크가 통째로 죽어도 던지지 않고 건별로 보고한다", async () => {
    const r = await buildRegistryPdfBundle([{ jibun: "가", pdfUrl: "u1" }], {
      fetchImpl: fakeFetch({}),
    });
    expect(r.items[0].status).toBe("fetch_failed");
    expect(r.items[0].detail).toContain("연결할 수 없습니다");
  });

  it("★담긴 것이 없으면 zip 은 null — 빈 ZIP 을 성공처럼 내려보내지 않는다", async () => {
    const r = await buildRegistryPdfBundle([{ jibun: "가", pdfUrl: null }], {
      fetchImpl: fakeFetch({}),
    });
    expect(r.zip).toBeNull();
  });

  it("같은 지번이 둘이어도 서로 다른 파일명이 된다(덮어쓰기 방지)", async () => {
    const r = await buildRegistryPdfBundle(
      [
        { jibun: "같은지번", pdfUrl: "u1" },
        { jibun: "같은지번", pdfUrl: "u2" },
      ],
      { fetchImpl: fakeFetch({ u1: { status: 200, data: "A" }, u2: { status: 200, data: "B" } }) },
    );
    expect(r.items[0].fileName).not.toBe(r.items[1].fileName);
  });

  it("빈 응답은 담지 않는다(0바이트 PDF 를 성공으로 세지 않는다)", async () => {
    const r = await buildRegistryPdfBundle([{ jibun: "가", pdfUrl: "u1" }], {
      fetchImpl: fakeFetch({ u1: { status: 200, data: "" } }),
    });
    expect(r.items[0].status).toBe("fetch_failed");
    expect(r.included).toBe(0);
  });
});

describe("describeBundle — 빠진 건을 반드시 말한다", () => {
  const mk = async (table: Parameters<typeof fakeFetch>[0], sources: PdfSource[]) =>
    buildRegistryPdfBundle(sources, { fetchImpl: fakeFetch(table) });

  it("★제외가 있으면 사유별 건수를 적는다", async () => {
    const r = await mk(
      { u1: { status: 200, data: "A" }, u2: { status: 400, body: EXPIRED_BODY } },
      [
        { jibun: "가", pdfUrl: "u1" },
        { jibun: "나", pdfUrl: "u2" },
        { jibun: "다", pdfUrl: null },
      ],
    );
    const s = describeBundle(r);
    expect(s).toContain("3건 중 1건");
    expect(s).toContain("발급 링크 만료 1건");
    expect(s).toContain("PDF 없음 1건");
  });

  it("★대조군 — 전부 담겼으면 없는 제외를 지어내지 않는다", async () => {
    const r = await mk({ u1: { status: 200, data: "A" } }, [{ jibun: "가", pdfUrl: "u1" }]);
    const s = describeBundle(r);
    expect(s).toBe("1건 중 1건 담았습니다");
    expect(s).not.toContain("제외");
  });
});
