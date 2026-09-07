import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import InstallGuide from "@/components/sales-app/InstallGuide";
import { FIELD_APP_WINDOW_NAME } from "@/lib/field-app-shell";

/**
 * ★`InstallGuide` 계약 — **이 파일에는 테스트가 0건이었다**(모노레포 전수 실측).
 *
 * ## 왜 지금 만드나 (2026-09-07 적대 리뷰 MAJOR-1)
 *
 * PR #1015 가 이 컴포넌트의 가드를 `inAppShell`(standalone ‖ 별도 창)로 넓혔다가
 * **BLOCKER 로 지적받고 `standalone` 만 보도록 되돌렸다.** 그런데 그 왕복을 태우는 락이 없어서,
 * 같은 변이를 형제(`FieldAppAffordance`)에 넣으면 CAUGHT 인데 **여기 넣으면 SURVIVED** 였다:
 *
 *     InstallGuide.tsx        if (standalone) → if (standalone || inSeparateWindow)  → SURVIVED
 *     FieldAppAffordance.tsx  같은 형태의 변이                                        → CAUGHT
 *
 * ★**하필 잠기지 않은 쪽이 「iOS 유일 설치 경로」다.** `FieldAppAffordance` 의 「앱 설치」 단추는
 *   iOS 에서 **영원히 안 뜬다**(`beforeinstallprompt` 부재). 그러니 iOS 사용자의 설치 경로는
 *   **오직 이 컴포넌트의 단계 안내**이고, `DESIGN.md` B3.3 진리표가 *「별도 창 → 설치 유도 **켠다**」*
 *   로 못 박은 칸을 실제로 지키는 코드가 여기다. **그 칸만 락이 없었다.**
 *   ⇒ 「고쳤으나 무잠금」이지 「미수정」이 아니다 — 그 둘을 섞지 않는다.
 *
 * ★런타임(`usePwaRuntime`)만 갈아 끼우고 **판별 로직(`useFieldAppShell`)은 실물을 태운다.**
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

describe("★MAJOR-1 — 설치 안내는 **설치본일 때만** 숨는다(두 모집단)", () => {
  it("설치본(standalone) → 안내를 접고 「앱으로 실행 중」만 남긴다", () => {
    runtime.standalone = true;
    render(<InstallGuide />);
    expect(screen.getByText(/앱으로 실행 중입니다/)).toBeTruthy();
    // 두 모집단 — 설치 유도 표면이 사라진다.
    expect(screen.queryByText(/홈 화면에 앱 추가/)).toBeNull();
  });

  it("★별도 창 안 → 설치 안내가 **살아 있다**(넓은 가드로 되돌리면 여기서 잡힌다)", () => {
    window.name = FIELD_APP_WINDOW_NAME;
    render(<InstallGuide />);
    // 이것이 iOS 의 유일한 설치 경로다 — 별도 창에서 사라지면 안 된다.
    expect(screen.getByText(/홈 화면에 앱 추가/)).toBeTruthy();
    expect(screen.queryByText(/앱으로 실행 중입니다/)).toBeNull();
  });

  it("일반 탭(둘 다 아님) → 안내가 보인다 — 대조군", () => {
    render(<InstallGuide />);
    expect(screen.getByText(/홈 화면에 앱 추가/)).toBeTruthy();
  });
});

describe("별도 창 고지 — 「앱이 아니다」를 정직하게 말한다(두 모집단)", () => {
  it("별도 창 안에서는 주소창이 남는다는 고지가 뜬다", () => {
    window.name = FIELD_APP_WINDOW_NAME;
    render(<InstallGuide />);
    expect(screen.getByText(/별도 창은 주소창이 남아 앱과 다릅니다/)).toBeTruthy();
  });

  it("일반 탭에서는 그 고지가 **없다** — 항상-표시 회귀 방지", () => {
    render(<InstallGuide />);
    expect(screen.queryByText(/별도 창은 주소창이 남아/)).toBeNull();
  });
});

describe("설치 프롬프트 배선", () => {
  it("설치 가능(비-iOS) → 「앱 설치하기」가 실제로 requestInstall 을 부른다", () => {
    runtime.installState = "available";
    render(<InstallGuide />);
    screen.getByRole("button", { name: /앱 설치하기/ }).click();
    expect(runtime.requestInstall).toHaveBeenCalled();
  });

  it("설치 불가 → 「앱 설치하기」가 없다 — 대조군", () => {
    render(<InstallGuide />);
    expect(screen.queryByRole("button", { name: /앱 설치하기/ })).toBeNull();
  });
});

/*
 * ★부채를 초록 안에 보이게 남긴다(§B-13 — 커밋 메시지에만 적으면 드러나지 않는다).
 */
describe("남은 부채", () => {
  it.todo(
    "셸(SiteWorkspaceClient)을 실제로 렌더해 배선을 태운다 — 현재 셸 렌더 커버리지 0. " +
      "FieldShell.wiring.test.ts 는 소스 문자열 검사라 `onNavigate={() => setTab(\"home\")}` 같은 " +
      "틀린 인자를 통과시킨다(적대 리뷰 실증)",
  );
  it.todo(
    "iOS Safari 분기(공유→홈 화면 추가 단계 안내)를 실기기로 태운다 — 현재 장치 부재로 미측정",
  );
});
