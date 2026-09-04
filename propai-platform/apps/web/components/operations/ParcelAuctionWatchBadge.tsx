"use client";

/**
 * **이 프로젝트 필지의 경·공매 연동 상태**를 필지 문맥에서 보여 준다.
 *
 * ## 왜 필요한가 (2026-08-25 사용자 신고)
 *
 * *"해당 필지(프로젝트)의 경·공매 현황 모니터링과 연동도 안 되고 있다."*
 *
 * **연동은 되어 있었다.** `GET /auction/watchlist` 는 호출마다
 * `sync_landschedule_targets()` 로 **토지조서 필지를 자동 등록**하고,
 * 매칭은 PNU 직접 → 주소 부분 → 폴리곤 순으로 돈다. 토지조서·종합분석 화면에도
 * `공·경매` 지도 레이어가 이미 배선돼 있다.
 *
 * 그런데 **사용자는 그것을 볼 수 없었다**:
 *  · 지도 레이어는 **기본 꺼짐**이다(`SatongMapShell`: `new Set(["cadastre"])`)
 *  · 매칭 **결과**는 전용 `/auction` 페이지에서만 보인다
 *  · 등기·토지조서 화면에는 *"이 필지가 경매에 나왔는가"* 를 말하는 것이 **아무것도 없다**
 *
 * 즉 결함은 배선이 아니라 **작업 흐름 위에 놓이지 않은 것**이다. 이 배지가 그 자리를 잇는다.
 *
 * ## 왜 `/auction/my` 인가 (다른 후보를 재고 골랐다)
 *
 * `/auction/monitor` 는 **구획(폴리곤) 대상에 지오코딩을 돌 수 있고** 구독자 전용이다 —
 * 등기 화면처럼 자주 열리는 곳에서 부르면 지연·비용이 붙는다.
 * `/auction/my?group_by=project` 는 `my_listings()` 가 **순수 SQL 조인**(watch ⋈ items +
 * PNU→project 매핑)이라 **외부 호출이 0**이고, 애초에 **프로젝트별**로 묶여 온다.
 *
 * ## ★"0건"을 뭉뚱그리지 않는다
 *
 * 이 화면에서 침묵·0 은 **네 가지 다른 사실**일 수 있고, 처방이 전부 다르다:
 *  ① 아직 확인 중  ② 조회 실패  ③ 감시는 도는데 **매칭이 없음**  ④ **필지가 없음**
 * 하나로 뭉치면 "연동이 안 된다"는 오해가 그대로 재생산된다 — 그게 이 신고의 출발점이었다.
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Gavel } from "lucide-react";

import { apiClient } from "@/lib/api-client";

type MyAuctionItem = { item_no?: string | null; address?: string | null };
type MyAuctionGroup = { project_id: string | null; items?: MyAuctionItem[] | null };
type MyAuctionResponse = { projects?: MyAuctionGroup[] | null };

/** 이 프로젝트에 매칭된 물건 수. 프로젝트가 목록에 없으면 `0`(감시는 돌지만 매칭 없음). */
export function countForProject(data: MyAuctionResponse | undefined, projectId: string | null): number {
  if (!data?.projects || !projectId) return 0;
  const g = data.projects.find((p) => p.project_id === projectId);
  return g?.items?.length ?? 0;
}

export function ParcelAuctionWatchBadge({
  projectId,
  parcelCount,
  locale = "ko",
  className = "",
}: {
  projectId: string | null;
  parcelCount: number;
  locale?: string;
  className?: string;
}) {
  const q = useQuery({
    queryKey: ["auction-my", "project"],
    queryFn: () => apiClient.get<MyAuctionResponse>("/auction/my?group_by=project", { skipSessionExpiry: true }),
    staleTime: 5 * 60 * 1000,   // 경·공매 목록은 분 단위로 안 바뀐다 — 화면 열 때마다 때리지 않는다.
    retry: false,               // 실패를 조용히 재시도로 덮지 않는다(사유를 말해야 한다).
  });

  const href = `/${locale}/auction`;
  const base =
    "inline-flex flex-wrap items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-bold";

  // ④ 필지가 없다 — 감시 대상 자체가 만들어지지 않는다. 다른 상태와 섞지 않는다.
  if (parcelCount === 0) {
    return (
      <span data-testid="auction-watch-empty-parcels" className={`${base} border-[var(--line)] text-[var(--text-hint)] ${className}`}>
        <Gavel className="size-3.5" aria-hidden />
        필지를 등록하면 경·공매 감시가 자동으로 시작됩니다
      </span>
    );
  }

  // ① 확인 중 — 0 으로 보이지 않게 한다.
  if (q.isPending) {
    return (
      <span data-testid="auction-watch-loading" className={`${base} border-[var(--line)] text-[var(--text-hint)] ${className}`}>
        <Gavel className="size-3.5" aria-hidden />
        경·공매 연동 확인 중…
      </span>
    );
  }

  // ② 조회 실패 — **0건이 아니다.** 모르는 것을 없는 것으로 말하지 않는다.
  if (q.isError) {
    return (
      <span data-testid="auction-watch-error" className={`${base} border-[var(--status-warning)]/40 text-[var(--status-warning)] ${className}`}>
        <Gavel className="size-3.5" aria-hidden />
        경·공매 연동 상태를 확인하지 못했습니다 — 잠시 후 다시 열어 주세요
      </span>
    );
  }

  const n = countForProject(q.data, projectId);

  // ③ 감시는 도는데 매칭이 없다 — **감시가 돌고 있다는 사실**을 함께 말한다.
  if (n === 0) {
    return (
      <Link
        href={href}
        data-testid="auction-watch-none"
        className={`${base} border-[var(--line)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)] ${className}`}
      >
        <Gavel className="size-3.5" aria-hidden />
        경·공매 매칭 없음 — 이 프로젝트 {parcelCount.toLocaleString("ko-KR")}필지는 자동 감시 중입니다
      </Link>
    );
  }

  return (
    <Link
      href={href}
      data-testid="auction-watch-hit"
      className={`${base} border-[var(--status-error)]/40 bg-[var(--status-error)]/10 text-[var(--status-error)] hover:border-[var(--status-error)] ${className}`}
    >
      <Gavel className="size-3.5" aria-hidden />
      이 프로젝트 필지에 경·공매 <b>{n.toLocaleString("ko-KR")}건</b> — 자세히 보기 →
    </Link>
  );
}
