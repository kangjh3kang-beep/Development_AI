/**
 * 유료 AI 렌더 결과 **영속** 계약.
 *
 * 【지침이 예측한 결함을 다른 도메인에서 실측】
 * CLAUDE.md 「유료·비가역 산출물 규율」의 *"유료 산출물은 영속한다"* 를 세우고 나서
 * 형제를 훑었더니 `photoreal_render`(**건당 3,000원**, 외부 GPU 호출)가 결과를
 * `setRenderImage`(평범한 `useState`)로만 들고 있었다 — **새로고침 한 번에 사라진다.**
 * 등기 권리분석 리스트와 **같은 얼굴**이다.
 *
 * ★이 스위트가 특히 보는 것: **용량 때문에 못 담을 때 조용히 사라지지 않는가.**
 *   base64 렌더는 수 MB 가 될 수 있고 localStorage 는 대략 5MB 다. 그때 항목을 통째로
 *   버리면 사용자는 자기가 3,000원을 쓴 사실조차 알 수 없다.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { MAX_INLINE_BYTES, MAX_ITEMS, usePaidRenderStore } from "@/store/usePaidRenderStore";

const P = "proj-1";
const big = "x".repeat(MAX_INLINE_BYTES + 10);

beforeEach(() => {
  usePaidRenderStore.setState({ byProject: {} });
});

describe("유료 렌더 영속", () => {
  it("★렌더 결과를 프로젝트별로 보관하고 시점·과금액을 남긴다", () => {
    usePaidRenderStore.getState().add(P, { id: "1", imageUrl: "https://x/a.png", chargedKrw: 3000 });
    const got = usePaidRenderStore.getState().byProject[P];
    expect(got).toHaveLength(1);
    expect(got[0].imageUrl).toBe("https://x/a.png");
    expect(got[0].chargedKrw, "얼마짜리인지 없으면 화면이 말할 수 없다").toBe(3000);
    expect(got[0].at).toBeTruthy();
  });

  it("★★용량이 커서 본문을 못 담아도 **항목과 사유는 남긴다**(조용한 소실 금지)", () => {
    usePaidRenderStore.getState().add(P, { id: "1", imageBase64: big, chargedKrw: 3000 });
    const got = usePaidRenderStore.getState().byProject[P];
    expect(got, "항목이 통째로 사라졌다 — 3,000원을 쓴 사실도 같이 사라진다").toHaveLength(1);
    expect(got[0].imageBase64).toBeNull();
    expect(got[0].omitted).toBe("size");
    expect(got[0].chargedKrw).toBe(3000);
  });

  it("대조군 — 작은 이미지는 본문을 담고 사유를 붙이지 않는다(두 경로가 실제로 갈린다)", () => {
    usePaidRenderStore.getState().add(P, { id: "1", imageBase64: "data:image/png;base64,AAA" });
    const got = usePaidRenderStore.getState().byProject[P][0];
    expect(got.imageBase64).toContain("AAA");
    expect(got.omitted).toBeNull();
  });

  it("★항목 수 상한을 넘으면 **오래된 것부터** 버린다(무한 성장 방지)", () => {
    const s = usePaidRenderStore.getState();
    for (let i = 0; i < MAX_ITEMS + 3; i++) s.add(P, { id: `${i}`, imageUrl: `u${i}` });
    const got = usePaidRenderStore.getState().byProject[P];
    expect(got).toHaveLength(MAX_ITEMS);
    expect(got[0].id, "가장 오래된 것이 남았다 — 버리는 방향이 반대다").toBe("3");
    expect(got[got.length - 1].id).toBe(`${MAX_ITEMS + 2}`);
  });

  it("★프로젝트가 다르면 섞이지 않는다", () => {
    const s = usePaidRenderStore.getState();
    s.add("A", { id: "1", imageUrl: "a" });
    s.add("B", { id: "1", imageUrl: "b" });
    const st = usePaidRenderStore.getState().byProject;
    expect(st["A"][0].imageUrl).toBe("a");
    expect(st["B"][0].imageUrl).toBe("b");
  });

  it("remove 는 그 항목만, clear 는 그 프로젝트만 지운다", () => {
    const s = usePaidRenderStore.getState();
    s.add(P, { id: "1", imageUrl: "a" });
    s.add(P, { id: "2", imageUrl: "b" });
    usePaidRenderStore.getState().remove(P, "1");
    expect(usePaidRenderStore.getState().byProject[P].map((x) => x.id)).toEqual(["2"]);
    usePaidRenderStore.getState().clear(P);
    expect(usePaidRenderStore.getState().byProject[P]).toBeUndefined();
  });
});

describe("배선 — 화면이 실제로 보관·복원한다", () => {
  const read = async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { __stripCommentsForScan } = await import("@/lib/source-invariant");
    const rel = "components/design/CadBimIntegrationPanel.tsx";
    return __stripCommentsForScan(fs.readFileSync(path.resolve(__dirname, "../..", rel), "utf8"), rel);
  };

  it("전제: 대상 파일을 읽었고 렌더 성공 경로가 있다(공허한 초록 방지)", async () => {
    const src = await read();
    expect(src.length).toBeGreaterThan(1000);
    expect(src).toMatch(/setRenderImage\(img\)/);
  });

  it("★렌더가 성공하면 보관한다", async () => {
    expect(await read()).toMatch(/addRender\s*\(/);
  });

  it("★보관분을 화면에 되살린다", async () => {
    const src = await read();
    expect(src).toMatch(/savedRenders/);
    expect(src).toContain("saved-renders");
  });

  it("★못 담은 건의 사유를 화면에 말한다", async () => {
    expect(await read()).toContain("saved-render-omitted");
  });
});
