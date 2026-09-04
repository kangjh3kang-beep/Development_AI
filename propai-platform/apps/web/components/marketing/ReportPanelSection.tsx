"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, BarChart3, MapPin, Search, ShieldCheck, type LucideIcon } from "lucide-react";

/**
 * 리포트 패널 — white 섹션.
 *  • 주소 입력 pill: 미인증 상태이므로 실 분석 호출은 하지 않고
 *    로그인/가입(`/{locale}/login?next=...`)으로 유도한다.
 *  • 보고서 선택 카드 — 실제 제공 산출물 중 **랜딩용으로 선별**한 목록이다.
 *    ★종전 주석은 "creationProducts 기준"이라고 단정했는데 **사실이 아니다**:
 *      `precheck`(후보지 진단서)는 여기 있고 대시보드 카드 목록엔 없다(실측).
 *      두 화면은 각자 선별한다 — 그 문장을 믿고 "부분집합" 락을 걸었다가 CI 에서 걸렸다.
 *    지켜야 할 것은 하나다: **실재하는 라우트만 내건다**(없는 것을 광고하지 않는다).
 */
type ReportOption = {
  id: string;
  title: string;
  desc: string;
  icon: LucideIcon;
  routeId: string;
};

const reports: ReportOption[] = [
  {
    // ★맨 앞 — "지번 하나만"이 이 산출물의 전부이자 차별점이다.
    //   대시보드 `creationProducts` 의 첫 카드와 순서를 맞춘다(두 목록은 서로의 미러다).
    id: "quick-survey",
    title: "간편 분양성 조사",
    desc: "주변시세·계획시설·입지·분양사례 (수요 지표 미포함)",
    icon: Search,
    routeId: "quick-survey",
  },
  {
    id: "precheck",
    title: "후보지 진단서",
    desc: "규제 요약·개발 가능성·다음 액션",
    icon: MapPin,
    routeId: "precheck",
  },
  {
    id: "investment",
    title: "사업성 검토서",
    desc: "ROI·현금흐름·민감도(수지분석)",
    icon: BarChart3,
    routeId: "investment",
  },
  {
    id: "market",
    title: "시장·분양 리포트",
    desc: "시세 범위·경쟁 단지·분양 전략",
    icon: Search,
    routeId: "market-insights",
  },
  {
    id: "permits",
    title: "인허가 체크리스트",
    desc: "허가 가능성·보완 항목·담당 액션",
    icon: ShieldCheck,
    routeId: "permits",
  },
];

export function ReportPanelSection({ locale }: { locale: string }) {
  const router = useRouter();
  const [address, setAddress] = useState("");
  const [selected, setSelected] = useState<string>(reports[0].id);

  function goToLogin() {
    const report = reports.find((r) => r.id === selected) ?? reports[0];
    const params = new URLSearchParams();
    if (address.trim()) params.set("address", address.trim());
    const query = params.toString();
    const next = `/${locale}/${report.routeId}${query ? `?${query}` : ""}`;
    router.push(`/${locale}/login?next=${encodeURIComponent(next)}`);
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    goToLogin();
  }

  return (
    <section className="mkt-section mkt-section--white">
      <div className="mkt-container flex flex-col gap-10">
        <div className="flex flex-col gap-5">
          <span className="mkt-label-pill">
            <span className="mkt-glyph">✦</span>주소 한 줄로
          </span>
          <h2 className="mkt-h2" style={{ maxWidth: "20ch" }}>
            주소 하나로, 보고서가 완성됩니다.
          </h2>
        </div>

        {/* 주소 입력 pill */}
        <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <label htmlFor="mkt-address" className="sr-only">
            분석할 주소
          </label>
          <div
            className="flex flex-1 items-center gap-3"
            style={{
              border: "1px solid var(--mkt-line)",
              borderRadius: 999,
              padding: "6px 8px 6px 22px",
              background: "var(--mkt-white)",
            }}
          >
            <MapPin aria-hidden="true" className="h-5 w-5" style={{ color: "var(--mkt-graphite)" }} strokeWidth={1.5} />
            <input
              id="mkt-address"
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="예: 경기도 광주시 회안대로 637-36"
              autoComplete="off"
              style={{
                flex: 1,
                minWidth: 0,
                border: "none",
                outline: "none",
                background: "transparent",
                fontSize: 16,
                color: "var(--mkt-ink)",
                height: 44,
              }}
            />
            <button type="submit" className="mkt-pill-btn" style={{ whiteSpace: "nowrap" }}>
              보고서 만들기
              <ArrowRight aria-hidden="true" className="mkt-arrow h-[18px] w-[18px]" />
            </button>
          </div>
        </form>

        {/* 보고서 선택 카드 — ★열 수를 개수에 **하드코딩하지 않는다**. `lg:grid-cols-4` 에
            5번째가 들어오면 마지막 한 장이 홀로 떨어진다(카드가 늘 때마다 깨지는 형태).
            `auto-fit` + `minmax` 로 개수와 무관하게 채운다. */}
        <div
          role="radiogroup"
          aria-label="생성할 보고서 종류"
          className="grid gap-3"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}
        >
          {reports.map((r) => {
            const Icon = r.icon;
            const active = selected === r.id;
            return (
              <button
                key={r.id}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setSelected(r.id)}
                className="mkt-card text-left"
                style={{
                  padding: "20px 18px",
                  cursor: "pointer",
                  borderColor: active ? "var(--mkt-accent)" : "var(--mkt-line)",
                  background: active ? "rgba(200,135,63,0.06)" : "var(--mkt-white)",
                  transition: "border-color 200ms var(--mkt-ease), background 200ms var(--mkt-ease)",
                }}
              >
                <span
                  className="inline-flex items-center justify-center"
                  style={{
                    height: 40,
                    width: 40,
                    borderRadius: 12,
                    border: "1px solid var(--mkt-line)",
                    color: active ? "var(--mkt-accent-deep)" : "var(--mkt-ink-soft)",
                  }}
                >
                  <Icon aria-hidden="true" className="h-5 w-5" strokeWidth={1.5} />
                </span>
                <h3
                  style={{
                    marginTop: 14,
                    fontFamily: "var(--mkt-font-sans)",
                    fontWeight: 600,
                    fontSize: 16,
                    color: "var(--mkt-ink)",
                  }}
                >
                  {r.title}
                </h3>
                <p style={{ marginTop: 6, fontSize: 13, lineHeight: 1.5, color: "var(--mkt-graphite)" }}>
                  {r.desc}
                </p>
              </button>
            );
          })}
        </div>

        <p style={{ fontSize: 13, color: "var(--mkt-graphite)" }}>
          공공데이터 기준 자동 생성 · 참고용
        </p>
      </div>
    </section>
  );
}
