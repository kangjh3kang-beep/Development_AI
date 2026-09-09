"use client";

/**
 * Stage 2 — **등록 안 된 현장** 발견 + 등록신청.
 *
 * ## 왜 (2026-09-09)
 *
 * 종전 현장 리스트의 빈 상태 문구가 이렇게 말했다:
 *
 * > 소속된 현장이 없습니다. **현장 관리자가 조직도에 추가하면** 여기에 표시됩니다.
 *
 * 즉 사용자가 할 수 있는 일이 **아무것도 없었다.** 신청은 «공고(job_posts)» 를 대상으로만
 * 가능했으므로(`market.apply_post`), 공고를 안 올린 현장에는 «들어가고 싶다» 를 말할 방법이
 * 아예 없었다. 이 패널이 그 막다른 길을 연다.
 *
 * ## 세 관계는 **세 가지 다른 행동**이다
 *
 * | `membership` | 뜻 | 사용자가 할 일 |
 * |---|---|---|
 * | `active` | 이미 멤버 | 위쪽 「내 현장」에서 들어간다 — 여기 안 보인다 |
 * | `pending` | 신청 대기 | **기다린다**(승인자가 결정한다) |
 * | `none` | 미신청 | **신청한다** |
 *
 * ★한 값으로 뭉개면 화면이 무엇을 보여줄지 정할 수 없다. 그래서 서버가 세 값을 준다.
 *
 * ## 단독 컴포넌트인 이유
 *
 * 부모(`SiteListClient`)를 통째로 렌더해야만 태울 수 있으면 락이 무거워지고, 무거우면 안 쓴다.
 * 이 패널은 `apiClient` 만 목킹하면 **혼자 렌더된다.**
 */
import { useCallback, useEffect, useState } from "react";
import { MapPin, Send, Clock3 } from "lucide-react";

import { apiClient } from "@/lib/api-client";
import { STATUS_LABEL } from "@/components/sales-app/roleConfig";

/** 서버 `membership` 의 전체 집합 — 백엔드 `site_join.discover_sites` 와 1:1. */
export const DISCOVER_RELATIONS = ["active", "pending", "none"] as const;
export type DiscoverRelation = (typeof DISCOVER_RELATIONS)[number];

export interface DiscoverSite {
  site_id: string;
  site_code?: string;
  site_name: string;
  development_type?: string;
  status: string;
  membership: DiscoverRelation | string;
}

/**
 * 이 패널이 보여줄 현장 — **이미 들어갈 수 있는 곳은 뺀다.**
 *
 * ★순수 함수로 꺼내 둔 이유: 「무엇을 보여주는가」가 이 컴포넌트의 계약인데,
 *   렌더 안 삼항식에 두면 렌더 없이는 못 재고 그러면 락이 문자열 검사가 된다.
 */
export function selectJoinable(sites: DiscoverSite[]): DiscoverSite[] {
  return sites.filter((s) => s.membership !== "active");
}

export default function DiscoverSitesPanel() {
  const [sites, setSites] = useState<DiscoverSite[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [sendingId, setSendingId] = useState("");
  /** ★신청하려면 **나를 부른 담당자의 이메일**이 필요하다(희망 직속 상위).
   *  그래야 누가 승인하든 같은 자리에 붙는다 — 승인자를 부모로 쓰면 클릭 순서가 체인을 정한다. */
  const [sponsorFor, setSponsorFor] = useState("");
  const [sponsorEmail, setSponsorEmail] = useState("");

  const load = useCallback(() => {
    apiClient
      .get<DiscoverSite[] | { items?: DiscoverSite[] }>("/sales/sites/discover")
      .then((r) => {
        setSites(Array.isArray(r) ? r : (r?.items ?? []));
        setErr("");
      })
      .catch(() => setErr("현장 목록을 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const apply = (siteId: string) => {
    setSendingId(siteId);
    setErr("");
    apiClient
      .post<{ status?: string | null; already_member?: boolean }>(
        `/sales/sites/${siteId}/join-requests`,
        { body: { sponsor_email: sponsorEmail.trim() } },
      )
      .then((r) => {
        // ★서버가 판정한 결과를 **그대로 반영**한다(낙관적으로 'pending' 을 지어내지 않는다).
        //   ★`status` 는 **행 상태**, `already_member` 는 **처리 결과** — 서버가 두 어휘를
        //   분리했다(2026-09-09). 종전엔 한 키에 섞여 있어 프론트가 상태값으로 결과를 읽었다.
        const next = r?.already_member ? "active" : "pending";
        setSites((prev) =>
          prev.map((s) => (s.site_id === siteId ? { ...s, membership: next } : s)),
        );
      })
      .then(() => {
        setSponsorFor("");
        setSponsorEmail("");
      })
      .catch((e) => {
        // ★서버가 왜 거절했는지 **그대로** 보여 준다 — «실패했습니다» 는 진단 불가다.
        //   이메일 오타·그 현장 사람이 아님·직급 부족이 전부 다른 조치를 뜻한다.
        const msg = (e as { message?: string })?.message;
        setErr(msg || "등록신청에 실패했습니다. 잠시 후 다시 시도해 주세요.");
      })
      .finally(() => setSendingId(""));
  };

  const joinable = selectJoinable(sites);

  if (loading) {
    return <div className="sa-skeleton h-24 rounded-2xl" />;
  }

  return (
    <section className="space-y-3">
      <div className="flex items-baseline gap-2">
        <h2 className="text-base font-black text-[var(--text-primary)]">등록 안 된 현장</h2>
        <span className="text-[11px] text-[var(--text-tertiary)]">
          등록신청하면 현장 관리자·상위 레벨이 승인합니다
        </span>
      </div>

      {err && (
        <p className="text-sm font-semibold text-[var(--status-error)]">{err}</p>
      )}

      {joinable.length === 0 ? (
        <p className="text-xs text-[var(--text-tertiary)]">
          신청할 수 있는 현장이 없습니다 — 등록된 현장에 모두 소속되어 있습니다.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {joinable.map((s) => {
            const pending = s.membership === "pending";
            return (
              <li
                key={s.site_id}
                className="flex items-center gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-3"
              >
                <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[var(--surface-soft)] text-[var(--text-tertiary)]">
                  <MapPin className="size-4" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <b className="block truncate text-sm text-[var(--text-primary)]">{s.site_name}</b>
                  <span className="block text-[11px] text-[var(--text-tertiary)]">
                    {STATUS_LABEL[s.status] ?? s.status}
                    {s.site_code ? ` · ${s.site_code}` : ""}
                  </span>
                </span>
                {pending ? (
                  <span className="flex shrink-0 items-center gap-1 rounded-lg bg-[var(--surface-soft)] px-2.5 py-1.5 text-[11px] font-bold text-[var(--text-secondary)]">
                    <Clock3 className="size-3.5" aria-hidden /> 승인 대기
                  </span>
                ) : sponsorFor === s.site_id ? (
                  <span className="flex shrink-0 items-center gap-1">
                    <input
                      value={sponsorEmail}
                      onChange={(e) => setSponsorEmail(e.target.value)}
                      placeholder="나를 부른 담당자 이메일"
                      aria-label="희망 직속 상위 이메일"
                      className="w-44 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1.5 text-[11px] text-[var(--text-primary)] placeholder:text-[var(--text-hint)]"
                    />
                    <button
                      onClick={() => apply(s.site_id)}
                      disabled={sendingId === s.site_id || sponsorEmail.trim().length < 3}
                      className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-black text-white transition hover:opacity-90 disabled:opacity-50"
                    >
                      보내기
                    </button>
                  </span>
                ) : (
                  <button
                    onClick={() => {
                      setSponsorFor(s.site_id);
                      setSponsorEmail("");
                    }}
                    disabled={sendingId === s.site_id}
                    className="flex shrink-0 items-center gap-1 rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-black text-white transition hover:opacity-90 disabled:opacity-50"
                  >
                    <Send className="size-3.5" aria-hidden /> 등록신청
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
