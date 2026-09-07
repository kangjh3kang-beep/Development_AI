import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import FieldAppAffordance from "@/components/sales-app/FieldAppAffordance";
import { FIELD_APP_WINDOW_NAME } from "@/lib/field-app-shell";

/**
 * ★L3·L4·L5 — 앱 어포던스 계약(2026-09-07 사용자 신고 봉합).
 *
 * 종전엔 이 단추에 **조건이 하나도 없어** 앱 안에서도 계속 떴고, 그것을 태우는 락이 **0건**이었다.
 * 전부 **두 모집단**으로 건다 — "안 보인다"만 단언하면 아무것도 렌더하지 않는 구현이 만점을 받는다.
 *
 * ★`useFieldAppShell`(공용 판별자)은 **모킹하지 않는다**. 브라우저 런타임(usePwaRuntime)만
 *   갈아 끼우고 판별 로직은 실물을 태운다 — 스텁이 검증 대상 층을 우회하지 않게.
 */

const runtime = {
  installState: "unavailable" as "unavailable" | "available",
  standalone: false,
  requestInstall: vi.fn(),
};

vi.mock("@/components/pwa/PwaRuntimeProvider", () => ({
  usePwaRuntime: () => runtime,
}));

beforeEach(() => {
  runtime.installState = "unavailable";
  runtime.standalone = false;
  runtime.requestInstall = vi.fn();
  window.name = "";
});

afterEach(() => {
  window.name = "";
  vi.restoreAllMocks();
});

describe("L3 — 설치 실행 중이면 사라진다(두 모집단)", () => {
  it("standalone=false → 단추가 **보인다**", () => {
    render(<FieldAppAffordance />);
    expect(screen.getByRole("button")).toBeTruthy();
  });

  it("standalone=true → **아무것도 렌더하지 않는다**", () => {
    runtime.standalone = true;
    const { container } = render(<FieldAppAffordance />);
    expect(container.firstChild).toBeNull();
  });
});

describe("L4 — 별도 창 안에서도 사라진다(두 모집단)", () => {
  it("window.name 미설정 → 단추가 **보인다**", () => {
    render(<FieldAppAffordance />);
    expect(screen.getByRole("button")).toBeTruthy();
  });

  it("window.name 이 앱 창 이름 → **아무것도 렌더하지 않는다**", () => {
    window.name = FIELD_APP_WINDOW_NAME;
    const { container } = render(<FieldAppAffordance />);
    expect(container.firstChild).toBeNull();
  });

  it("★다른 이름의 창은 앱 안이 **아니다** — 판별이 과하게 넓어지지 않는다", () => {
    window.name = "some-other-window";
    render(<FieldAppAffordance />);
    expect(screen.getByRole("button")).toBeTruthy();
  });
});

describe("L5 — 라벨이 실제 동작과 일치한다", () => {
  it("설치 프롬프트 가능 → 「앱 설치」를 먼저 권한다", () => {
    runtime.installState = "available";
    render(<FieldAppAffordance />);
    expect(screen.getByRole("button", { name: /앱 설치/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /별도 창/ })).toBeNull();
  });

  it("★「앱 설치」가 실제로 설치를 부른다 — 라벨만 맞고 아무 일도 안 하면 안 된다", () => {
    // 기계적 변이가 짚은 자리: onClick 줄을 지워도 위 케이스는 통과했다(라벨만 봤다).
    runtime.installState = "available";
    render(<FieldAppAffordance />);
    screen.getByRole("button", { name: /앱 설치/ }).click();
    expect(runtime.requestInstall).toHaveBeenCalled();
  });

  it("설치 불가 → 「별도 창으로 열기」", () => {
    render(<FieldAppAffordance />);
    expect(screen.getByRole("button", { name: /별도 창으로 열기/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /앱 설치/ })).toBeNull();
  });

  it("★「앱으로 열기」라고 부르지 않는다 — window.open 은 앱이 아니다(주소창이 남는다)", () => {
    render(<FieldAppAffordance />);
    // 두 모집단: 거짓 라벨은 없고(↓), 참인 라벨은 있다(↑ 위 케이스).
    expect(screen.queryByText(/앱으로 열기/)).toBeNull();
  });
});

describe("★여는 이름과 판별 이름이 같은 상수다(어긋나면 앱 안 판별이 조용히 죽는다)", () => {
  it("window.open 의 창 이름 == FIELD_APP_WINDOW_NAME · 지키지 못할 location=no 를 넣지 않는다", () => {
    const open = vi.spyOn(window, "open").mockReturnValue({ focus: vi.fn() } as unknown as Window);
    render(<FieldAppAffordance />);
    screen.getByRole("button", { name: /별도 창으로 열기/ }).click();

    expect(open).toHaveBeenCalled();
    const [, name, features] = open.mock.calls[0];
    expect(name).toBe(FIELD_APP_WINDOW_NAME);
    // ★현대 브라우저가 무시하는 옵션을 약속하지 않는다(주석이 거짓이 된 원래 결함).
    expect(String(features)).not.toContain("location=no");
    // 대조군 — features 자체는 비어 있지 않다(단언이 공허하지 않다).
    expect(String(features)).toContain("popup=yes");
  });

  it("★팝업이 차단되면 새 탭으로 폴백한다 — 기능이 조용히 죽지 않는다", () => {
    // 기계적 변이가 짚은 자리: 폴백 줄을 바꿔도 아무 락이 안 울었다.
    const open = vi.spyOn(window, "open").mockReturnValue(null); // 차단 상황
    render(<FieldAppAffordance />);
    screen.getByRole("button", { name: /별도 창으로 열기/ }).click();

    expect(open).toHaveBeenCalledTimes(2); // 팝업 시도 → 차단 → 새 탭
    const [, target, features] = open.mock.calls[1];
    expect(target).toBe("_blank");
    // 두 모집단 — 폴백은 팝업 옵션을 들고 가지 않는다(새 탭이지 창이 아니다).
    expect(String(features)).not.toContain("popup=yes");
  });
});

describe("★B2 — 「앱 안」과 「설치 억제」는 다른 명제다(적대 리뷰 BLOCKER 봉합)", () => {
  it("별도 창 안이어도 **설치는 권한다** — 별도 창은 앱이 아니므로 설치가 여전히 개선이다", () => {
    window.name = FIELD_APP_WINDOW_NAME;
    runtime.installState = "available";
    render(<FieldAppAffordance />);
    // 초판은 여기서 null 을 반환해 **팝업 안에서 설치가 원천 봉쇄**됐다.
    expect(screen.getByRole("button", { name: /앱 설치/ })).toBeTruthy();
  });

  it("두 모집단 — 설치본(standalone)이면 그때는 **아무것도 내지 않는다**", () => {
    runtime.standalone = true;
    runtime.installState = "available";
    const { container } = render(<FieldAppAffordance />);
    expect(container.firstChild).toBeNull();
  });

  it("별도 창 안 + 설치 불가 → 「별도 창으로 열기」는 **내지 않는다**(무의미하다)", () => {
    window.name = FIELD_APP_WINDOW_NAME;
    const { container } = render(<FieldAppAffordance />);
    expect(container.firstChild).toBeNull();
  });
});

describe("★F1 — 새 탭 폴백의 역탭내빙 가드(적대 리뷰가 SURVIVED 로 실증한 자리)", () => {
  it("폴백은 noopener·noreferrer 를 들고 간다 — 지워도 초록이던 자리다", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null); // 팝업 차단
    render(<FieldAppAffordance />);
    screen.getByRole("button", { name: /별도 창으로 열기/ }).click();

    const [, , features] = open.mock.calls[1];
    expect(String(features)).toContain("noopener");
    expect(String(features)).toContain("noreferrer");
    // 대조군 — 주 경로(팝업)에는 noopener 를 **넣지 않는다**(넣으면 window.open 이 null 을
    // 돌려줘 폴백이 오작동한다). 형제 간 차이가 **의도된 것**임을 여기서 못 박는다.
    const [, , popupFeatures] = open.mock.calls[0];
    expect(String(popupFeatures)).not.toContain("noopener");
    expect(String(popupFeatures)).toContain("popup=yes");
  });
});
