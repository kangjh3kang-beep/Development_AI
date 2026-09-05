import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * ★배선 락 — 순수 함수만 잠그면 **호출부가 무잠금**이다.
 *   이 저장소의 반복 결함: "변이를 함수 안에만 넣으면 5/5 CAUGHT 인데 호출부 한 줄을
 *   되돌리면 전부 초록". 그래서 **세 공급자 전수**를 파생시켜 배선을 직접 태운다.
 *
 * ★목록형을 쓰지 않는다 — 디렉토리에서 공급자를 **파생**시키므로 네 번째 공급자가
 *   추가되면 자동으로 감시망에 들어온다(§수집·판정 규율).
 */

const WEB = path.resolve(__dirname, "..", "..", "..");
const CALLBACK_ROOT = path.join(WEB, "app", "[locale]", "(auth)");
const AUTH_COMPONENTS = path.join(WEB, "components", "auth");

/** `app/[locale]/(auth)/<provider>/callback/page.tsx` 가 있는 공급자를 전수로 모은다. */
function discoverProviders(): string[] {
  return fs
    .readdirSync(CALLBACK_ROOT, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .filter((name) =>
      fs.existsSync(path.join(CALLBACK_ROOT, name, "callback", "page.tsx")),
    )
    .sort();
}

function readPage(provider: string): string {
  return fs.readFileSync(
    path.join(CALLBACK_ROOT, provider, "callback", "page.tsx"),
    "utf-8",
  );
}

function clientFileFor(provider: string): string {
  const comp = provider.charAt(0).toUpperCase() + provider.slice(1);
  return path.join(AUTH_COMPONENTS, `${comp}CallbackWorkspaceClient.tsx`);
}

describe("소셜 콜백 배선", () => {
  const providers = discoverProviders();

  it("공급자를 파생으로 찾는다 — 하한을 걸어 공허한 통과를 막는다", () => {
    // ★이 단언이 없으면 providers=[] 일 때 아래 전부가 「대상 0개」로 조용히 통과한다.
    expect(providers.length).toBeGreaterThanOrEqual(3);
    expect(providers).toEqual(expect.arrayContaining(["google", "kakao", "naver"]));
  });

  it.each(discoverProviders())(
    "%s: page.tsx 가 error·error_description 을 읽어 넘긴다",
    (provider) => {
      const src = readPage(provider);
      // 재료: searchParams 타입에 선언돼 있는가
      expect(src).toMatch(/error\?:\s*string/);
      expect(src).toMatch(/error_description\?:\s*string/);
      // ★행위: 실제로 **prop 으로 전달**하는가 (선언만으로는 배선이 아니다)
      expect(src).toContain("providerError=");
      expect(src).toContain("providerErrorDescription=");
      // 대조군: 기존 code/state 배선이 살아 있는가(회귀 축)
      expect(src).toContain("code=");
      expect(src).toContain("state=");
    },
  );

  it.each(discoverProviders())(
    "%s: 클라이언트가 공용 판정기를 **호출하고 그 결과를 소비**한다",
    (provider) => {
      const file = clientFileFor(provider);
      expect(fs.existsSync(file)).toBe(true);
      const src = fs.readFileSync(file, "utf-8");
      // 재료
      // ★경계를 건다 — `toContain("@/lib/socialLoginError")` 는
      //   `"@/lib/socialLoginErrorXX"` 도 통과시킨다(부분문자열 위음성 · 변이로 실증).
      expect(src).toMatch(/from "@\/lib\/socialLoginError"/);
      expect(src).toContain("providerError?: string | null");
      // ★행위 — 호출과 소비를 각각 태운다(이름만 있는 것과 값이 실리는 것은 다르다)
      expect(src).toMatch(/classifySocialLoginError\(\s*providerError/);
      expect(src).toMatch(/socialLoginErrorMessage\(\s*providerVerdict/);
      // ★소비: 화면 문구 산출에 실제로 쓰이는가
      expect(src).toMatch(/providerMessage\s*(\?\?|\?)/);
      // ★상태도 error 로 넘어가는가
      expect(src).toMatch(/providerVerdict\.kind !== "none"/);
    },
  );

  it("세 공급자가 **같은** 판정기를 쓴다 — 형제가 갈라지면 한쪽만 고쳐진다", () => {
    const imports = discoverProviders().map((p) =>
      /from "@\/lib\/socialLoginError"/.test(
        fs.readFileSync(clientFileFor(p), "utf-8"),
      ),
    );
    expect(imports.every(Boolean)).toBe(true);
    // 대조군: 판정기 파일이 실재해야 위 단언이 의미를 갖는다
    expect(fs.existsSync(path.join(WEB, "lib", "socialLoginError.ts"))).toBe(true);
  });
});
