/**
 * 효과기 발화 표면 — ★**선언과 실제가 갈리는 것을 화면이 말하는가.**
 *
 * 이 저장소가 반복해 데인 형태: 백엔드 enum 11종 ↔ 프론트 표 7종이라 **4종이 영문 raw**
 * 로 떴다. 손으로 센 표는 곧 상한이 된다. 그래서 라벨 정합을 **파이썬 원본에서 파생**한다.
 */

import fs from "node:fs";
import path from "node:path";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("@/lib/api-client", () => {
  class ApiClientError extends Error {
    status: number;
    payload: unknown;
    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.name = "ApiClientError";
      this.status = status;
      this.payload = payload;
    }
  }
  return {
    ApiClientError,
    apiClient: { get: (...a: unknown[]) => get(...a), post: vi.fn() },
    apiV1BaseUrl: () => "http://x/api/v1",
  };
});

import { ApiClientError as FakeErr } from "@/lib/api-client";
import { EFFECTOR_STATE_LABELS, GrowthDashboard } from "@/components/settings/GrowthDashboard";

/** 라이브 실측(2026-08-27)을 그대로 옮긴 픽스처 — 세 상태가 **다 들어 있다**. */
const STATUS = {
  effectors: [
    { key: "threshold_relax", declared_reach: "product", total: 47,
      last_fired_at: "2026-08-24T18:50:15Z", hours_since: 66.0, state: "active" },
    { key: "threshold_autotune", declared_reach: "self", total: 441,
      last_fired_at: "2026-08-06T23:46:54Z", hours_since: 493.0, state: "dormant" },
    { key: "prompt_ab_adopt", declared_reach: "none", total: 0,
      last_fired_at: null, hours_since: null, state: "never_fired" },
  ],
  undeclared: [],
  dormant_hours: 72,
  summary: {
    declared: 3, never_fired: 1, dormant: 1, active: 1, undeclared: 0,
    product_reaching_declared: 1, product_reaching_active: 1,
    product_reaching_max_hours_since: 66.0, product_reaching_never_fired: 0,
  },
};

beforeEach(() => {
  get.mockReset();
  get.mockImplementation((p: string) =>
    p.startsWith("/growth/effectors")
      ? Promise.resolve(STATUS)
      : Promise.resolve({ insights: [], total: 0 }),
  );
});

async function openTab() {
  const { default: userEvent } = await import("@testing-library/user-event");
  render(<GrowthDashboard />);
  await userEvent.setup().click(await screen.findByRole("button", { name: "효과기 발화" }));
  return screen.findByTestId("effector-firing");
}

describe("효과기 발화 표면", () => {
  it("★`/growth/effectors` 를 실제로 부른다", async () => {
    await openTab();
    await waitFor(() =>
      expect(get.mock.calls.some((c) => String(c[0]).startsWith("/growth/effectors"))).toBe(true),
    );
  });

  it("★발화 0건 효과기가 **표에 보인다**(그게 이 화면의 존재 이유다)", async () => {
    const el = await openTab();
    const t = el.textContent ?? "";
    expect(t).toContain("prompt_ab_adopt");
    expect(t).toContain(EFFECTOR_STATE_LABELS.never_fired);
  });

  it("★라벨과 **원값**을 함께 낸다 — 라벨에 동의하지 않을 수 있게", async () => {
    const el = await openTab();
    const t = el.textContent ?? "";
    // 66시간은 임계(72) 미만이라 라벨은 `active` 지만, 원값이 보여야 사람이 판단한다.
    expect(t).toContain("66");
    expect(t).toContain("최장 침묵");
  });

  it("★세 상태가 **서로 다른 라벨**을 받는다(뭉치는 구현 방지)", async () => {
    const el = await openTab();
    const t = el.textContent ?? "";
    const labels = ["never_fired", "dormant", "active"].map((k) => EFFECTOR_STATE_LABELS[k]);
    expect(new Set(labels).size, "라벨이 중복이면 상태를 구별할 수 없다").toBe(3);
    for (const l of labels) expect(t).toContain(l);
  });

  it("★조회 실패를 '효과기 없음'으로 위장하지 않는다", async () => {
    get.mockImplementation((p: string) =>
      p.startsWith("/growth/effectors")
        ? Promise.reject(new FakeErr("boom", 500, { detail: "권한 없음" }))
        : Promise.resolve({ insights: [], total: 0 }),
    );
    const { default: userEvent } = await import("@testing-library/user-event");
    render(<GrowthDashboard />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "효과기 발화" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});

describe("★라벨 정합 — 백엔드 상태 어휘에서 **파생**", () => {
  const py = path.resolve(
    __dirname,
    "../../../../api/app/services/growth/effector_firing.py",
  );

  it("★추출기가 살아 있다(공허한 초록 방지)", () => {
    expect(fs.existsSync(py), `백엔드 원본을 못 찾았다: ${py}`).toBe(true);
  });

  it("백엔드가 내는 모든 상태에 한국어 라벨이 있다", () => {
    const src = fs.readFileSync(py, "utf-8");
    const states = [...src.matchAll(/^STATE_[A-Z_]+ = "([a-z_]+)"/gm)].map((m) => m[1]);
    expect(states.length, "★상태 추출 0건 — 추출기가 죽었다(위반 아님)").toBeGreaterThanOrEqual(4);
    const missing = states.filter((s) => !(s in EFFECTOR_STATE_LABELS));
    expect(missing, `라벨 없는 상태(화면에 영문 raw): ${missing.join(", ")}`).toEqual([]);
  });

  it("★역방향 — 백엔드에 없는 유령 라벨이 없다", () => {
    const src = fs.readFileSync(py, "utf-8");
    const states = new Set([...src.matchAll(/^STATE_[A-Z_]+ = "([a-z_]+)"/gm)].map((m) => m[1]));
    const ghosts = Object.keys(EFFECTOR_STATE_LABELS).filter((k) => !states.has(k));
    expect(ghosts, `백엔드에 없는 유령 라벨: ${ghosts.join(", ")}`).toEqual([]);
  });
});
