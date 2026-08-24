/**
 * 필지별 권리분석 결과 **영속** 계약.
 *
 * 【사용자 신고 2026-08-24】*"하단에 필지별 권리분석 리스트가 있고 상세를 누르면 볼 수
 * 있었는데 사라졌다."* — 사라진 게 아니라 **처음부터 휘발성**이었다. 그 목록은 화면
 * 상태(`batchResults`)에만 있었고 어디에도 저장되지 않았다. 그래서
 *  · 새로고침하면 없어지고
 *  · 토지조서에서 `?addr=` 로 들어오면(사용자 URL 이 정확히 그 경우) 단건 조회만 돌아
 *    목록이 **아예 만들어지지 않았으며**
 *  · **개별 `분석` 버튼으로 한 필지씩 돌리면 목록에 쌓이지도 않았다**(전체 분석만 쌓았다).
 *
 * 필지당 1,200원이 나가는 산출물이 새로고침 한 번에 사라지는 것은 결함이다.
 *
 * ★이 파일이 `store/` 가 아니라 `lib/__tests__/` 에 있는 이유: vitest include 가
 *   `store/**` 를 **덮지 않는다**. 거기 두면 테스트가 영영 실행되지 않는다(조용한 미실행).
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useRegistryAnalysisStore } from "@/store/useRegistryAnalysisStore";

const P = "proj-1";
const res = (owner: string) => ({
  status: "ok",
  ai: { generated: true, ownership: { current_owner: owner } },
});
const owner = (r: unknown) =>
  (r as { ai: { ownership: { current_owner: string } } }).ai.ownership.current_owner;

beforeEach(() => {
  useRegistryAnalysisStore.setState({ byProject: {} });
});

describe("권리분석 결과 영속", () => {
  it("★분석 결과를 프로젝트별로 담고 시점을 남긴다", () => {
    useRegistryAnalysisStore
      .getState()
      .upsert(P, { jibun: "내삼미동 448-2", rowId: "r1", result: res("홍길동") });
    const got = useRegistryAnalysisStore.getState().byProject[P];
    expect(got).toHaveLength(1);
    expect(got[0].jibun).toBe("내삼미동 448-2");
    expect(got[0].savedAt, "언제 분석분인지 없으면 화면이 시점을 말할 수 없다").toBeTruthy();
  });

  it("★같은 필지를 다시 분석하면 **덮어쓴다**(중복이 쌓이지 않는다)", () => {
    const s = useRegistryAnalysisStore.getState();
    s.upsert(P, { jibun: "가", rowId: "r1", result: res("옛소유자") });
    s.upsert(P, { jibun: "가", rowId: "r1", result: res("새소유자") });
    const got = useRegistryAnalysisStore.getState().byProject[P];
    expect(got).toHaveLength(1);
    expect(owner(got[0].result)).toBe("새소유자");
  });

  it("★분석한 순서를 유지한다(행 순서로 재정렬하면 방금 돌린 게 어디 갔는지 모른다)", () => {
    const s = useRegistryAnalysisStore.getState();
    s.upsert(P, { jibun: "나중", rowId: "r2", result: res("B") });
    s.upsert(P, { jibun: "먼저", rowId: "r1", result: res("A") });
    expect(useRegistryAnalysisStore.getState().byProject[P].map((x) => x.rowId)).toEqual(["r2", "r1"]);
  });

  it("★행을 지우면 결과도 지운다 — 안 지우면 **없는 필지가 유령으로 되살아난다**", () => {
    const s = useRegistryAnalysisStore.getState();
    s.upsert(P, { jibun: "가", rowId: "r1", result: res("A") });
    s.upsert(P, { jibun: "나", rowId: "r2", result: res("B") });
    useRegistryAnalysisStore.getState().remove(P, "r1");
    expect(useRegistryAnalysisStore.getState().byProject[P].map((x) => x.rowId)).toEqual(["r2"]);
  });

  it("★프로젝트가 다르면 섞이지 않는다(대조군 — 남의 분석이 보이면 안 된다)", () => {
    const s = useRegistryAnalysisStore.getState();
    s.upsert("A", { jibun: "가", rowId: "r1", result: res("갑") });
    s.upsert("B", { jibun: "나", rowId: "r1", result: res("을") });
    const st = useRegistryAnalysisStore.getState().byProject;
    expect(owner(st["A"][0].result)).toBe("갑");
    expect(owner(st["B"][0].result)).toBe("을");
  });

  it("활성 프로젝트가 없어도 결과를 버리지 않는다", () => {
    useRegistryAnalysisStore.getState().upsert(null, { jibun: "가", rowId: "r1", result: res("A") });
    expect(useRegistryAnalysisStore.getState().byProject["_default"]).toHaveLength(1);
  });

  it("실패한 건(result=null)도 담는다 — 무엇을 시도했는지 남아야 한다", () => {
    useRegistryAnalysisStore.getState().upsert(P, { jibun: "가", rowId: "r1", result: null });
    expect(useRegistryAnalysisStore.getState().byProject[P][0].result).toBeNull();
  });

  it("clear 는 그 프로젝트만 비운다", () => {
    const s = useRegistryAnalysisStore.getState();
    s.upsert("A", { jibun: "가", rowId: "r1", result: res("A") });
    s.upsert("B", { jibun: "나", rowId: "r1", result: res("B") });
    useRegistryAnalysisStore.getState().clear("A");
    const st = useRegistryAnalysisStore.getState().byProject;
    expect(st["A"]).toBeUndefined();
    expect(st["B"]).toHaveLength(1);
  });
});

describe("배선 — 화면이 실제로 저장·복원한다", () => {
  const read = async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { __stripCommentsForScan } = await import("@/lib/source-invariant");
    const rel = "components/operations/RegistryAnalysisWorkspaceClient.tsx";
    return __stripCommentsForScan(fs.readFileSync(path.resolve(__dirname, "../..", rel), "utf8"), rel);
  };

  it("전제: 대상 파일을 읽었다(공허한 초록 방지)", async () => {
    expect((await read()).length).toBeGreaterThan(1000);
  });

  it("★개별 분석도 저장한다 — 종전엔 전체 분석만 목록에 쌓았다", async () => {
    expect(await read()).toMatch(/saveAnalysis\s*\(/);
  });

  it("★저장분으로 목록을 복원한다(새로고침·딥링크 진입)", async () => {
    const src = await read();
    expect(src).toMatch(/savedAnalyses/);
    expect(src).toMatch(/setBatchResults\(/);
  });

  it("★행 삭제가 결과 삭제와 짝을 이룬다", async () => {
    expect(await read()).toMatch(/dropAnalysis\s*\(/);
  });
});

describe("번지 없는 주소는 유료 발급으로 나가지 않는다", () => {
  const read = async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { __stripCommentsForScan } = await import("@/lib/source-invariant");
    const rel = "components/operations/RegistryAnalysisWorkspaceClient.tsx";
    return __stripCommentsForScan(fs.readFileSync(path.resolve(__dirname, "../..", rel), "utf8"), rel);
  };

  it("★필지 식별자(PNU 또는 지번)를 확인한 뒤에만 조회한다", async () => {
    const src = await read();
    // 종전엔 `addressHasJibun` 이 **PNU 보강에만** 쓰였고 유료 호출은 막지 않았다.
    expect(src).toMatch(/hasParcelId/);
    expect(src).toMatch(/addressHasJibun\(target\)/);
  });

  it("★막을 때 **무엇이 없는지와 다음 행동**을 말한다(‘잠시 후 재시도’는 틀린 안내다)", async () => {
    const src = await read();
    expect(src).toContain("번지가 없어");
    expect(src).toContain("필지 단위");
  });
});

describe("addressHasJibun — 게이트가 무엇을 통과시키나", () => {
  it("★동 단위 주소는 막고, 지번이 있으면 통과시킨다(대조군)", async () => {
    const { addressHasJibun } = await import("@/lib/pnu");
    expect(addressHasJibun("경기도 오산시 내삼미동"), "동 단위인데 통과했다").toBe(false);
    expect(addressHasJibun("경기도 오산시 내삼미동 448-2")).toBe(true);
    expect(addressHasJibun("경기도 오산시 내삼미동 467-1 (내삼미동)")).toBe(true);
  });
});
