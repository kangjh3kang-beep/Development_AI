/**
 * 배치 미리보기 섹션(W3) — 표시 계약 + 정직 표기.
 *
 * 고정하는 계약:
 *   ① 조회 전(idle)엔 수치를 만들지 않고 "도면이 아니라 볼륨 감"임을 밝힌다
 *   ② ★`spacing_meaningful=false`(단일동)면 **인동간격을 표시하지 않는다** — 인접동이 없어
 *      개념 자체가 무의미한데 숫자를 보이면 오도다
 *   ③ ★서버 `honest_notes`(v1 한계)를 **그대로** 옮긴다
 *   ④ `ok:false`는 "0동"이 아니라 산출 불가 + 서버 사유(가짜 배치 금지)
 *   ⑤ 일조 충족/미충족은 서버 판정을 그대로 표기한다
 *   ⑥ 대안 토글은 (유형×각도) 키로 동작하고 활성 상태를 aria-pressed로 노출한다
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ParcelLayoutSection } from "@/components/precheck/ParcelLayoutSection";
import type { SiteLayoutOption, SiteLayoutResult } from "@/lib/site-layout";

const NOTE = "v1 한계: 축정렬 직사각형 동·균일 세트백·동지 일조 근사. 부정형 정밀배치·3D 음영은 후속.";

const MULTI: SiteLayoutOption = {
  kind: "판상형", angle_deg: 0, buildings: 3, floors: 5, height_m: 15,
  spacing_meaningful: true, spacing_m: 12, total_units_est: 24,
  yield_pct: 72, openness_pct: 61,
  daylight: { meets_sunlight: true, direct_sun_hours: 5.2 },
};

/** 단일동 — 인접동이 없어 인동간격 개념이 무의미(서버가 spacing_m=null·meaningful=false). */
const SINGLE: SiteLayoutOption = {
  ...MULTI, buildings: 1, spacing_meaningful: false, spacing_m: null,
  daylight: { meets_sunlight: false, direct_sun_hours: 2.1 },
};

const OK = (option: SiteLayoutOption, options?: SiteLayoutOption[]): SiteLayoutResult => ({
  ok: true, honest_notes: [NOTE], buildable_area_sqm: 820, setback_m: 3,
  options: options ?? [option], best: option,
});

describe("ParcelLayoutSection 표시 계약(W3)", () => {
  it("① 조회 전 — 수치 없이 '도면이 아니라 볼륨 감'임을 밝히고 요청 버튼을 준다", () => {
    const onRequest = vi.fn();
    render(
      <ParcelLayoutSection status="idle" onRequest={onRequest} onSelectOption={vi.fn()} />,
    );
    expect(screen.getByText(/도면이 아니라 볼륨 감/)).toBeInTheDocument();
    expect(screen.queryByTestId("parcel-layout-buildings")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("parcel-layout-request"));
    expect(onRequest).toHaveBeenCalledTimes(1);
  });

  it("★② 단일동(spacing_meaningful=false)이면 인동간격을 표시하지 않는다", () => {
    render(
      <ParcelLayoutSection
        status="done" result={OK(SINGLE)} selectedOption={SINGLE}
        onRequest={vi.fn()} onSelectOption={vi.fn()}
      />,
    );
    expect(screen.getByTestId("parcel-layout-buildings").textContent).toBe("1동");
    // ★인접동이 없으므로 간격 배지 자체가 없어야 한다.
    expect(screen.queryByTestId("parcel-layout-spacing")).not.toBeInTheDocument();
    expect(screen.queryByText(/인동간격/)).not.toBeInTheDocument();
  });

  it("★② 방어: meaningful=false인데 숫자가 와도 표시하지 않는다(계약 결합에 의존하지 않는다)", () => {
    // 현재 서버는 `spacing_meaningful: n>1`과 `spacing_m: spacing if n>1 else None`을 **항상
    //   함께** 내므로 두 조건이 결합돼 있다 → `spacing_m != null`만 봐도 결과가 같아, 단순
    //   변이로는 이 가드를 검증할 수 없다(등가 변이). 그러나 화면 규칙은 "단일동이면 간격을
    //   보이지 않는다"이지 "숫자가 없으면 안 보인다"가 아니다. 서버가 언젠가 결합을 깨고
    //   meaningful=false에 숫자를 실어도 오도하지 않도록 **규칙 자체**를 고정한다.
    render(
      <ParcelLayoutSection
        status="done"
        result={OK({ ...SINGLE, spacing_m: 12 })}
        selectedOption={{ ...SINGLE, spacing_m: 12 }}
        onRequest={vi.fn()}
        onSelectOption={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("parcel-layout-spacing")).not.toBeInTheDocument();
    expect(screen.queryByText(/인동간격/)).not.toBeInTheDocument();
  });

  it("② 다동이면 인동간격을 표시한다(서버 값 그대로)", () => {
    render(
      <ParcelLayoutSection
        status="done" result={OK(MULTI)} selectedOption={MULTI}
        onRequest={vi.fn()} onSelectOption={vi.fn()}
      />,
    );
    expect(screen.getByTestId("parcel-layout-spacing").textContent).toContain("12m");
  });

  it("★③ 서버 honest_notes를 그대로 옮긴다(요약·의역 금지)", () => {
    render(
      <ParcelLayoutSection
        status="done" result={OK(MULTI)} selectedOption={MULTI}
        onRequest={vi.fn()} onSelectOption={vi.fn()}
      />,
    );
    expect(screen.getByTestId("parcel-layout-notes").textContent).toBe(NOTE);
  });

  it("★④ ok:false — '0동'이 아니라 산출 불가 + 서버 사유", () => {
    const reason = "세트백 적용 후 건축가능 영역에 표준 동이 들어가지 않습니다.";
    render(
      <ParcelLayoutSection
        status="done"
        result={{ ok: false, honest_notes: [reason], options: [], best: null }}
        onRequest={vi.fn()} onSelectOption={vi.fn()}
      />,
    );
    const box = screen.getByTestId("parcel-layout-unavailable");
    expect(box.textContent).toContain("임의 배치를 만들지 않습니다");
    expect(box.textContent).toContain(reason);
    expect(screen.queryByTestId("parcel-layout-buildings")).not.toBeInTheDocument();
    expect(screen.queryByText("0동")).not.toBeInTheDocument();
  });

  it("⑤ 일조 판정은 서버 값을 그대로(충족/미충족)", () => {
    const { unmount } = render(
      <ParcelLayoutSection
        status="done" result={OK(MULTI)} selectedOption={MULTI}
        onRequest={vi.fn()} onSelectOption={vi.fn()}
      />,
    );
    expect(screen.getByTestId("parcel-layout-daylight").textContent).toContain("충족");
    expect(screen.getByTestId("parcel-layout-daylight").textContent).toContain("5.2h");
    unmount();

    render(
      <ParcelLayoutSection
        status="done" result={OK(SINGLE)} selectedOption={SINGLE}
        onRequest={vi.fn()} onSelectOption={vi.fn()}
      />,
    );
    expect(screen.getByTestId("parcel-layout-daylight").textContent).toContain("미충족");
  });

  it("⑤-b 추정 지표(실현율·세대수·오픈스페이스)를 표시한다", () => {
    render(
      <ParcelLayoutSection
        status="done" result={OK(MULTI)} selectedOption={MULTI}
        onRequest={vi.fn()} onSelectOption={vi.fn()}
      />,
    );
    expect(screen.getByTestId("parcel-layout-yield").textContent).toBe("72%");
    expect(screen.getByText(/연면적 실현율\(추정\)/)).toBeInTheDocument();
    expect(screen.getByText(/세대수\(추정\)/)).toBeInTheDocument();
    expect(screen.getByText(/건축가능\(세트백 3m\)/)).toBeInTheDocument();
  });

  it("⑥ 대안 토글 — 키(유형×각도)로 선택되고 활성 상태를 노출한다", () => {
    const tower: SiteLayoutOption = { ...MULTI, kind: "탑상형" };
    const onSelectOption = vi.fn();
    render(
      <ParcelLayoutSection
        status="done"
        result={OK(MULTI, [MULTI, tower])}
        selectedOption={MULTI}
        selectedKey="판상형@0"
        onRequest={vi.fn()}
        onSelectOption={onSelectOption}
      />,
    );
    expect(screen.getByTestId("parcel-layout-option-판상형@0")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("parcel-layout-option-탑상형@0")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByTestId("parcel-layout-option-탑상형@0"));
    expect(onSelectOption).toHaveBeenCalledWith("탑상형@0");
  });

  it("★모바일 IA P2: done 상태에서만 나타나는 컨트롤도 44px 터치 타깃 하한을 지킨다", () => {
    // ★이 케이스가 필요한 이유: SatongMapShell 의 전수 불변식은 이 섹션을 `status="idle"` 로만
    //   스윕하므로, done 뒤에 나타나는 **대안 칩**과 **설계 시작** 버튼이 그 검사에 잡히지 않는다
    //   (R2 가 변이로 실증 — 하한을 지워도 전건 통과했다). 상태를 만들 수 있는 이 파일에서 잠근다.
    //   ★두 컨트롤은 종전 18px·27px 로 이 상세 패널에서 가장 작았다.
    const tower: SiteLayoutOption = { ...MULTI, kind: "탑상형" };
    render(
      <ParcelLayoutSection
        status="done"
        // ★land_area_sqm 이 있어야 "설계 시작"이 렌더된다(면적 미확인이면 죽은 버튼을 안 그리는
        //   정책 — ParcelLayoutSection.tsx:270). 픽스처가 그 조건을 만족시켜야 검사가 성립한다.
        result={{ ...OK(MULTI, [MULTI, tower]), land_area_sqm: 820 }}
        selectedOption={MULTI}
        selectedKey="판상형@0"
        onRequest={vi.fn()}
        onSelectOption={vi.fn()}
        onSeedDesign={vi.fn()}
      />,
    );

    const floorOk = (el: HTMLElement) => {
      const cls = el.className ?? "";
      for (const m of cls.matchAll(/(?:^|\s)(?:min-)?(?:h|size)-(\d+(?:\.\d+)?)(?=\s|$)/g)) {
        if (Number(m[1]) * 4 >= 44) return true;
      }
      for (const m of cls.matchAll(/(?:^|\s)(?:min-)?(?:h|size)-\[(\d+(?:\.\d+)?)(px|rem)\](?=\s|$)/g)) {
        if ((m[2] === "rem" ? Number(m[1]) * 16 : Number(m[1])) >= 44) return true;
      }
      return false;
    };

    const chip = screen.getByTestId("parcel-layout-option-탑상형@0");
    const seed = screen.getByTestId("parcel-layout-seed-design");
    // 공허 진리 방지 — 둘 다 실제로 렌더된 상태에서만 이 단언이 의미를 갖는다.
    expect(chip).toBeInTheDocument();
    expect(seed).toBeInTheDocument();

    expect(floorOk(chip), `대안 칩이 44px 미달이다: ${chip.className}`).toBe(true);
    expect(floorOk(seed), `설계 시작 버튼이 44px 미달이다: ${seed.className}`).toBe(true);
  });

  it("⑥-b 대안이 1개면 토글을 만들지 않는다(고를 게 없는 UI 금지)", () => {
    render(
      <ParcelLayoutSection
        status="done" result={OK(MULTI)} selectedOption={MULTI}
        onRequest={vi.fn()} onSelectOption={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("parcel-layout-options")).not.toBeInTheDocument();
  });

  it("로딩·실패 상태 — 진행 표시 / 실패는 '0동' 아님 + 재조회", () => {
    const { unmount } = render(
      <ParcelLayoutSection status="loading" onRequest={vi.fn()} onSelectOption={vi.fn()} />,
    );
    expect(screen.getByTestId("parcel-layout-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("parcel-layout-request")).not.toBeInTheDocument();
    unmount();

    const onRequest = vi.fn();
    render(
      <ParcelLayoutSection
        status="error" errorMessage="네트워크 오류"
        onRequest={onRequest} onSelectOption={vi.fn()}
      />,
    );
    expect(screen.getByTestId("parcel-layout-error").textContent).toContain("산출 불가");
    fireEvent.click(screen.getByRole("button", { name: "다시 조회" }));
    expect(onRequest).toHaveBeenCalledTimes(1);
  });
});
