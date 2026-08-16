import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  timeout: 60_000,

  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:3100",
    trace: "on-first-retry",
    screenshot: "only-on-failure",

    /**
     * ★서비스워커를 막는다 — 이걸 안 막으면 **스펙이 SW 활성화 타이밍에 좌우된다**.
     *
     *   `page.route` 는 페이지가 직접 내는 요청만 가로챈다. **서비스워커가 대신 내는
     *   요청은 가로채지 못한다.** 그래서 prod 빌드에서 이런 일이 벌어졌다(실측 2026-08-16):
     *     · SW 가 아직 제어권을 못 잡은 초반 요청 → 해네스 도달 → `404`(정상 픽스처 경로)
     *     · SW 활성화 이후의 재조회 → SW 의 `fetch()` 가 **실제 네트워크**로 나감 →
     *       백엔드가 없으니 throw → `sw.js:apiNoStore` 가 **503 을 합성** →
     *       화면에 "API request failed with status 503."
     *
     *   즉 같은 URL 이 한 테스트 안에서 404 였다가 503 이 된다. 해네스에 분기가 **있는데도**
     *   픽스처가 안 나와 "해네스 버그"로 오진하기 쉽다(실제로 그렇게 한참 헤맸다).
     *
     *   e2e 는 해네스가 정의한 응답만 봐야 하므로 SW 를 차단한다. SW 자체의 동작
     *   (오프라인 폴백·캐시 버전)은 이 스펙들의 계약이 아니다 — 필요하면 전용 스펙에서
     *   `serviceWorkers: "allow"` 로 따로 검증할 것.
     */
    serviceWorkers: "block",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: process.env.CI
    ? undefined
    : {
        command:
          "NEXT_PUBLIC_USE_MOCKS=false pnpm dev --webpack --hostname 127.0.0.1 --port 3100",
        url: "http://127.0.0.1:3100",
        reuseExistingServer: false,
        timeout: 120_000,
      },
});
