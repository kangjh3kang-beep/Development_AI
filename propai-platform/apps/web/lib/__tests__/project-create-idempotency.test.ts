/**
 * 프로젝트 생성 멱등키 — **한 시도 = 한 키**.
 *
 * `#815`(같은 탭 인플라이트 레지스트리)·`#822`(목록 절단으로 인한 고아 오판)는 둘 다
 * **클라이언트 처방**이라 다른 탭·기기·재설치에는 닿지 않는다. 서버가 키를 기억하면 닫힌다.
 */
import { describe, expect, it } from "vitest";

import {
  PROJECT_CREATE_KEY_PREFIX,
  projectCreateHeaders,
  projectCreateIdempotencyKey,
} from "@/lib/project-create-key";
import { assertWiredThrough } from "@/lib/source-invariant";

describe("★판단 — 키는 내용이 아니라 시도로 만든다", () => {
  it("같은 로컬 id 는 **같은 키**(재전송이 재생된다)", () => {
    expect(projectCreateIdempotencyKey("abc1234")).toBe(
      projectCreateIdempotencyKey("abc1234"),
    );
  });

  it("★다른 시도는 **다른 키** — 같은 부지로 두 번째 프로젝트를 만들 수 있어야 한다", () => {
    // 주소·이름으로 키를 만들면 이 단언이 깨진다. 프로덕션에 같은 주소로 의도적으로 만든
    // 프로젝트가 실재한다(검증용 2건) — 그것을 막으면 정상 사용을 막는 것이다.
    expect(projectCreateIdempotencyKey("abc1234")).not.toBe(
      projectCreateIdempotencyKey("zzz9999"),
    );
  });

  it("키에 접두가 붙어 다른 엔드포인트의 키 공간과 섞이지 않는다", () => {
    expect(projectCreateIdempotencyKey("abc1234")).toBe(
      `${PROJECT_CREATE_KEY_PREFIX}abc1234`,
    );
  });

  it("id 가 비면 키를 만들지 않는다 — 헤더를 붙이지 않고 종전 동작", () => {
    expect(projectCreateIdempotencyKey("")).toBeUndefined();
    expect(projectCreateIdempotencyKey(null)).toBeUndefined();
    expect(projectCreateIdempotencyKey("   ")).toBeUndefined();
    expect(projectCreateHeaders(null)).toEqual({});
  });

  it("[양성 대조군] id 가 있으면 헤더가 실제로 만들어진다 — 항상 빈 객체가 아니다", () => {
    expect(projectCreateHeaders("abc1234")).toEqual({
      "Idempotency-Key": "project-create:abc1234",
    });
  });
});

describe("★배선 — 생성 POST 세 곳이 모두 키를 보낸다", () => {
  it("최초 생성 2경로 + 고아 재전송 1경로 (하나라도 빠지면 그 경로로 중복이 샌다)", () => {
    for (const file of [
      "lib/satong-project-create.ts",
      "app/[locale]/(dashboard)/projects/new/page.tsx",
      "store/useProjectStore.ts",
    ]) {
      expect(() =>
        assertWiredThrough({
          file,
          scope: /headers: projectCreateHeaders\(/,
          mustContain: "projectCreateHeaders(",
          minMatches: 1,
        }),
      ).not.toThrow();
    }
  });

  it("★고아 재전송이 **최초 생성과 같은 값**(로컬 레코드 id)을 쓴다 — 다른 값이면 중복이 생긴다", () => {
    expect(() =>
      assertWiredThrough({
        file: "store/useProjectStore.ts",
        scope: /headers: projectCreateHeaders\(/,
        mustContain: "projectCreateHeaders(o.id)",
        minMatches: 1,
      }),
    ).not.toThrow();
  });
});
