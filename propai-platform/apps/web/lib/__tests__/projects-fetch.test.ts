/**
 * 프로젝트 목록 페이지 순회 락 — **탐지·특이도·배선·판단**을 각각 잠근다.
 *
 * 왜 축을 나누는가: 탐지만 잠그면 "항상 전부 가져온다고 주장하는" 구현이 만점을 받는다.
 * 각 축은 서로 다른 변이에 죽는다.
 */
import { describe, expect, it } from "vitest";

import {
  PROJECTS_PAGE_SIZE,
  fetchAllProjects,
  projectsPagePath,
  selectOrphans,
} from "@/lib/projects-fetch";
import { assertWiredThrough } from "@/lib/source-invariant";

type P = { id: string; address: string };

/** 라이브 실측 형상(2026-08-25): total=24 · 서버 기본 page_size=20 · has_next=true. */
function pagedServer(total: number, pageSize: number) {
  const all: P[] = Array.from({ length: total }, (_, i) => ({
    id: `p${i + 1}`,
    address: `주소${i + 1}`,
  }));
  const calls: string[] = [];
  const get = async (path: string) => {
    calls.push(path);
    const page = Number(new URL(path, "http://x").searchParams.get("page") ?? "1");
    const size = Number(new URL(path, "http://x").searchParams.get("page_size") ?? String(pageSize));
    const eff = Math.min(size, pageSize); // 서버가 상한을 두는 경우까지 흉내
    const offset = (page - 1) * eff;
    const items = all.slice(offset, offset + eff);
    return { items, total, page, page_size: eff, has_next: offset + items.length < total };
  };
  return { get, calls, all };
}

describe("★탐지 — has_next 를 따라 끝까지 걷는다", () => {
  it("서버가 20건씩 주고 전체가 24건이면 **24건**을 모은다(한 번만 부르면 20건)", async () => {
    const s = pagedServer(24, 20);
    const r = await fetchAllProjects<P>(s.get);
    expect(r.items).toHaveLength(24);
    expect(r.total).toBe(24);
    expect(s.calls.length).toBeGreaterThanOrEqual(2);
    // ★두 모집단을 가른다: 1페이지만 걸으면 마지막 4건이 없다.
    expect(r.items.map((p) => p.id)).toContain("p24");
    expect(r.items.map((p) => p.id)).toContain("p21");
  });

  it("요청 경로에 page·page_size 가 **실제로 실린다**(파라미터 없는 호출이 이 결함의 원인이었다)", () => {
    expect(projectsPagePath(1)).toContain(`page_size=${PROJECTS_PAGE_SIZE}`);
    expect(projectsPagePath(3, 50)).toBe("/projects?page=3&page_size=50");
  });
});

describe("[특이도] 과호출·헛돌기를 하지 않는다", () => {
  it("한 페이지로 끝나면 **한 번만** 부른다", async () => {
    const s = pagedServer(7, 100);
    const r = await fetchAllProjects<P>(s.get);
    expect(s.calls).toHaveLength(1);
    expect(r.items).toHaveLength(7);
    expect(r.truncated).toBe(false);
  });

  it("has_next 가 참인데 **빈 페이지**를 주면 멈춘다(서버 오계산에 상한까지 헛돌지 않는다)", async () => {
    const calls: string[] = [];
    const get = async (path: string) => {
      calls.push(path);
      return { items: [], total: 99, has_next: true };
    };
    const r = await fetchAllProjects<P>(get);
    expect(calls).toHaveLength(1);
    expect(r.items).toHaveLength(0);
  });

  it("배열 응답(레거시·목)은 그대로 흡수하고 더 부르지 않는다", async () => {
    const calls: string[] = [];
    const get = async (path: string) => {
      calls.push(path);
      return [{ id: "a", address: "가" }];
    };
    const r = await fetchAllProjects<P>(get);
    expect(calls).toHaveLength(1);
    expect(r.items).toHaveLength(1);
    expect(r.truncated).toBe(false);
  });
});

describe("★조용한 절단 금지 — 끝까지 못 걸었으면 신고한다", () => {
  it("상한에 걸리면 truncated=true", async () => {
    const s = pagedServer(1000, 10);
    const r = await fetchAllProjects<P>(s.get, { pageSize: 10, maxPages: 3 });
    expect(r.pagesFetched).toBe(3);
    expect(r.items).toHaveLength(30);
    expect(r.truncated, "끝까지 못 걸었는데 조용히 성공으로 보고했다").toBe(true);
  });

  it("[양성 대조군] 정상 종료면 truncated=false — 항상 참인 플래그가 아니다", async () => {
    const s = pagedServer(25, 10);
    const r = await fetchAllProjects<P>(s.get, { pageSize: 10, maxPages: 10 });
    expect(r.truncated).toBe(false);
    expect(r.items).toHaveLength(25);
  });
});

describe("★판단 — 고아 선정 자체를 태운다(재료만 잠그면 분기를 지워도 초록이다)", () => {
  const isUuid = (id: string) => /^[0-9a-f]{8}-/.test(id);
  const none: ReadonlySet<string> = new Set();

  it("백엔드에 없는 비UUID 로컬 레코드는 고아다", () => {
    const local: P[] = [{ id: "abc1234", address: "서울 강남구 역삼동 736" }];
    const r = selectOrphans(local, new Set(["다른 주소"]), {
      listComplete: true,
      isUuid,
      inFlight: none,
    });
    expect(r).toHaveLength(1);
  });

  it("★목록이 **불완전**하면 고아 판정을 하지 않는다 — 잘려서 안 보일 뿐인 것을 다시 만들지 않는다", () => {
    const local: P[] = [{ id: "abc1234", address: "서울 강남구 역삼동 736" }];
    const r = selectOrphans(local, new Set(["다른 주소"]), {
      listComplete: false,
      isUuid,
      inFlight: none,
    });
    expect(r, "불완전한 목록으로 '없다'고 판정하면 중복 프로젝트가 생긴다").toHaveLength(0);
  });

  it("[양성 대조군] 같은 입력에서 listComplete 만 뒤집으면 결과가 갈린다 — 두 값이 같으면 배선이 죽은 것", () => {
    const local: P[] = [{ id: "abc1234", address: "고아 주소" }];
    const backend = new Set(["다른 주소"]);
    const complete = selectOrphans(local, backend, { listComplete: true, isUuid, inFlight: none });
    const partial = selectOrphans(local, backend, { listComplete: false, isUuid, inFlight: none });
    expect(complete.length).not.toBe(partial.length);
  });

  it("UUID·인플라이트·백엔드 보유·빈 주소는 고아가 아니다", () => {
    const local: P[] = [
      { id: "0f7a1b2c-aaaa-bbbb-cccc-ddddeeeeffff", address: "UUID 라 제외" },
      { id: "inflight1", address: "생성 중이라 제외" },
      { id: "known01", address: "백엔드에 있음" },
      { id: "blank01", address: "   " },
    ];
    const r = selectOrphans(local, new Set(["백엔드에 있음"]), {
      listComplete: true,
      isUuid,
      inFlight: new Set(["inflight1"]),
    });
    expect(r).toHaveLength(0);
  });

  it("같은 주소의 로컬 중복은 **한 번만** 고아가 된다", () => {
    const local: P[] = [
      { id: "l1", address: "같은 주소" },
      { id: "l2", address: "같은 주소" },
    ];
    const r = selectOrphans(local, new Set(), { listComplete: true, isUuid, inFlight: none });
    expect(r).toHaveLength(1);
  });
});

describe("★배선 — 소비처가 정말 이 SSOT 를 거치는가", () => {
  it("네 소비처가 fetchAllProjects 를 경유한다(파라미터 없는 /projects 호출이 남으면 실패)", () => {
    for (const file of [
      "store/useProjectStore.ts",
      "components/operations/TenantWorkspaceClient.tsx",
      "components/digital-twin/DigitalTwinControlTowerWorkspaceClient.tsx",
      "app/[locale]/(dashboard)/sales-info/page.tsx",
    ]) {
      expect(() =>
        assertWiredThrough({
          file,
          scope: /fetchAllProjects</,
          mustContain: "fetchAllProjects<",
          minMatches: 1,
        }),
      ).not.toThrow();
    }
  });

  it("★고아 판정이 순수 함수를 경유한다 — 루프로 되돌리면 실패한다", () => {
    expect(() =>
      assertWiredThrough({
        file: "store/useProjectStore.ts",
        scope: /const orphans = /,
        mustContain: "selectOrphans(",
        minMatches: 1,
      }),
    ).not.toThrow();
  });
});
