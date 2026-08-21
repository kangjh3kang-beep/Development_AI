/**
 * ★★이번 결함의 **진짜 상류** 배선 락 — 엑셀 소재지/지번 분리 양식.
 *
 * 라이브 실측(2026-08-20): `/zoning/parse-parcels` 는 `소재지 | 지번` 분리 양식을
 * `address="경기도 오산시 내삼미동"` · `jibun="467-1"` · `pnu="4137…0001"` 로 **정직하게 나눠**
 * 돌려준다. 사통맵 유입부가 `parcel.address || parcel.jibun` 로 받아 **지번을 통째로 버렸다**
 * (`||` 라 소재지가 있으면 지번은 평가조차 되지 않는다).
 *
 * 형제 화면 `GlobalAddressSearch` 는 같은 결합을 **2026-06-17 에 이미** 갖고 있었고,
 * 13일 뒤 태어난 이 유입부가 그 목록에 없어 결함을 그대로 재도입했다.
 * 순수함수(joinAddressJibun) 테스트로는 **이 화면이 그걸 쓰는지** 알 수 없어 셸을 직접 태운다.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { readSatongMapSelection } from "@/components/precheck/satong-map-selection";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = () => <div data-testid="dynamic-map-stub" />;
    return DynamicStub;
  },
}));

/** 백엔드 parse-parcels 응답(라이브 실측 형태 그대로 — 소재지·지번 분리). */
const parsed = {
  parcels: [
    { address: "경기도 오산시 내삼미동", jibun: "467-1", pnu: "4137011000104670001", area_sqm: 53, status: "ok" },
    // ★결합이 **유일한 구조선**인 행: 지번은 있는데 PNU 해석에 실패했다(bcode 미상 + 지오코딩
    //   미스). 결합하지 않으면 지번이 증발하고 PNU 로 되살릴 수도 없다 — 이 행이
    //   `address || jibun` 변이를 죽인다(PNU 있는 행은 PNU 로도 지번이 나와 변이를 못 잡는다).
    { address: "경기도 오산시 내삼미동", jibun: "500-3", pnu: null, area_sqm: 88, status: "ok" },
    // PNU 도 지번도 못 얻은 행 2건 — 주소가 완전히 같다(#672 의 "77 → 1" 이 나던 조건).
    { address: "경기도 오산시 내삼미동", jibun: null, pnu: null, area_sqm: 100, status: "ambiguous" },
    { address: "경기도 오산시 내삼미동", jibun: null, pnu: null, area_sqm: 200, status: "ambiguous" },
    // 주소·지번·PNU 가 모두 빈 행 — 폴백 라벨이 없으면 `readSatongMapSelection` 의
    // "주소 비어있으면 제외" 필터에 걸려 **행이 조용히 사라진다**(무음 손실).
    { address: null, jibun: null, pnu: null, area_sqm: 12, status: "failed" },
  ],
};

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending),
      post: vi.fn((path: string) =>
        path === "/zoning/parse-parcels" ? Promise.resolve(parsed) : pending(),
      ),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

async function uploadExcel(container: HTMLElement) {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  expect(input).toBeTruthy(); // 공허 진리 가드: 업로드 입구가 실재한다
  const file = new File(["a"], "토지조서.csv", { type: "text/csv" });
  Object.defineProperty(input, "files", { value: [file] });
  const { fireEvent } = await import("@testing-library/react");
  fireEvent.change(input);
}

describe("엑셀 업로드 — 소재지/지번 분리 양식", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("★분리된 지번이 라벨에 살아 남는다(구 동작은 소재지만 남기고 버렸다)", async () => {
    const { container } = render(<SatongMapShell locale="ko" />);
    await uploadExcel(container);

    await waitFor(() => expect(screen.getAllByTestId("parcel-jibun-text")).toHaveLength(5));
    const texts = screen.getAllByTestId("parcel-jibun-text").map((el) => el.textContent);
    expect(texts).toContain("내삼미동 467-1"); // PNU 로도, 결합으로도 나온다
    // ★PNU 가 없는 행은 **결합만이** 지번을 살린다 — 여기가 이 수정의 진짜 잠금.
    expect(texts).toContain("내삼미동 500-3");
  });

  it("★PNU 없이 지번만 온 행은 결합 덕에 '미해석' 이 아니다(정직 배지 위양성 차단)", async () => {
    const { container } = render(<SatongMapShell locale="ko" />);
    await uploadExcel(container);

    await waitFor(() => expect(screen.getAllByTestId("parcel-jibun-text")).toHaveLength(5));
    // 5행 중 지번을 확보한 2행(PNU 보유 1 + 지번만 1)은 배지가 없고, 나머지 3행에 붙는다.
    expect(screen.getAllByTestId("parcel-jibun-unresolved")).toHaveLength(3);
  });

  it("★주소가 완전히 같고 PNU 도 없는 행이 **1건으로 접히지 않는다**(#672 원증상)", async () => {
    const { container } = render(<SatongMapShell locale="ko" />);
    await uploadExcel(container);

    await waitFor(() => expect(screen.getAllByTestId("parcel-jibun-text")).toHaveLength(5));
    // 영속까지 확인 — 화면만 4건이고 세션에 1건이면 재진입에서 사라진다.
    expect(readSatongMapSelection()?.parcels).toHaveLength(5);
    // 해석된 2건과 미해석 3건이 **다른 처분**을 받는다(전부 같으면 배선을 끊어도 통과한다).
    expect(screen.getAllByTestId("parcel-jibun-unresolved")).toHaveLength(3);
    // ★주소·지번·PNU 가 모두 빈 행도 **사라지지 않는다**. 폴백 라벨이 없으면 주소가 빈 문자열이
    //   되고 `readSatongMapSelection` 의 "주소 비어있으면 제외" 필터가 그 행을 조용히 버린다.
    //   (화면 라벨은 뒤 두 토큰으로 줄어드므로 영속된 원본 주소로 확인한다.)
    expect(readSatongMapSelection()?.parcels.map((p) => p.address)).toContain("엑셀 등록 필지");
  });
});
