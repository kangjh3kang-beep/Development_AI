"use client";

import { parcelJibunResolved, parcelShortLabel } from "@/lib/pnu";

/**
 * 필지 라벨 **단일 표면** — 짧은 지번 라벨 + "지번 미확인" 정직 표기.
 *
 * ## 왜 컴포넌트로 뽑았나 (2026-08-20 — 같은 결함 6번째)
 *
 * `오산시 내삼미동 외 76필지` 프로젝트에서 선택 필지 목록 77행이 **전부 같은 글자**였다.
 * 그때까지의 수정은 전부 "화면마다 라벨 헬퍼를 부르게 고치는" 방식이었는데, 화면이
 * 하나 늘 때마다 **누군가 그 화면을 목록에 넣어 줘야** 했고, 실제로 사통맵 목록·지도
 * 라벨·클릭메뉴는 그 목록에 없어서 계속 인라인 `address.split(/\s+/).slice(-2)` 를 썼다.
 * (`#673` 의 '형제 스윕' 이 이 화면을 빠뜨린 바로 그 실패다 — 사람이 센 목록이 상한.)
 *
 * 그래서 **표면 자체를 하나로** 만든다. 필지 주소를 사용자에게 보여주는 곳은 이 컴포넌트를
 * 쓰고, 이 컴포넌트만 렌더 테스트하면 세 모집단(PNU 보유 / 주소에 지번 보유 / 앵커 없음)의
 * 표시가 한 곳에서 잠긴다.
 *
 * ## 무날조 경계
 *
 * 지번을 확보하지 못했으면 **지어내지 않고** 그 사실을 말한다. 동 단위 주소를 지오코딩해
 * 채우면 같은 동 77필지가 전부 임의의 한 필지(라이브 실측: `114-1`)로 수렴하는
 * **조용한 오답**이 된다 — 같은 라벨이 77번 보이는 것보다 나쁘다.
 */
export const PARCEL_JIBUN_UNRESOLVED_TEXT = "지번 미확인";

export function ParcelJibunLabel({
  address,
  pnu,
  fallback = "필지",
  className = "",
  showUnresolved = true,
}: {
  address?: string | null;
  pnu?: string | null;
  /** 주소·PNU 가 모두 비었을 때 쓸 글자. */
  fallback?: string;
  className?: string;
  /** 좁은 자리(지도 마커 등)에서는 배지를 끄고 title 로만 알린다. */
  showUnresolved?: boolean;
}) {
  const short = parcelShortLabel(address, pnu, fallback);
  const resolved = parcelJibunResolved({ address, pnu });
  // ★이 래퍼에는 `title` 을 걸지 않는다. 필지 카드 등 호출부가 이미 전체 주소를 title 로
  //   달고 있어서, 여기에도 걸면 같은 주소의 title 이 두 개가 되어
  //   `getByTitle(/주소/)` 단일매치가 깨진다(셸 695행 주석이 경고하는 그 함정).
  //   전체 주소는 호출부의 title 이 담당하고, 이 컴포넌트는 **미해석 사실**만 알린다.
  return (
    <span className={`inline-flex min-w-0 max-w-full items-center gap-1 ${className}`}>
      <span className="min-w-0 truncate" data-testid="parcel-jibun-text">
        {short}
      </span>
      {!resolved && showUnresolved && (
        <span
          data-testid="parcel-jibun-unresolved"
          className="shrink-0 rounded-full bg-[var(--status-warning)]/15 px-1.5 py-0.5 text-[10px] font-bold text-[var(--status-warning)]"
        >
          {PARCEL_JIBUN_UNRESOLVED_TEXT}
        </span>
      )}
    </span>
  );
}
