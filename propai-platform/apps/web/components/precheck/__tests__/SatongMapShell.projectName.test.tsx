/**
 * 「새 프로젝트로 등록」 프로젝트명 입력 — **생성 전에 이름을 확정한다**.
 *
 * ## 왜 (2026-09-04 실측)
 *
 * · 생성은 **유료**다 — `satong-project-create.ts` 가 `POST /billing/charge`
 *   (`action: "project_create"`) 를 부른다. **오생성이 곧 낭비**다.
 * · `projects/new` 정본 UX 는 **이름을 먼저 받는데**(`placeholder="예: 성수 IT밸리 복합개발"`)
 *   지도 경로만 주소에서 **자동 파생**했다 — 코드 주석이 *"두 경로의 수렴은 후속 과제"* 라
 *   적어 둔 그 갭이다.
 *
 * ## ★중복은 **프론트에서** 막는다 — 백엔드에 유일성 제약을 넣으면 안 된다
 *
 * `POST /projects` 의 멱등 지문은 **주소만** 본다. 그 이유가 독스트링에 있다:
 * 고아 마이그레이션이 **같은 프로젝트를 재전송**하는데 본문이 다르다.
 * ★그 재전송은 **같은 이름**으로 오므로, 서버 유일성 제약은 **정당한 재전송을 거부**한다.
 * 잔여(다른 탭 동시 생성)는 `PUT /{id}` 로 이름을 바꿀 수 있으므로 **복구 가능**하다.
 *
 * ## 상한은 **백엔드 계약에서 파생**한다
 * `packages/schemas/models.py`: `name: str = Field(min_length=1, max_length=200)`.
 * 내가 지어낸 값을 쓰지 않는다 — 더 관대하면 서버가 422, 더 엄격하면 정당한 이름을 막는다.
 */
import { describe, expect, it, vi } from "vitest";

import {
  isDuplicateProjectName,
  normalizeProjectName,
  PROJECT_NAME_MAX,
} from "@/lib/satong-project-create";

describe("프로젝트명 정규화 — 판정한 문자열과 저장하는 문자열이 같다", () => {
  it("앞뒤 공백을 벗기고 내부 연속 공백을 하나로 만든다", () => {
    expect(normalizeProjectName("  내삼미동   프로젝트  ")).toBe("내삼미동 프로젝트");
  });

  it("★상한은 백엔드 계약값이다(내가 지어낸 값이 아니다)", () => {
    expect(PROJECT_NAME_MAX).toBe(200); // packages/schemas/models.py:99
    expect(normalizeProjectName("가".repeat(300))).toHaveLength(200);
  });

  it("빈 값·공백만이면 빈 문자열 — 그때는 호출부가 **파생 이름**을 쓴다", () => {
    expect(normalizeProjectName("   ")).toBe("");
    expect(normalizeProjectName(null)).toBe("");
    expect(normalizeProjectName(undefined)).toBe("");
  });
});

describe("이름 중복 판정", () => {
  const existing = [{ name: "내삼미동 342-5 외 205필지" }, { name: "상도동 개발" }];

  it("같은 이름은 중복이다", () => {
    expect(isDuplicateProjectName("상도동 개발", existing)).toBe(true);
  });

  it("★공백·대소문자 차이는 같은 이름으로 본다(정규화 후 비교)", () => {
    expect(isDuplicateProjectName("  상도동   개발 ", existing)).toBe(true);
    expect(isDuplicateProjectName("SANGDO Project", [{ name: "sangdo project" }])).toBe(true);
  });

  it("★음성 대조군 — 다른 이름은 중복이 아니다(「전부 막는」 구현과 구별)", () => {
    expect(isDuplicateProjectName("내삼미동 2차", existing)).toBe(false);
  });

  it("★빈 입력은 중복이 아니다 — 파생 이름을 쓰는 경로를 막으면 안 된다", () => {
    expect(isDuplicateProjectName("", existing)).toBe(false);
    expect(isDuplicateProjectName("   ", existing)).toBe(false);
  });

  it("★기존 목록의 이름도 정규화해 비교한다(한쪽만 정규화하면 새는 축)", () => {
    expect(isDuplicateProjectName("상도동 개발", [{ name: "  상도동   개발  " }])).toBe(true);
  });

  it("이름이 없는 레코드는 건너뛴다(빈 이름끼리 「중복」이 되지 않게)", () => {
    expect(isDuplicateProjectName("무제", [{ name: null }, { name: undefined }])).toBe(false);
  });
});

describe("★배선 — 입력한 이름이 **실제로 실린다**", () => {
  // ★「입력창이 있다」가 아니라 **「그 값이 로컬 레코드와 POST 본문에 실린다」**를 본다.
  //   이 저장소가 반복해 데인 형태: 이름만 보는 락은 값이 0 이어도 초록이다.
  const load = async () => {
    vi.resetModules();
    const posted: Array<{ path: string; body: unknown }> = [];
    const added: Array<Record<string, unknown>> = [];
    vi.doMock("@/lib/api-client", () => ({
      apiClient: {
        post: async (path: string, init?: { body?: unknown }) => {
          posted.push({ path, body: init?.body });
          return { id: "backend-uuid" };
        },
      },
    }));
    vi.doMock("@/store/useProjectStore", () => ({
      useProjectStore: {
        getState: () => ({
          addProject: (p: Record<string, unknown>) => {
            added.push(p);
            return "local-1";
          },
          updateProject: () => {},
        }),
      },
      markProjectCreating: () => {},
      unmarkProjectCreating: () => {},
    }));
    vi.doMock("@/lib/project-create-key", () => ({ projectCreateHeaders: () => ({}) }));
    const mod = await import("@/lib/satong-project-create");
    return { mod, posted, added };
  };

  const parcels = [
    { id: "p1", address: "경기도 오산시 내삼미동 356-1", pnu: "4137011000103560001", areaSqm: 100 },
  ] as never;

  it("사용자가 입력한 이름이 로컬 레코드와 POST 본문에 **그대로** 실린다", async () => {
    const { mod, posted, added } = await load();
    await mod.createProjectFromParcels(parcels, { name: "  성수  IT밸리 복합개발 " });
    // ★정규화한 형태로 **양쪽 모두** 실려야 한다(판정 ≠ 소비 방지).
    expect(added[0]?.name).toBe("성수 IT밸리 복합개발");
    const create = posted.find((r) => r.path === "/projects");
    expect((create?.body as { name?: string })?.name).toBe("성수 IT밸리 복합개발");
  });

  it("★음성 대조군 — 미입력이면 **파생 이름**이 실린다(무회귀)", async () => {
    const { mod, posted, added } = await load();
    await mod.createProjectFromParcels(parcels, { name: "   " });
    expect(added[0]?.name).toContain("내삼미동");
    expect(((posted.find((r) => r.path === "/projects")?.body) as { name?: string })?.name)
      .toContain("내삼미동");
  });

  it("★opts 를 아예 안 주면 종전과 동일하다(시그니처 뒤에 추가한 근거)", async () => {
    const { mod, added } = await load();
    await mod.createProjectFromParcels(parcels);
    expect(added[0]?.name).toContain("내삼미동");
  });

  it("★생성이 유료라는 사실을 잠근다 — 과금 호출이 실제로 나간다", async () => {
    // 이 축이 「오생성이 곧 낭비」라는 이 기능의 존재 이유다. 사라지면 근거가 사라진다.
    const { mod, posted } = await load();
    await mod.createProjectFromParcels(parcels, { name: "요금 확인" });
    const charge = posted.find((r) => r.path === "/billing/charge");
    expect((charge?.body as { action?: string })?.action).toBe("project_create");
  });
});
