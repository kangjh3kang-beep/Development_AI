/**
 * `resolveLayerSourceNote` 순수 계약 — ★**세 상태**가 서로 다른 값을 낸다.
 *
 * 배선 축은 `components/precheck/__tests__/SatongMapShell.layerSourceReason.test.tsx` 가 태운다
 * (순수 함수만 잠그면 «호출부가 안 부른다» 를 못 잡는다 — `#1026` 교훈).
 * 이 파일은 **호출부에서 도달 불가한 입력**까지 직접 태운다.
 */
import { describe, expect, it } from "vitest";

import { resolveLayerSourceNote } from "@/lib/satong-layer-source-note";

describe("resolveLayerSourceNote — 「없음」과 「모름」을 가른다", () => {
  it("★조회했고 0건이면 빈 문자열(화면은 종전대로 「무자료」)", () => {
    expect(resolveLayerSourceNote("경매", { data_source: "onbid_live" })).toBe("");
    expect(resolveLayerSourceNote("분양", { available: true })).toBe("");
  });

  it("★★서버의 사유가 있으면 **그대로** 쓴다 — 프론트가 분류하지 않는다", () => {
    // ★★2026-09-12 2차 정정. 초판은 `data_source:"unavailable"` 을 **「못 봤다」로 단정**했는데,
    //   `onbid_client.py` 는 그 토큰을 **네 갈래**(인증키 미설정·응답 오류·**정직한 0건**·호출 실패)
    //   에 쓴다. 그중 `:308` 「온비드 응답 무자료(해당 조건의 공고 없음)」는
    //   **조회에 성공하고 정말 없는** 경우다 — 거기서 「데이터원 조회 불가」는
    //   ***「없다」를 「못 봤다」로 뒤집는 것***이다(내가 고치려던 결함의 거울상).
    //   ⇒ 프론트는 **분류하지 않는다.** 서버가 자기 말로 준 사유를 그대로 말한다.
    expect(
      resolveLayerSourceNote("경매", { data_source: "unavailable", reason: "온비드 응답 무자료(해당 조건의 공고 없음)" }),
      "서버가 「무자료」라 했는데 내가 「불가」로 덮어썼다",
    ).toBe("경매: 온비드 응답 무자료(해당 조건의 공고 없음)");
    expect(
      resolveLayerSourceNote("경매", { data_source: "unavailable", reason: "온비드 인증키 미설정(공공데이터포털 활용신청 필요)" }),
    ).toContain("인증키 미설정");
    // ★형제 대칭 — 분양은 같은 뜻을 `note` 로 보낸다(`presale_service.py:293`).
    expect(
      resolveLayerSourceNote("분양", { available: false, note: "청약홈 응답 지연" }),
      "분양의 서버 사유를 뭉갰다 — POI 는 reason 을 그대로 올린다",
    ).toBe("분양: 청약홈 응답 지연");
  });

  it("★★사유 없는 `unavailable` 은 **원인을 단정하지 않는다**", () => {
    // 토큰 하나로는 네 갈래를 못 가른다 — 「데이터원 조회 불가」라고 말하면 그중 하나에만 참이다.
    const note = resolveLayerSourceNote("경매", { data_source: "unavailable" });
    expect(note, "사유 없이 원인을 단정했다").not.toContain("데이터원 조회 불가");
    expect(note, "「확인 불가」로 가지 않았다").toContain("확인 불가");
    expect(note, "빈 노트다 — 화면이 부재를 단정한다").not.toBe("");
  });

  it("★사유를 아는 나머지 실패", () => {
    expect(resolveLayerSourceNote("경매", { data_source: "subscriber_only" })).toContain("구독 필요");
    expect(resolveLayerSourceNote("분양", { available: false })).toContain("조회 불가");
  });

  it("★★응답 **자체가 없으면** 「확인 불가」다 — 「무자료」로 떨어뜨리지 않는다", () => {
    // ★독립 리뷰가 «호출부에서 도달 불가» 라고 재 줬다(맞다). **그래도 잠근다** —
    //   도달 불가라는 이유로 원칙에 어긋난 분기를 남기면 되살아나는 날 아무도 다시 안 본다.
    //   ★반증조건: 204·빈 본문처럼 «성공했는데 res 가 없는» 응답이 실재하면 이 줄이 발화한다.
    for (const res of [null, undefined]) {
      const note = resolveLayerSourceNote("경매", res);
      expect(note, "응답이 없는데 빈 노트다 — 화면이 부재를 단정한다").not.toBe("");
      expect(note, "「확인 불가」가 아니다").toContain("확인 불가");
      expect(note, "레이어 이름이 없다").toContain("경매");
    }
  });

  it("★★`mock`·`fallback` 은 **확인된 조회가 아니다** — 0건을 부재로 단정하지 않는다", () => {
    // 「다른 것으로 답했다」이지 「그 출처를 조회했다」가 아니다. 이 제외가 처방의 핵심이다.
    for (const src of ["mock", "fallback"]) {
      expect(resolveLayerSourceNote("경매", { data_source: src }), `${src} 를 성공으로 셌다`).toContain("확인 불가");
    }
  });

  it.todo(
    "★어휘 SSOT 부채 — 같은 `data_source` 토큰을 **반대 뜻으로** 읽는 표면이 이미 배포돼 있다: " +
      "`components/operations/market/DataSourceBadge.tsx:20` 이 `unavailable` 을 **「데이터 없음」** 으로 " +
      "렌더한다(여기서는 「못 봤다」로 읽는다). 그리고 site-analysis 화면은 세 번째 어휘(「조회 불가」)를 쓴다. " +
      "★이 PR 범위 밖으로 뒀다 — 묶으려면 양쪽 소비처를 다 태워야 하고, 그 배지는 다른 화면의 계약이다. " +
      "★처방 방향: 프론트가 토큰을 **분류하지 않게** 하는 것(서버 `reason` 을 그대로 쓰는 이 PR 의 축)을 " +
      "그 배지에도 적용한다",
  );

  it.todo(
    "★실거래 마커 path 클릭이 jsdom 에서 팝업을 열지 않는다(전수 프로브 실측 · 중심 마커는 열린다) — " +
      "원인 **미측정**. ★반증조건: 라이브 브라우저에서도 안 열리면 **사용자 결함**이고 별건이다",
  );

  it("★프로토타입 오염 — `constructor` 같은 키가 사유로 새지 않는다", () => {
    expect(resolveLayerSourceNote("경매", { data_source: "constructor" })).toContain("확인 불가");
    expect(resolveLayerSourceNote("경매", { data_source: "toString" })).toContain("확인 불가");
  });
});
