/**
 * ★렌더 락 — 토지조서 `지번` 칸(사용자 신고 화면 ②).
 *
 * 신고: 77행이 전부 `경기도 오산시 내삼미동`. 이 화면은 **이미** `parcelDisplayAddress` 를
 * 쓰고 있었는데도 안 나았다 — 두 가지 이유가 겹쳐 있었다.
 *   ① 저장된 필지의 PNU 칸에 **주소 문자열**이 들어앉아 지번을 파생할 수 없었다(상류 결함).
 *   ② 병합이 `existing.jibun` 을 무조건 보존해, 상류가 나아도 **기존 행은 영원히 옛 라벨**.
 *
 * 그래서 렌더로 잠근다: 세 모집단이 서로 다른 지번 칸 값을 갖고, 미해석은 그 사실을 말한다.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LandScheduleClient } from "@/components/operations/LandScheduleClient";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useLandScheduleStore, type LandRow } from "@/store/useLandScheduleStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/land-schedule",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

// 지도(next/dynamic)는 jsdom에서 Leaflet 실로드 불가 — 스텁. 검사 대상(표)은 이 화면이 직접 렌더한다.
vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = () => <div data-testid="dynamic-map-stub" />;
    return DynamicStub;
  },
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

const PID = "prj-osan";
const DONG = "경기도 오산시 내삼미동";
const PNU_A = "4137011000104670001"; // → 467-1
const PNU_B = "4137011000101140001"; // → 114-1

function jibunCells(): string[] {
  return screen.getAllByTestId("land-row-jibun").map((el) => (el as HTMLInputElement).value);
}

function seedProject(parcels: SiteAnalysisData["parcels"]) {
  useProjectContextStore.setState({
    projectId: PID,
    projectName: "오산시 내삼미동 외 2필지",
    siteAnalysis: { address: DONG, pnu: PNU_A, parcels } as SiteAnalysisData,
  });
}

describe("토지조서 지번 칸 — 세 모집단", () => {
  beforeEach(() => {
    useLandScheduleStore.setState({ byProject: {} });
  });

  it("★신규 시드: PNU 로 지번을 파생하고, 앵커 없는 행은 '지번 미확인' 을 말한다", () => {
    seedProject([
      { pnu: PNU_A, address: DONG, areaSqm: 100, landCategory: "임야", ownerType: "" },        // (A)
      { pnu: "", address: `${DONG} 114-1`, areaSqm: 100, landCategory: "임야", ownerType: "" }, // (B)
      { pnu: "", address: DONG, areaSqm: 100, landCategory: "임야", ownerType: "" },            // (C)
    ]);
    render(<LandScheduleClient locale="ko" />);

    const cells = jibunCells();
    expect(cells).toHaveLength(3); // 공허 진리 가드: 검사 대상이 실제로 렌더됐다
    expect(cells).toContain(`${DONG} 467-1`);
    expect(cells).toContain(`${DONG} 114-1`);
    expect(cells).toContain(DONG);
    expect(new Set(cells).size).toBe(3);

    // (C) 한 건만 정직 고지 — 셋 다 붙으면 위양성이고, 0건이면 침묵이다.
    expect(screen.getAllByTestId("land-row-jibun-unresolved")).toHaveLength(1);
  });

  it("★기존 행 자가치유: 예전에 **주소만** 으로 시드된 행이 PNU 확보 후 지번을 얻는다", () => {
    // 사용자 프로젝트에 이미 이렇게 저장돼 있다 — 종전 병합은 이 행을 영원히 그대로 뒀다.
    const stale: LandRow = {
      id: "r1", jibun: DONG, pnu: null, owner: "", share: "", area_sqm: 100,
      owner_type: "", expected_price: null, purchase_price: null, contracted: false,
      land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
    };
    useLandScheduleStore.setState({ byProject: { [PID]: [stale] } });
    seedProject([{ pnu: PNU_B, address: DONG, areaSqm: 100, landCategory: "임야", ownerType: "" }]);

    render(<LandScheduleClient locale="ko" />);

    expect(jibunCells()).toEqual([`${DONG} 114-1`]);
    expect(screen.queryByTestId("land-row-jibun-unresolved")).toBeNull();
  });

  it("★사용자가 손댄 지번은 덮어쓰지 않는다(무음 손실 금지)", () => {
    const edited: LandRow = {
      id: "r1", jibun: `${DONG} 999-9`, pnu: null, owner: "김소유", share: "", area_sqm: 100,
      owner_type: "사유지", expected_price: null, purchase_price: null, contracted: false,
      land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
    };
    useLandScheduleStore.setState({ byProject: { [PID]: [edited] } });
    seedProject([{ pnu: PNU_B, address: DONG, areaSqm: 100, landCategory: "임야", ownerType: "" }]);

    render(<LandScheduleClient locale="ko" />);

    expect(jibunCells()).toEqual([`${DONG} 999-9`]);
  });

  it("★재시드 병합: 기존 행에 **PNU 가 채워진다**(등기·대지지분 조회의 정체성)", () => {
    // 행 1 < 필지 2 → 재시드가 돈다(loadFromProject 의 existing 병합 경로).
    const stale: LandRow = {
      id: "r1", jibun: DONG, pnu: null, owner: "김소유", share: "", area_sqm: 100,
      owner_type: "사유지", expected_price: null, purchase_price: null, contracted: false,
      land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
    };
    useLandScheduleStore.setState({ byProject: { [PID]: [stale] } });
    seedProject([
      { pnu: PNU_B, address: DONG, areaSqm: 100, landCategory: "임야", ownerType: "" },
      { pnu: PNU_A, address: DONG, areaSqm: 200, landCategory: "임야", ownerType: "" },
    ]);

    render(<LandScheduleClient locale="ko" />);

    const rows = useLandScheduleStore.getState().byProject[PID] ?? [];
    expect(rows).toHaveLength(2); // 공허 진리 가드: 재시드가 실제로 돌았다
    // 기존 행(사용자 입력 보존)에 PNU 가 실렸다 — 이 줄이 빠지면 등기가 대표 PNU 로 떨어진다.
    const kept = rows.find((r) => r.owner === "김소유");
    expect(kept).toBeDefined();
    expect(kept!.pnu).toBe(PNU_B);
  });

  it("★같은 동 필지가 **한 행에 몰려 같은 id 로 복제**되지 않는다(치유가 엉뚱한 행을 덮어쓴다)", () => {
    const stale: LandRow = {
      id: "r1", jibun: DONG, pnu: null, owner: "김소유", share: "", area_sqm: 100,
      owner_type: "사유지", expected_price: null, purchase_price: null, contracted: false,
      land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
    };
    useLandScheduleStore.setState({ byProject: { [PID]: [stale] } });
    seedProject([
      { pnu: PNU_B, address: DONG, areaSqm: 100, landCategory: "임야", ownerType: "" },
      { pnu: PNU_A, address: DONG, areaSqm: 200, landCategory: "임야", ownerType: "" },
    ]);

    render(<LandScheduleClient locale="ko" />);

    const rows = useLandScheduleStore.getState().byProject[PID] ?? [];
    expect(rows).toHaveLength(2); // 공허 진리 가드: 재시드가 실제로 돌았다
    expect(new Set(rows.map((r) => r.id)).size).toBe(2); // ★id 중복 없음
    // 두 행이 **서로 다른 필지**로 치유됐다(한 행에 몰렸으면 둘이 같아진다).
    expect(new Set(rows.map((r) => r.jibun)).size).toBe(2);
    expect(jibunCells()).toEqual([`${DONG} 114-1`, `${DONG} 467-1`]);
  });

  it("★이미 치유된 라벨의 행에도 PNU 가 채워진다(라벨 치유 이펙트가 안 도는 유일한 경로)", () => {
    // 라벨은 이미 `… 114-1` 이라 staleJibunFixes 는 이 행을 건드리지 않는다.
    // 그때 PNU 를 채우는 곳은 병합의 그 한 줄뿐이다 — 빠지면 등기가 대표 PNU 로 떨어진다.
    const healedLabelNoPnu: LandRow = {
      id: "r1", jibun: `${DONG} 114-1`, pnu: null, owner: "김소유", share: "", area_sqm: 100,
      owner_type: "사유지", expected_price: null, purchase_price: null, contracted: false,
      land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
    };
    useLandScheduleStore.setState({ byProject: { [PID]: [healedLabelNoPnu] } });
    seedProject([
      { pnu: PNU_B, address: DONG, areaSqm: 100, landCategory: "임야", ownerType: "" },
      { pnu: PNU_A, address: DONG, areaSqm: 200, landCategory: "임야", ownerType: "" },
    ]);

    render(<LandScheduleClient locale="ko" />);

    const rows = useLandScheduleStore.getState().byProject[PID] ?? [];
    expect(rows).toHaveLength(2); // 공허 진리 가드: 재시드가 실제로 돌았다
    const kept = rows.find((r) => r.owner === "김소유");
    expect(kept).toBeDefined();
    expect(kept!.jibun).toBe(`${DONG} 114-1`); // 라벨은 그대로(치유 이펙트 미발화 확인)
    expect(kept!.pnu).toBe(PNU_B);             // ★PNU 만 병합이 채웠다
  });

  // ── 적대리뷰 HIGH: 자가치유 **가드**가 무잠금이었다 ──────────────────────────
  //  최후 방어인 "라벨이 시드 원본과 같은가" 는 신고 프로젝트에서 **공허하다**(77개 주소가
  //  전부 같아 어느 필지와 짝지어도 통과). 즉 아래 두 가드가 **유일한 잠금**이다.

  it("★행 수와 필지 수가 다르면 **아무 행도 건드리지 않는다**(인덱스 대응이 성립하지 않는다)", () => {
    // 사용자가 행을 1개 더 만든 상태(77↔78). 가드가 없으면 모든 행이 **이웃 필지**의 지번으로 밀린다.
    const rows: LandRow[] = [0, 1, 2].map((i) => ({
      id: `r${i}`, jibun: DONG, pnu: null, owner: "", share: "", area_sqm: 100,
      owner_type: "", expected_price: null, purchase_price: null, contracted: false,
      land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
    }));
    useLandScheduleStore.setState({ byProject: { [PID]: rows } });
    seedProject([
      { pnu: PNU_B, address: DONG, areaSqm: 100, landCategory: "임야", ownerType: "" },
      { pnu: PNU_A, address: DONG, areaSqm: 200, landCategory: "임야", ownerType: "" },
    ]);

    render(<LandScheduleClient locale="ko" />);

    const cells = jibunCells();
    expect(cells).toHaveLength(3); // 공허 진리 가드: 재시드가 행을 갈아엎지 않았다
    expect(cells).toEqual([DONG, DONG, DONG]); // ★한 행도 밀리지 않았다
    expect(screen.getAllByTestId("land-row-jibun-unresolved")).toHaveLength(3);
  });

  it("★세대행(집합건물 호실)은 필지 지번으로 덮이지 않는다", () => {
    const parent: LandRow = {
      id: "r0", jibun: DONG, pnu: null, owner: "", share: "", area_sqm: 100,
      owner_type: "", expected_price: null, purchase_price: null, contracted: false,
      land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
    };
    const unit: LandRow = { ...parent, id: "r1", parent_id: "r0", unit_label: "101동 1502호" };
    useLandScheduleStore.setState({ byProject: { [PID]: [parent, unit] } });
    seedProject([
      { pnu: PNU_B, address: DONG, areaSqm: 100, landCategory: "임야", ownerType: "" },
      { pnu: PNU_A, address: DONG, areaSqm: 200, landCategory: "임야", ownerType: "" },
    ]);

    render(<LandScheduleClient locale="ko" />);

    const cells = jibunCells();
    expect(cells).toHaveLength(2); // 공허 진리 가드
    // ★두 행이 **다른 처분**을 받아야 한다 — 같으면 parent_id 가드를 지워도 통과한다.
    expect(cells[0]).toBe(`${DONG} 114-1`); // 필지 행: 치유됨
    expect(cells[1]).toBe(DONG);            // 세대 행: 그대로(필지가 아니다)
  });
});
