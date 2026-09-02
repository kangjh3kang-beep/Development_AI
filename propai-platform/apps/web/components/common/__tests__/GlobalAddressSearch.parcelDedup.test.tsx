/**
 * ★배선 락 — `GlobalAddressSearch` 가 **실제로** 정체성 규칙을 쓰는가.
 *
 * 모듈 단위 락(`lib/__tests__/parcel-entry-identity.test.ts`)만으로는 이 컴포넌트가 그 함수를
 * 부른다는 것을 아무것도 보고 있지 않다 — 이 저장소가 반복해서 데인 「함수는 잠갔는데
 * 배선은 무잠금」이다. 여기서는 **화면에 몇 필지가 서 있는지**(지도 스텁의 `data-parcels`)를
 * 관측한다.
 *
 * 【두 모집단을 같은 실행에서 가른다】
 *   A 같은 동 주소 + 서로 다른 유효 PNU → **2건 유지**(접히면 안 된다)
 *   B 보강이 표기를 수렴시킨 뒤          → **1건으로 접힌다**(중복이 남으면 안 된다)
 *
 * ★B 가 3단계다. 보강이 짧은 주소를 전체 시군구 주소로 되돌려 주면 두 행이 **바이트 동일**로
 *   수렴하는데, 종전엔 수렴 후 다시 접는 곳이 없어 **같은 필지가 두 건으로 남았다.**
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const postMock = vi.fn();
/** 검색 스텁이 무엇을 고를지 — 테스트마다 바꾼다(빈 div 스텁은 이 경로를 전혀 안 태운다). */
const PICK = { address: "상도동 211-204" };
vi.mock("@/lib/api-client", async (orig) => {
  const actual = await (orig as () => Promise<Record<string, unknown>>)();
  return { ...actual, apiClient: { ...(actual.apiClient as object), post: (...a: unknown[]) => postMock(...a), get: vi.fn() } };
});
vi.mock("@/components/common/MapShell", () => ({
  MapShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  dynamicMap: () => function S() { return <div />; },
}));
// ★검색 스텁은 **실제 콜백을 부른다** — 빈 div 로 두면 「검색→추가」 경로가 전혀 안 태워진다.
vi.mock("@/components/ui/KakaoAddressSearch", () => ({
  KakaoAddressSearch: (props: { onSelect?: (r: Record<string, string>) => void }) => (
    <button
      type="button"
      data-testid="kakao-pick"
      onClick={() =>
        props.onSelect?.({
          fullAddress: PICK.address, roadAddress: "", jibunAddress: PICK.address,
          zonecode: "", sido: "", sigungu: "", bname: "", buildingName: "", bcode: "",
        })
      }
    />
  ),
}));
vi.mock("next/dynamic", () => ({
  default: () =>
    function S(props: { selectedParcels?: unknown[] }) {
      return <div data-testid="map" data-parcels={String(props.selectedParcels?.length ?? 0)} />;
    },
}));

import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const 동 = "경기도 오산시 내삼미동";
const PNU_A = "4137010900100380000";
const PNU_B = "4137010900104670001";
const 짧은 = "상도동 211-204";
const 긴 = "서울특별시 동작구 상도동 211-204";

function seed(parcels: unknown[]) {
  useProjectContextStore.setState({ siteAnalysis: { address: String(parcels[0] && (parcels[0] as { address: string }).address), parcels } } as never);
}
const count = () => Number(screen.getByTestId("map").getAttribute("data-parcels"));


beforeEach(() => {
  PICK.address = 짧은;
  postMock.mockReset();
  postMock.mockResolvedValue({ parcels: [] });   // 기본: 보강이 아무것도 안 바꾼다
});

describe("★A 모집단 — 같은 동 주소의 서로 다른 필지는 접히지 않는다", () => {
  it("PNU 가 다르면 주소가 같아도 2건이 선다", async () => {
    seed([{ address: 동, pnu: PNU_A, areaSqm: 53 }, { address: 동, pnu: PNU_B, areaSqm: 684 }]);
    render(<GlobalAddressSearch single={false} writeToContext />);
    await waitFor(() => expect(screen.getByTestId("map")).toBeInTheDocument());
    // ★공허 진리 가드 — 진입점이 실제로 필지를 만들었는가. 0건이면 아래 단언이 아무것도 안 본다
    //   (첫 실행에서 `writeToContext={false}` 라 0건이었고, 그 상태로도 «붕괴» 로 읽힐 뻔했다:
    //    `buildInitialAddressEntries` 는 `writeToContext && !single` 일 때만 필지를 만든다).
    expect(count(), "★진입점이 필지를 하나도 안 만들었다 — 이 케이스는 공허하다").toBeGreaterThan(0);
    expect(count(), "★같은 동 주소의 다른 필지가 한 건으로 붕괴했다").toBe(2);
  });
});

describe("★B 모집단(3단계) — 보강이 표기를 수렴시킨 뒤 중복이 남지 않는다", () => {
  /**
   * 사용자가 실제로 겪는 순서 그대로:
   *   ① 목록에 전체 주소 필지가 이미 있다 (`서울특별시 동작구 상도동 211-204`)
   *   ② 검색으로 **짧은 표기**를 추가한다 (`상도동 211-204`) — 이 시점엔 **다른 문자열**이라
   *      추가되는 것이 맞다(아직 같은 필지인지 알 수 없다)
   *   ③ 보강이 짧은 주소를 전체 주소로 해소한다 → **같은 필지로 드러난다**
   *   ④ 종전엔 ③ 뒤에 다시 접는 곳이 없어 **두 건으로 남았다**
   */
  it("해소되면 **1건으로** 접힌다", async () => {
    seed([{ address: 긴, pnu: null, areaSqm: 100 }, { address: 동, pnu: PNU_A, areaSqm: 53 }]);
    postMock.mockImplementation((url: string, opts?: { body?: { parcels?: { __rid: number; address: string }[] } }) => {
      if (!String(url).includes("/zoning/parcels-info")) return Promise.resolve({ parcels: [] });
      const rows = opts?.body?.parcels ?? [];
      return Promise.resolve({
        // 짧은 주소만 전체 주소로 해소된다(백엔드 C2 보강). 나머지는 그대로.
        parcels: rows.map((r) => ({
          __rid: r.__rid, status: "ok", area_sqm: 100,
          address: r.address === 짧은 ? 긴 : r.address,
        })),
      });
    });
    render(<GlobalAddressSearch single={false} writeToContext />);
    await waitFor(() => expect(count()).toBe(2));
    fireEvent.click(screen.getByTestId("kakao-pick"));          // ② 짧은 표기 추가
    await waitFor(() => expect(count(), "★다른 문자열인데 추가가 거부됐다").toBe(3));
    await waitFor(
      () => expect(postMock.mock.calls.some((c) => String(c[0]).includes("/zoning/parcels-info")),
        "★보강 요청이 안 나갔다 — 이 케이스는 공허하다").toBe(true),
      { timeout: 4000 },
    );
    // ④ 수렴 후 접힌다 — 3필지 중 짧은/긴 두 표기가 하나가 되어 **2필지**.
    await waitFor(() => expect(count(), "★수렴 후 같은 필지가 두 건으로 남았다").toBe(2), { timeout: 5000 });
  });

  it("★음성 대조군 — 해소가 **안 되면** 접지 않는다(과잉 병합 금지)", async () => {
    seed([{ address: 긴, pnu: null, areaSqm: 100 }, { address: 동, pnu: PNU_A, areaSqm: 53 }]);
    postMock.mockImplementation((url: string, opts?: { body?: { parcels?: { __rid: number }[] } }) => {
      if (!String(url).includes("/zoning/parcels-info")) return Promise.resolve({ parcels: [] });
      const rows = opts?.body?.parcels ?? [];
      // status 가 ok 가 아니면 주소를 갱신하지 않는다 → 여전히 서로 다른 문자열이다.
      return Promise.resolve({ parcels: rows.map((r) => ({ __rid: r.__rid, status: "ambiguous" })) });
    });
    render(<GlobalAddressSearch single={false} writeToContext />);
    await waitFor(() => expect(count()).toBe(2));
    fireEvent.click(screen.getByTestId("kakao-pick"));
    await waitFor(() => expect(count()).toBe(3));
    await waitFor(
      () => expect(postMock.mock.calls.some((c) => String(c[0]).includes("/zoning/parcels-info"))).toBe(true),
      { timeout: 4000 },
    );
    // ★두 모집단이 **다른 결과**를 낸다 — 위는 2, 여기는 3.
    await waitFor(() => expect(count(), "★해소되지 않았는데 병합했다(과잉 교정)").toBe(3), { timeout: 5000 });
  });

  it("★검색 추가 자체가 정체성으로 판정된다 — **같은 필지면 안 늘어난다**", async () => {
    seed([{ address: 짧은, pnu: null, areaSqm: 100 }, { address: 동, pnu: PNU_A, areaSqm: 53 }]);
    render(<GlobalAddressSearch single={false} writeToContext />);
    await waitFor(() => expect(count()).toBe(2));
    fireEvent.click(screen.getByTestId("kakao-pick"));   // 이미 있는 짧은 표기와 **같은 필지**
    await waitFor(() => expect(count(), "★같은 필지가 또 추가됐다").toBe(2));
  });
});


describe("★배선 보강 — 변이 생존 2건을 봉합한다", () => {
  /**
   * ★①은 처음에 **생존**했다. 픽스처가 «같은 문자열» 이라 옛 주소 비교도 같은 결과를 냈다 —
   * **두 모집단이 안 갈렸다.** 표기만 다른 **같은 필지**로 바꿔야 규칙이 드러난다.
   */
  it("① 표기만 다른 같은 필지는 추가되지 않는다(옛 `===` 는 추가했다)", async () => {
    seed([{ address: 짧은, pnu: null, areaSqm: 100 }, { address: 동, pnu: PNU_A, areaSqm: 53 }]);
    PICK.address = "상도동  211-204";        // ★공백만 다르다 — 같은 필지다
    render(<GlobalAddressSearch single={false} writeToContext />);
    await waitFor(() => expect(count()).toBe(2));
    fireEvent.click(screen.getByTestId("kakao-pick"));
    // 옛 코드(`a.fullAddress === entry.fullAddress`)는 문자열이 달라 **3건**이 됐다.
    await waitFor(() => expect(count(), "★표기만 다른 같은 필지가 또 추가됐다").toBe(2));
  });

  /**
   * ★③도 처음에 **생존**했다 — 엑셀 병합 경로가 어떤 테스트에서도 태워지지 않았다.
   * 파일 입력을 실제로 흔들어 `handleExcelUpload` → `/zoning/parse-parcels` 를 태운다.
   */
  async function uploadExcel(rows: Array<Record<string, unknown>>) {
    postMock.mockImplementation((url: string) => {
      if (String(url).includes("/zoning/parse-parcels")) return Promise.resolve({ parcels: rows });
      return Promise.resolve({ parcels: [] });
    });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input, "★파일 입력을 못 찾았다 — 이 케이스는 공허하다").not.toBeNull();
    fireEvent.change(input, { target: { files: [new File(["x"], "조서.xlsx")] } });
    await waitFor(
      () => expect(postMock.mock.calls.some((c) => String(c[0]).includes("/zoning/parse-parcels")),
        "★파싱 요청이 안 나갔다").toBe(true),
      { timeout: 4000 },
    );
  }

  it("③ ★기존 필지가 **같은 주소라는 이유로 지워지지 않는다**(PNU 가 다르면 다른 필지)", async () => {
    seed([{ address: 동, pnu: PNU_B, areaSqm: 684 }, { address: 긴, pnu: null, areaSqm: 100 }]);
    render(<GlobalAddressSearch single={false} writeToContext />);
    await waitFor(() => expect(count()).toBe(2));
    // 업로드분은 **같은 동 주소**지만 **다른 PNU** — 옛 코드는 기존 PNU_B 행을 주소가 같다는
    // 이유로 버렸다(접힘). 새 규칙은 서로 다른 필지로 본다.
    await uploadExcel([{ address: 동, pnu: PNU_A, area_sqm: 53 }]);
    await waitFor(() => expect(count(), "★같은 동 주소라는 이유로 기존 필지가 사라졌다").toBe(3), { timeout: 5000 });
  });

  it("③-b ★음성 대조군 — 정말 같은 필지면 기존분은 안 남는다(과잉 보존 금지)", async () => {
    seed([{ address: 동, pnu: PNU_A, areaSqm: 53 }, { address: 긴, pnu: null, areaSqm: 100 }]);
    render(<GlobalAddressSearch single={false} writeToContext />);
    await waitFor(() => expect(count()).toBe(2));
    await uploadExcel([{ address: 동, pnu: PNU_A, area_sqm: 53 }]);   // 같은 PNU = 같은 필지
    await waitFor(() => expect(count(), "★같은 필지가 두 건으로 남았다").toBe(2), { timeout: 5000 });
  });

  it("④ 엑셀 파일 안의 중복(공유지분 다중행)은 1필지로 정리된다", async () => {
    seed([{ address: 긴, pnu: null, areaSqm: 100 }, { address: 동, pnu: PNU_B, areaSqm: 684 }]);
    render(<GlobalAddressSearch single={false} writeToContext />);
    await waitFor(() => expect(count()).toBe(2));
    // 같은 필지가 소유자별로 3행 — 분석 목록은 **필지 단위**다.
    await uploadExcel([
      { address: 동, pnu: PNU_A, area_sqm: 53 },
      { address: 동, pnu: PNU_A, area_sqm: 53 },
      { address: 동, pnu: PNU_A, area_sqm: 53 },
    ]);
    await waitFor(() => expect(count(), "★같은 필지 3행이 그대로 들어왔다").toBe(3), { timeout: 5000 });
  });
});
