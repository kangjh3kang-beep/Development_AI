"use client";

/**
 * 간편 분양성 조사 — 지번 하나로 공급·가격 축을 한 화면에.
 *
 * ★이 화면의 설계 원칙은 "빨리 보여주기"가 아니라 **범위를 오해하지 않게 하기**다.
 *   백엔드가 `demand_indicators`(수요 축 미연동)와 `scope_note`를 항상 실어 보내므로,
 *   화면은 그것을 **접어 두지 않고 본문에** 띄운다. 접으면 "안 본 것"과 "없는 것"이 같아진다.
 */

import { useState } from "react";
import { apiClient } from "@/lib/api-client";

type MissingRow = { name: string; reason: string };
type Block = { available: boolean; count?: number; items?: unknown[]; note?: string };

type Survey = {
  address: string;
  generated_at?: string;
  scope_note?: string;
  market?: {
    zone_type?: string | null;
    official_price_per_sqm?: number | null;
    sections_present?: string[];
    sections_missing?: string[];
    narrative?: { summary?: string } | null;
  };
  planned_facilities?: Block & { source?: string; radius_m?: number };
  presale_cases?: Block & { source?: string; radius_m?: number };
  demand_indicators?: { available: boolean; missing?: MissingRow[]; note?: string };
};

const SECTION_LABEL: Record<string, string> = {
  trade: "매매 실거래",
  rent: "전월세 실거래",
  apt_trend: "시세 추이",
  infrastructure: "입지·인프라",
  demographics: "인구·소득",
  pricing_band: "분양가 적정성",
};

export function QuickSalesSurveyClient() {
  const [address, setAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<Survey | null>(null);

  const run = async () => {
    const target = address.trim();
    if (!target) {
      setError("지번 주소를 입력해 주세요.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // ★두 번째 인자는 body 가 아니라 **옵션**이다(`{ body }` 로 감싼다).
      //   시그니처를 추측해서 넘기면 서버가 422 를 내고 화면은 "조회 실패"만 보인다.
      // ★타임아웃을 넉넉히 준다 — 상위 시장조사 엔진은 비동기 잡을 따로 둘 만큼 무겁다.
      const res = await apiClient.post<Survey>("/market/quick-survey", {
        body: { address: target, use_llm: true },
        timeoutMs: 180_000,
      });
      setData(res);
    } catch (e) {
      // ★실패를 조용히 두지 않는다 — 빈 화면은 "자료 없음"으로 오독된다.
      setError(e instanceof Error ? e.message : "조회에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 p-4 sm:p-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight text-[var(--foreground)]">
          간편 분양성 조사
        </h1>
        <p className="text-sm leading-relaxed text-[var(--muted-foreground)]">
          지번 하나만 입력하면 주변시세·계획시설·입지·분양사례를 한 화면에 모아 드립니다.
        </p>
      </header>

      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void run();
          }}
          placeholder="예) 서울특별시 강남구 역삼동 123-4"
          aria-label="지번 주소"
          className="min-h-11 flex-1 rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 text-sm text-[var(--foreground)]"
        />
        <button
          type="button"
          onClick={() => void run()}
          disabled={loading}
          className="min-h-11 rounded-lg bg-[var(--accent-strong)] px-5 text-sm font-semibold text-white disabled:opacity-60"
        >
          {loading ? "조사 중…" : "조사하기"}
        </button>
      </div>

      {error ? (
        <p role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-600">
          {error}
        </p>
      ) : null}

      {data ? (
        <div className="space-y-4">
          {/* ★범위 고지를 **본문 최상단**에 둔다 — 접거나 각주로 내리면 오해가 남는다. */}
          {data.scope_note ? (
            <p className="rounded-lg border border-[var(--border)] bg-[var(--muted)]/40 p-3 text-sm leading-relaxed text-[var(--muted-foreground)]">
              {data.scope_note}
            </p>
          ) : null}

          <section className="rounded-xl border border-[var(--border)] p-4">
            <h2 className="mb-2 text-base font-semibold">시세·입지 요약</h2>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-[var(--muted-foreground)]">용도지역</dt>
                <dd className="font-medium">{data.market?.zone_type ?? "미확보"}</dd>
              </div>
              <div>
                <dt className="text-[var(--muted-foreground)]">공시지가(㎡)</dt>
                <dd className="font-medium">
                  {typeof data.market?.official_price_per_sqm === "number"
                    ? `${data.market.official_price_per_sqm.toLocaleString()}원`
                    : "미확보"}
                </dd>
              </div>
            </dl>
            {data.market?.sections_missing?.length ? (
              <p className="mt-3 text-xs text-amber-600">
                미확보 섹션:{" "}
                {data.market.sections_missing.map((k) => SECTION_LABEL[k] ?? k).join(" · ")}
              </p>
            ) : null}
          </section>

          <SurveyBlock title="계획 고시된 시설(개발 영향)" block={data.planned_facilities} />
          <SurveyBlock title="주변 분양사례" block={data.presale_cases} />

          {/* ★수요 축 결손 — 항상 렌더한다. 이 블록이 이 화면의 정직성 그 자체다. */}
          <section className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4">
            <h2 className="mb-2 text-base font-semibold">수요 지표 — 미포함</h2>
            <p className="mb-2 text-sm leading-relaxed text-[var(--muted-foreground)]">
              {data.demand_indicators?.note ?? "수요 축 데이터원이 연결되지 않았습니다."}
            </p>
            <ul className="space-y-1 text-sm">
              {(data.demand_indicators?.missing ?? []).map((m) => (
                <li key={m.name}>
                  <span className="font-medium">{m.name}</span>
                  <span className="text-[var(--muted-foreground)]"> — {m.reason}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : null}
    </div>
  );
}

function SurveyBlock({ title, block }: { title: string; block?: Block & { source?: string } }) {
  return (
    <section className="rounded-xl border border-[var(--border)] p-4">
      <h2 className="mb-2 text-base font-semibold">{title}</h2>
      {block?.available ? (
        <>
          <p className="text-sm text-[var(--muted-foreground)]">
            {block.count}건 · 출처 {block.source ?? "-"}
          </p>
          <ul className="mt-2 space-y-1 text-sm">
            {(block.items ?? []).slice(0, 5).map((it, i) => (
              <li key={i} className="truncate">
                {typeof it === "object" && it !== null
                  ? String((it as Record<string, unknown>).name ?? JSON.stringify(it))
                  : String(it)}
              </li>
            ))}
          </ul>
        </>
      ) : (
        // ★"없음"과 "못 봄"을 가르는 문장을 그대로 보여준다.
        <p className="text-sm text-amber-600">{block?.note ?? "미확보"}</p>
      )}
    </section>
  );
}
