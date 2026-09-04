/**
 * 조직도 시트 — **렌더 경로 + 포커스 트랩**.
 *
 * ## 왜 이 파일이 먼저인가
 *
 * `OrgTree` 는 모달 표면 2개(`aria-modal`)를 갖는데 **포커스 배선이 0** 이었다.
 * 그런데 배선만 먼저 넣으면 **런타임으로 태울 수 없는 배선**이 되고, 그건 소스 검사만
 * 남아 *주석 처리 · 인자 바꿔치기* 변이에 뚫린다(이 저장소가 반복해 데인 형태).
 *
 * 그래서 `FOCUS_UNWIRED` 에 *"조직 픽스처를 세운 뒤 배선한다"* 고 사유를 적어 두었고,
 * 이 파일이 그 **선행 조건**이다 — 먼저 **여는 경로**를 만들고, 그 위에 트랩을 잠근다.
 *
 * ## 이 표면의 성질 (실측)
 *
 * · 시트가 둘이고 **서로 배타적**이다 — `openSheet`/`openAssign` 이 상대를 먼저 닫는다.
 *   그래서 트랩이 겹칠 일이 없다(중첩 트랩 걱정은 여기 해당 없음).
 * · 마운트 즉시 `/org/tree`·`/org/context` 를 조회해야 트리가 그려지고, 그 뒤에야
 *   행 버튼을 눌러 시트를 열 수 있다 — **목 없이는 시트에 닿을 수 없다.**
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const responses: Record<string, unknown> = {};

vi.mock("@/lib/salesApi", () => ({
  salesApi: () => ({
    get: vi.fn((path: string) => {
      const v = responses[path];
      if (v === undefined) return Promise.reject(new Error(`no mock: ${path}`));
      return Promise.resolve(v);
    }),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    del: vi.fn().mockResolvedValue({}),
  }),
}));

import OrgTree from "@/components/sales/OrgTree";

/** 최소 조직 — 루트 하나면 행 버튼이 하나 그려진다. */
const NODES = [
  { id: "n1", path: "1", node_type: "hq", display_name: "본부" },
];

/** 로스터 1행 — "배정" 버튼이 그려져야 `assign` 시트에 닿는다. */
const OVERVIEW = {
  members: 1,
  totals: { contracts: 0, customers: 0, work_logs: 0 },
  roster: [
    {
      node_id: "n1",
      name: "홍길동",
      role_label: "팀원",
      assigned: false,
      contracts: 0,
      customers: 0,
      work_logs: 0,
    },
  ],
};

const CTX = {
  role: "owner",
  org_path: "1",
  addable_types: ["team"],
  scope: "site" as const,
};

/** 훅이 **실제로 가둔 컨테이너**(`useModalFocus` 가 다는 표식). */
function trapEl(): HTMLElement | null {
  return document.body.querySelector<HTMLElement>("[data-modal-focus]");
}

function focusablesIn(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'a[href], button, textarea, input, select, [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((el) => !el.hasAttribute("disabled") && el.getAttribute("aria-hidden") !== "true");
}

beforeEach(() => {
  for (const k of Object.keys(responses)) delete responses[k];
  responses["/org/tree"] = NODES;
  responses["/org/context"] = CTX;
  responses["/org/team-overview"] = OVERVIEW;
});

/** 트리가 그려질 때까지 기다린 뒤 행 액션 시트를 연다. */
async function openActionSheet() {
  render(<OrgTree siteCode="SITE-1" />);
  // ★전제 — 조회가 끝나 트리가 실제로 그려졌는지 먼저 본다.
  //   이게 없으면 아래 "시트가 열렸다"가 **대상 없이** 실패하고 원인이 흐려진다.
  const row = await screen.findByText("본부");
  expect(row, "조직 트리가 그려지지 않았다 — 목이 안 먹었거나 응답 형태가 바뀌었다").toBeTruthy();

  const dialogsBefore = document.body.querySelectorAll('[aria-modal="true"]').length;
  expect(dialogsBefore, "열기도 전에 시트가 떠 있다 — 픽스처 전제가 깨졌다").toBe(0);

  fireEvent.click(screen.getByRole("button", { name: /본부/ }));
  await waitFor(() =>
    expect(
      document.body.querySelectorAll('[aria-modal="true"]').length,
      "행을 눌렀는데 시트가 열리지 않았다 — 여는 경로가 사라졌다",
    ).toBe(1),
  );
}

describe("조직도 시트 — 렌더 경로", () => {
  it("★전제: 목을 세우면 시트까지 **닿을 수 있다**(이 파일의 존재 이유)", async () => {
    await openActionSheet();
    const sheet = document.body.querySelector<HTMLElement>('[aria-modal="true"]');
    expect(sheet).not.toBeNull();
    expect(
      focusablesIn(sheet as HTMLElement).length,
      "시트에 포커스 가능 요소가 0개 — 트랩 단언이 공허해진다",
    ).toBeGreaterThan(0);
  });

  it("★음성대조 — 조회가 실패하면 트리가 비고 시트에 닿을 수 없다(목이 실제로 쓰인다는 증거)", async () => {
    responses["/org/tree"] = [];
    render(<OrgTree siteCode="SITE-1" />);
    await waitFor(() => expect(screen.queryByText("본부")).toBeNull());
    expect(document.body.querySelectorAll('[aria-modal="true"]').length).toBe(0);
  });
});

/** 로스터의 "배정" 버튼으로 **두 번째 시트**를 연다. */
async function openAssignSheet() {
  render(<OrgTree siteCode="SITE-1" />);
  const btn = await screen.findByRole("button", { name: "배정" });
  expect(btn, "로스터가 그려지지 않았다 — team-overview 목이 안 먹었다").toBeTruthy();
  fireEvent.click(btn);
  await waitFor(() =>
    expect(
      document.body.querySelectorAll('[aria-modal="true"]').length,
      "배정 버튼을 눌렀는데 시트가 열리지 않았다",
    ).toBe(1),
  );
}

describe("조직도 시트 — 포커스 생명주기", () => {
  it("★열면 포커스가 시트 **안**으로 들어온다", async () => {
    await openActionSheet();
    const trap = trapEl();
    expect(trap, "훅이 가둔 컨테이너가 없다 — 포커스 배선이 없거나 죽었다").not.toBeNull();
    expect(
      (trap as HTMLElement).contains(document.activeElement),
      "시트를 열었는데 포커스가 밖에 있다",
    ).toBe(true);
  });

  it("★마지막 요소에서 Tab 하면 첫 요소로 **돈다**(트랩)", async () => {
    await openActionSheet();
    const items = focusablesIn(trapEl() as HTMLElement);
    items[items.length - 1].focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement, "Tab 이 시트 밖으로 샌다").toBe(items[0]);
  });

  it("★Shift+Tab 은 첫 요소에서 마지막으로 돈다(경계는 한 쌍)", async () => {
    await openActionSheet();
    const items = focusablesIn(trapEl() as HTMLElement);
    items[0].focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement, "역방향 트랩이 없다").toBe(items[items.length - 1]);
  });

  it("★음성대조 — Tab 이 아닌 키는 포커스를 옮기지 않는다(판별력)", async () => {
    await openActionSheet();
    const items = focusablesIn(trapEl() as HTMLElement);
    const probe = items[Math.min(1, items.length - 1)];
    probe.focus();
    fireEvent.keyDown(document, { key: "Enter" });
    fireEvent.keyDown(document, { key: "a" });
    expect(document.activeElement, "아무 키에나 포커스를 옮긴다").toBe(probe);
  });

  // ── ★형제 표면 — 이 파일은 처음에 `sheet` 만 태웠고, `assign` 배선을 지워도 초록이었다 ──
  //   (변이 검증이 잡았다). **한 파일에 표면이 둘이면 둘 다 태워야 한다.**
  it("★형제 시트(인원 배정)도 트랩된다 — 하나만 잠그면 나머지가 샌다", async () => {
    await openAssignSheet();
    const trap = trapEl();
    expect(trap, "배정 시트에 트랩이 없다 — 형제 배선이 빠졌다").not.toBeNull();
    expect(
      (trap as HTMLElement).contains(document.activeElement),
      "배정 시트를 열었는데 포커스가 밖에 있다",
    ).toBe(true);
  });

  it("★형제 시트도 Tab 이 **돈다**", async () => {
    await openAssignSheet();
    const items = focusablesIn(trapEl() as HTMLElement);
    expect(items.length, "배정 시트에 포커스 요소가 0개 — 단언이 공허하다").toBeGreaterThan(0);
    items[items.length - 1].focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement, "배정 시트에서 Tab 이 샌다").toBe(items[0]);
  });

  it("★트랩 대상이 **시트 본체**다 — 이 표면은 ARIA 가 본체에 있다(다른 모달과 반대)", async () => {
    // ★모달마다 `aria-modal` 이 붙는 자리가 다르다. 대부분은 **백드롭**에 있는데
    //   `OrgTree` 는 **본체**에 있다(`onClick={stopPropagation}` 과 같은 요소).
    //   그래서 `[aria-modal]` 로 트랩 범위를 재면 표면마다 결과가 갈린다 —
    //   드로어에서 배운 것과 같은 축이다. **훅이 실제로 가둔 표식**을 기준으로 재야 한다.
    await openActionSheet();
    const ariaEl = document.body.querySelector<HTMLElement>('[aria-modal="true"]');
    const trap = trapEl();
    expect(trap, "트랩된 컨테이너가 없다").not.toBeNull();
    // 이 표면에서는 둘이 **같은 요소**여야 한다(ARIA 가 본체에 있으므로).
    expect(trap, "트랩 대상이 ARIA 표면과 다르다 — ref 가 엉뚱한 요소에 달렸다").toBe(ariaEl);
    // 백드롭(=부모)은 트랩 대상이 아니어야 한다.
    expect(
      (trap as HTMLElement).parentElement?.hasAttribute("data-modal-focus"),
      "백드롭까지 트랩됐다 — 범위가 시트보다 넓다",
    ).toBeFalsy();
  });
});
