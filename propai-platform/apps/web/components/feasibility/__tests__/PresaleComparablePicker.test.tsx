import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("@/lib/presale-comparables", async (orig) => {
  const real = await orig<typeof import("@/lib/presale-comparables")>();
  return { ...real, fetchNearbyPresale: vi.fn(), fetchPresaleModels: vi.fn() };
});
import { fetchNearbyPresale, fetchPresaleModels } from "@/lib/presale-comparables";
import { PresaleComparablePicker } from "../PresaleComparablePicker";

const near = fetchNearbyPresale as unknown as ReturnType<typeof vi.fn>;
const models = fetchPresaleModels as unknown as ReturnType<typeof vi.fn>;
const ADDR = "경기도 남양주시 화도읍 마석우리 265-1";

describe("분양사례 선택 — 반경·거리·분양가", () => {
  beforeEach(() => { near.mockReset(); models.mockReset(); });

  it("★반경 선택지를 주고, 고른 반경으로 조회한다", async () => {
    near.mockResolvedValue({ items: [], note: null });
    render(<PresaleComparablePicker address={ADDR} onPick={() => {}} />);
    const sel = screen.getByTestId("presale-radius") as HTMLSelectElement;
    // ★20km 선택지가 없으면 이 사업지에서 아무것도 못 본다(실측: 최근접 10.6km)
    expect([...sel.options].map((o) => o.value)).toContain("20000");
    fireEvent.change(sel, { target: { value: "20000" } });
    fireEvent.click(screen.getByTestId("presale-load"));
    await waitFor(() => expect(near).toHaveBeenCalled());
    expect(near.mock.calls[0][1], "고른 반경이 조회에 안 실렸다").toBe(20000);
  });

  it("★0건도 **사유와 함께** 말한다 — 「없다」와 「못 봤다」는 다르다", async () => {
    near.mockResolvedValue({ items: [], note: null });
    render(<PresaleComparablePicker address={ADDR} onPick={() => {}} />);
    fireEvent.click(screen.getByTestId("presale-load"));
    await waitFor(() => expect(screen.getByTestId("presale-empty")).toBeTruthy());
    expect(screen.getByTestId("presale-empty").textContent).toContain("넓혀");
  });

  it("★★단지를 펼치면 주택형별 분양가가 나오고, 고르면 **원/평**으로 돌려준다", async () => {
    near.mockResolvedValue({ items: [{
      house_manage_no: "2026000365", pblanc_no: "2026000365",
      name: "오남역 서희스타힐스 여의재 1단지", address: "경기도 남양주시 오남읍",
      distance_m: 10635, move_in: null, models: [], median_per_pyeong_man: null,
    }], note: null });
    models.mockResolvedValue([
      { house_ty: "059.7153A", supply_area_m2: 83.9533, price_man: 55400, per_pyeong_man: 2181 },
    ]);
    const picked: Array<[number, string]> = [];
    render(<PresaleComparablePicker address={ADDR} onPick={(w, l) => picked.push([w, l])} />);
    fireEvent.click(screen.getByTestId("presale-load"));
    await waitFor(() => expect(screen.getByTestId("presale-item-2026000365")).toBeTruthy());

    // ★거리를 항상 보여 준다 — 반경 안이라도 「얼마나 가까운가」가 판단을 가른다
    expect(screen.getByTestId("presale-item-2026000365").textContent).toContain("10.6km");

    fireEvent.click(screen.getByTestId("presale-item-2026000365"));
    await waitFor(() => expect(screen.getByTestId("presale-pick-059.7153A")).toBeTruthy());
    fireEvent.click(screen.getByTestId("presale-pick-059.7153A"));

    expect(picked).toHaveLength(1);
    // ★만원/평 → 원/평 (수지 입력칸과 같은 단위)
    expect(picked[0][0]).toBe(21_810_000);
    // ★어느 사례에서 왔는지 라벨로 남는다(근거 추적)
    expect(picked[0][1]).toContain("오남역 서희스타힐스");
    expect(picked[0][1]).toContain("공급");
  });

  it("★분양가 미공개 주택형은 **고를 수 없다** — 지어낸 값을 못 쓰게", async () => {
    near.mockResolvedValue({ items: [{
      house_manage_no: "X", pblanc_no: "X", name: "미공개단지", address: "a",
      distance_m: 1000, move_in: null, models: [], median_per_pyeong_man: null,
    }], note: null });
    models.mockResolvedValue([
      { house_ty: "084A", supply_area_m2: 112, price_man: null, per_pyeong_man: null },
    ]);
    render(<PresaleComparablePicker address={ADDR} onPick={() => {}} />);
    fireEvent.click(screen.getByTestId("presale-load"));
    await waitFor(() => expect(screen.getByTestId("presale-item-X")).toBeTruthy());
    fireEvent.click(screen.getByTestId("presale-item-X"));
    await waitFor(() => expect(screen.queryByText(/분양가 미공개/)).toBeTruthy());
    expect(screen.queryByTestId("presale-pick-084A"), "분양가가 없는데 고를 수 있다").toBeNull();
  });
});
