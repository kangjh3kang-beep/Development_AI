"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiClientError, apiClient, apiV1BaseUrl } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";
import {
  ENTRY_TYPE_LABELS,
  MyPageShell,
  ORDER_STATUS_LABELS,
  formatKrw,
} from "./MyPageShell";

type Package = { key: string; amount_krw: number; label: string };
type PackagesResponse = {
  packages: Package[];
  custom: { min_krw: number; max_krw: number; unit_krw: number };
};

type Order = {
  id: string;
  order_no: string;
  amount_krw: number;
  coin_krw: number;
  status: string;
  provider: string | null;
  created_at: string | null;
  paid_at: string | null;
};

type LedgerItem = {
  created_at: string | null;
  entry_type: string;
  amount_krw: number;
  description: string | null;
  ref_type: string | null;
  ref_id: string | null;
};

type VerifyResult = { ok: boolean | null; count?: number; broken_at?: number };

const LEDGER_FILTERS: Array<{ key: string | null; label: string }> = [
  { key: null, label: "전체" },
  // '충전' = 신규 주문 지급(order_paid) + 레거시 직접충전(topup) 그룹(백엔드 FILTER_GROUPS).
  { key: "charge", label: "충전" },
  { key: "llm_usage", label: "AI 사용" },
  { key: "service_fee", label: "서비스료" },
  { key: "monthly_grant", label: "월기본" },
];

function resolveErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiClientError) {
    const payload = error.payload as { detail?: unknown } | null;
    if (payload && typeof payload.detail === "string") return payload.detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function CoinsClient({ locale }: { locale: Locale }) {
  const [packages, setPackages] = useState<PackagesResponse | null>(null);
  // ★결제 경로(simulated=데모 self-confirm 가능 / manual_only=관리자 확정만). 프로덕션에서
  //   100% 실패하는 '결제 완료 처리' 버튼을 감추기 위한 게이트(성장루프 MEDIUM 수렴).
  const [paymentMode, setPaymentMode] = useState<string>("manual_only");
  const [selected, setSelected] = useState<string>("starter");
  const [customAmount, setCustomAmount] = useState<string>("");
  const [orders, setOrders] = useState<Order[]>([]);
  const [ledger, setLedger] = useState<LedgerItem[]>([]);
  const [filter, setFilter] = useState<string | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [notice, setNotice] = useState<{ kind: "info" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  // ★조회 로딩·실패를 '내역 없음'으로 위장하지 않도록 명시 상태(성장루프 MEDIUM 수렴).
  const [loading, setLoading] = useState(true);
  const [ordersError, setOrdersError] = useState(false);
  const [ledgerError, setLedgerError] = useState(false);
  const [packagesError, setPackagesError] = useState(false);
  // ★요청 세대 카운터 — 필터 연속 전환 시 늦게 도착한 이전 요청 응답이 최신을 덮어쓰는 경합을
  //   차단한다(성장루프 LOW 수렴, Overview/Usage의 active 가드와 동일 취지).
  const reqSeqRef = useRef(0);

  const reload = useCallback(async () => {
    const myReq = ++reqSeqRef.current;
    // ★필터 전환 등 재조회 시 로딩 신호를 켜 이전 필터 항목이 새 필터 라벨 아래 사실처럼
    //   노출되는 stale 창을 제거한다(성장루프 LOW 수렴, UsageClient.changeDays와 정합).
    setLoading(true);
    const [o, l] = await Promise.allSettled([
      apiClient.get<{ orders: Order[] }>("/billing/orders?limit=20", { useMock: false }),
      apiClient.get<{ items: LedgerItem[] }>(
        `/billing/ledger?limit=50${filter ? `&entry_type=${filter}` : ""}`,
        { useMock: false },
      ),
    ]);
    // 뒤처진 응답(이후 더 새 요청이 발사됨) 또는 언마운트 후 도착분은 폐기.
    if (myReq !== reqSeqRef.current) return;
    if (o.status === "fulfilled") {
      setOrders(o.value.orders ?? []);
      setOrdersError(false);
    } else {
      setOrdersError(true);
    }
    if (l.status === "fulfilled") {
      setLedger(l.value.items ?? []);
      setLedgerError(false);
    } else {
      setLedgerError(true);
    }
    setLoading(false);
  }, [filter]);

  useEffect(() => {
    // 언마운트 시 세대 무효화 — 도착하는 응답을 폐기한다.
    return () => {
      reqSeqRef.current += 1;
    };
  }, []);

  useEffect(() => {
    void apiClient
      .get<PackagesResponse & { payment_mode?: string }>("/billing/packages", { useMock: false })
      .then((p) => {
        setPackages(p);
        if (p?.payment_mode) setPaymentMode(p.payment_mode);
        setPackagesError(false);
      })
      .catch(() => setPackagesError(true));
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const createOrder = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const body: { package_key: string; amount_krw?: number } = { package_key: selected };
      if (selected === "custom") body.amount_krw = Number(customAmount || 0);
      const order = await apiClient.post<Order & { payment_mode?: string }>(
        "/billing/orders",
        { body, useMock: false },
      );
      // ★안내문과 '결제 완료 처리' 버튼 게이트를 동일 출처(주문 응답 payment_mode)로 통일 —
      //   packages 조회가 실패해도 안내와 버튼 노출이 어긋나지 않게 한다(성장루프 LOW 수렴).
      if (order.payment_mode) setPaymentMode(order.payment_mode);
      setNotice({
        kind: "info",
        text:
          order.payment_mode === "simulated"
            ? `주문 ${order.order_no}이 생성되었습니다. 아래 결제내역에서 '결제 완료 처리'를 눌러 충전을 완료하세요(데모 환경).`
            : `주문 ${order.order_no}이 생성되었습니다. 온라인 결제 연동 준비 중이므로, 계좌이체 후 관리자 확인(k3880@kakao.com)으로 충전됩니다.`,
      });
      await reload();
    } catch (error) {
      setNotice({ kind: "error", text: resolveErrorMessage(error, "주문 생성에 실패했습니다.") });
    } finally {
      setBusy(false);
    }
  };

  const confirmOrder = async (id: string) => {
    setBusy(true);
    setNotice(null);
    try {
      await apiClient.post(`/billing/orders/${id}/confirm`, { useMock: false });
      setNotice({ kind: "info", text: "충전이 완료되었습니다." });
      await reload();
    } catch (error) {
      setNotice({
        kind: "error",
        text: resolveErrorMessage(error, "결제 확정에 실패했습니다."),
      });
    } finally {
      setBusy(false);
    }
  };

  const cancelOrder = async (id: string) => {
    setBusy(true);
    setNotice(null);
    try {
      await apiClient.post(`/billing/orders/${id}/cancel`, { useMock: false });
      await reload();
    } catch (error) {
      setNotice({ kind: "error", text: resolveErrorMessage(error, "주문 취소에 실패했습니다.") });
    } finally {
      setBusy(false);
    }
  };

  const runVerify = async () => {
    try {
      setVerify(await apiClient.get<VerifyResult>("/billing/ledger/verify", { useMock: false }));
    } catch {
      setVerify({ ok: null });
    }
  };

  const downloadCsv = async () => {
    try {
      // CSV는 파일 다운로드라 apiClient(JSON 전용) 대신 직접 fetch한다. 다만 raw fetch는
      // apiClient의 401→refresh를 못 타므로(성장루프 LOW 수렴), 먼저 apiClient로 가벼운
      // 조회를 1회 태워 토큰을 필요 시 자동 갱신한 뒤 최신 토큰으로 내려받는다.
      await apiClient.get("/billing/ledger?limit=1", { useMock: false });
      const token =
        typeof window !== "undefined" ? window.localStorage.getItem("propai_access_token") : null;
      const res = await fetch(`${apiV1BaseUrl()}/billing/ledger/export?days=365`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (res.status === 401) {
        throw new Error("세션이 만료되었습니다. 새로고침 후 다시 시도해 주세요.");
      }
      if (!res.ok) throw new Error("다운로드에 실패했습니다.");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "코인내역.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      // ★즉시 revoke하면 Safari/일부 Firefox가 blob을 읽기 전이라 다운로드가 취소될 수 있어
      //   다음 tick으로 지연 해제한다(MDN 권고, 성장루프 LOW 수렴).
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setNotice({ kind: "error", text: resolveErrorMessage(error, "CSV 다운로드에 실패했습니다.") });
    }
  };

  return (
    <MyPageShell
      locale={locale}
      title="코인 충전·결제내역"
      description="코인을 충전하고, 충전·사용·결제 기록을 확인합니다. 결제 기록은 전자상거래법에 따라 5년간 보존됩니다."
    >
      {notice ? (
        <div
          role="status"
          className={`mb-5 rounded-[var(--radius-xl)] border px-5 py-3.5 text-sm ${
            notice.kind === "error"
              ? "border-[rgba(217,119,6,0.35)] bg-[rgba(217,119,6,0.12)] text-[rgb(146,64,14)]"
              : "border-[rgba(13,148,136,0.28)] bg-[rgba(13,148,136,0.12)] text-[rgb(15,118,110)]"
          }`}
        >
          {notice.text}
        </div>
      ) : null}

      {/* 충전 — 패키지 선택(금액은 서버 결정) */}
      <section className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
        <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">코인 충전</h2>
        {packagesError ? (
          <p role="status" className="mt-3 text-sm text-[rgb(146,64,14)]">
            충전 상품을 불러오지 못했습니다. 잠시 후 새로고침해 주세요.
          </p>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-2">
          {(packages?.packages ?? []).map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => setSelected(p.key)}
              aria-pressed={selected === p.key}
              className={`rounded-[var(--radius-lg)] border px-4 py-2.5 text-sm font-semibold transition ${
                selected === p.key
                  ? "border-[var(--accent-strong)] bg-[rgba(14,116,144,0.08)] text-[var(--accent-strong)]"
                  : "border-[var(--line)] text-[var(--text-primary)] hover:bg-[var(--surface)]"
              }`}
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setSelected("custom")}
            aria-pressed={selected === "custom"}
            className={`rounded-[var(--radius-lg)] border px-4 py-2.5 text-sm font-semibold transition ${
              selected === "custom"
                ? "border-[var(--accent-strong)] bg-[rgba(14,116,144,0.08)] text-[var(--accent-strong)]"
                : "border-[var(--line)] text-[var(--text-primary)] hover:bg-[var(--surface)]"
            }`}
          >
            직접 입력
          </button>
        </div>
        {selected === "custom" ? (
          <div className="mt-3">
            <label htmlFor="custom-amount" className="text-xs text-[var(--text-tertiary)]">
              충전 금액(원) — {formatKrw(packages?.custom.min_krw ?? 1000)}~
              {formatKrw(packages?.custom.max_krw ?? 1000000)}, {packages?.custom.unit_krw ?? 100}원 단위
            </label>
            <input
              id="custom-amount"
              type="number"
              inputMode="numeric"
              min={packages?.custom.min_krw ?? 1000}
              max={packages?.custom.max_krw ?? 1000000}
              step={packages?.custom.unit_krw ?? 100}
              value={customAmount}
              onChange={(e) => setCustomAmount(e.target.value)}
              className="mt-1 block w-56 rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface)] px-3.5 py-2.5 text-sm text-[var(--text-primary)]"
            />
          </div>
        ) : null}
        <button
          type="button"
          disabled={busy}
          onClick={() => void createOrder()}
          className="mt-4 rounded-full bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
        >
          충전 주문 만들기
        </button>
        <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
          충전 코인은 1원 = 1코인으로 지급되며 월기본 소진 후 사용됩니다. 주문 생성 후 결제가
          확인되면 잔액에 반영됩니다.
        </p>
      </section>

      {/* 결제내역(주문) */}
      <section className="mt-4 rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
        <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">결제내역</h2>
        {ordersError ? (
          <p role="status" className="mt-3 text-sm text-[rgb(146,64,14)]">
            결제내역을 불러오지 못했습니다. 잠시 후 새로고침해 주세요.
          </p>
        ) : loading ? (
          <p className="mt-3 text-sm text-[var(--text-tertiary)]">불러오는 중…</p>
        ) : orders.length === 0 ? (
          <p className="mt-3 text-sm text-[var(--text-tertiary)]">결제(주문) 내역이 없습니다.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="border-b border-[var(--line)] text-left text-xs text-[var(--text-tertiary)]">
                  <th className="py-2 pr-3 font-medium">주문번호</th>
                  <th className="py-2 pr-3 font-medium">금액</th>
                  <th className="py-2 pr-3 font-medium">상태</th>
                  <th className="py-2 pr-3 font-medium">일시</th>
                  <th className="py-2 font-medium">처리</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--line)]">
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td className="py-2.5 pr-3 font-mono text-xs text-[var(--text-primary)]">{o.order_no}</td>
                    <td className="py-2.5 pr-3 font-semibold text-[var(--text-primary)]">
                      {formatKrw(o.amount_krw)}
                    </td>
                    <td className="py-2.5 pr-3">
                      <span
                        className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                          o.status === "paid"
                            ? "bg-[rgba(13,148,136,0.12)] text-[rgb(15,118,110)]"
                            : o.status === "pending"
                              ? "bg-[rgba(217,119,6,0.12)] text-[rgb(146,64,14)]"
                              : "bg-[var(--surface)] text-[var(--text-tertiary)]"
                        }`}
                      >
                        {ORDER_STATUS_LABELS[o.status] ?? o.status}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 text-xs text-[var(--text-tertiary)]">
                      {o.created_at ? new Date(o.created_at).toLocaleString("ko-KR") : "-"}
                    </td>
                    <td className="py-2.5">
                      {o.status === "pending" ? (
                        <span className="flex gap-2">
                          {/* '결제 완료 처리'(self-confirm)는 시뮬레이션 모드에서만 노출 —
                              프로덕션(manual_only)에선 항상 501이라 죽은 버튼이 되므로 감춘다. */}
                          {paymentMode === "simulated" ? (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void confirmOrder(o.id)}
                              className="rounded-full border border-[var(--accent-strong)] px-3 py-1 text-xs font-semibold text-[var(--accent-strong)] transition hover:bg-[rgba(14,116,144,0.08)] disabled:opacity-50"
                            >
                              (데모) 결제 완료 처리
                            </button>
                          ) : null}
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void cancelOrder(o.id)}
                            className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-semibold text-[var(--text-tertiary)] transition hover:bg-[var(--surface)] disabled:opacity-50"
                          >
                            취소
                          </button>
                        </span>
                      ) : (
                        <span className="text-xs text-[var(--text-tertiary)]">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 코인내역(통합 타임라인) */}
      <section className="mt-4 rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">코인내역</h2>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void runVerify()}
              className="rounded-full border border-[var(--line)] px-3.5 py-1.5 text-xs font-semibold text-[var(--text-primary)] transition hover:bg-[var(--surface)]"
            >
              내역 무결성 확인
            </button>
            <button
              type="button"
              onClick={() => void downloadCsv()}
              className="rounded-full border border-[var(--line)] px-3.5 py-1.5 text-xs font-semibold text-[var(--text-primary)] transition hover:bg-[var(--surface)]"
            >
              CSV 다운로드
            </button>
          </div>
        </div>
        {verify ? (
          <p
            role="status"
            className={`mt-2 text-xs font-semibold ${
              verify.ok === true
                ? "text-[rgb(15,118,110)]"
                : verify.ok === false
                  ? "text-[rgb(146,64,14)]"
                  : "text-[var(--text-tertiary)]"
            }`}
          >
            {verify.ok === true
              ? `위·변조 없음 확인(기록 ${verify.count ?? 0}건, 해시체인 재계산 일치)`
              : verify.ok === false
                ? `무결성 이상 감지(${verify.broken_at ?? "?"}번째 기록) — 고객센터에 문의해 주세요.`
                : "지금은 확인할 수 없습니다. 잠시 후 다시 시도해 주세요."}
          </p>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-1.5">
          {LEDGER_FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              onClick={() => setFilter(f.key)}
              aria-pressed={filter === f.key}
              className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                filter === f.key
                  ? "bg-[var(--accent-strong)] text-white"
                  : "border border-[var(--line)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        {ledgerError ? (
          <p role="status" className="mt-3 text-sm text-[rgb(146,64,14)]">
            코인내역을 불러오지 못했습니다. 잠시 후 새로고침해 주세요.
          </p>
        ) : loading ? (
          <p className="mt-3 text-sm text-[var(--text-tertiary)]">불러오는 중…</p>
        ) : ledger.length === 0 ? (
          <p className="mt-3 text-sm text-[var(--text-tertiary)]">코인내역이 없습니다.</p>
        ) : (
          <ul className="mt-3 divide-y divide-[var(--line)]">
            {ledger.map((item, i) => (
              <li key={`${item.created_at}-${i}`} className="flex items-center justify-between py-2.5 text-sm">
                <div>
                  <p className="font-medium text-[var(--text-primary)]">
                    {ENTRY_TYPE_LABELS[item.entry_type] ?? item.entry_type}
                  </p>
                  <p className="text-xs text-[var(--text-tertiary)]">
                    {item.description ?? ""}{" "}
                    {item.created_at ? new Date(item.created_at).toLocaleString("ko-KR") : ""}
                  </p>
                </div>
                <span
                  className={`font-semibold ${
                    item.amount_krw >= 0 ? "text-emerald-600" : "text-[var(--text-primary)]"
                  }`}
                >
                  {item.amount_krw >= 0 ? "+" : ""}
                  {formatKrw(item.amount_krw)}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs leading-5 text-[var(--text-tertiary)]">
          산출근거: 코인내역은 충전·지급·서비스료(거래 원장)와 AI 분석 사용(실계측 로그)을 합친
          기록입니다. &lsquo;내역 무결성 확인&rsquo;은 원장의 해시체인을 재계산해 위·변조 여부를
          검증합니다.
        </p>
      </section>
    </MyPageShell>
  );
}
