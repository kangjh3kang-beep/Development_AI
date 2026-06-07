"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";

type Webhook = {
  id: string;
  url: string;
  events: string[];
  active: boolean;
  last_delivery_status: "success" | "failed" | "pending" | null;
  last_delivered_at: string | null;
  created_at: string;
};

type WebhookListResponse = {
  webhooks: Webhook[];
};

const EVENT_OPTIONS = [
  { value: "project.created", label: "프로젝트 생성" },
  { value: "project.updated", label: "프로젝트 업데이트" },
  { value: "report.generated", label: "보고서 생성" },
  { value: "avm.completed", label: "AVM 감정 완료" },
  { value: "compliance.checked", label: "법규검토 완료" },
  { value: "design.generated", label: "AI 설계 완료" },
  { value: "risk.analyzed", label: "리스크 분석 완료" },
];

const DELIVERY_STATUS_LABELS: Record<string, { label: string; color: string }> = {
  success: { label: "성공", color: "text-emerald-500" },
  failed: { label: "실패", color: "text-red-500" },
  pending: { label: "대기 중", color: "text-amber-500" },
};

// Mock data for when API is not available
const MOCK_WEBHOOKS: Webhook[] = [
  {
    id: "wh-001",
    url: "https://example.com/hooks/propai",
    events: ["project.created", "report.generated"],
    active: true,
    last_delivery_status: "success",
    last_delivered_at: new Date(Date.now() - 3_600_000).toISOString(),
    created_at: new Date(Date.now() - 86_400_000 * 7).toISOString(),
  },
  {
    id: "wh-002",
    url: "https://slack.example.com/incoming/propai",
    events: ["avm.completed", "risk.analyzed"],
    active: false,
    last_delivery_status: "failed",
    last_delivered_at: new Date(Date.now() - 86_400_000 * 2).toISOString(),
    created_at: new Date(Date.now() - 86_400_000 * 14).toISOString(),
  },
];

export function WebhookManagementPanel() {
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newUrl, setNewUrl] = useState("");
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setWebhooks(MOCK_WEBHOOKS);
    setIsLoading(false);
  }, []);

  function toggleEvent(event: string) {
    setSelectedEvents((prev) =>
      prev.includes(event)
        ? prev.filter((e) => e !== event)
        : [...prev, event],
    );
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError("");

    const url = newUrl.trim();
    if (!url) {
      setError("웹훅 URL을 입력해 주세요.");
      return;
    }

    if (!url.startsWith("https://")) {
      setError("보안을 위해 https:// 로 시작하는 URL만 허용됩니다.");
      return;
    }

    try {
      new URL(url);
    } catch {
      setError("유효한 URL 형식이 아닙니다.");
      return;
    }

    if (!selectedEvents.length) {
      setError("최소 하나의 이벤트를 선택해 주세요.");
      return;
    }

    setIsCreating(true);
    await new Promise((r) => setTimeout(r, 200));

    const created: Webhook = {
      id: `wh-${Date.now()}`,
      url,
      events: selectedEvents,
      active: true,
      last_delivery_status: null,
      last_delivered_at: null,
      created_at: new Date().toISOString(),
    };
    setWebhooks((prev) => [...prev, created]);
    setShowCreateForm(false);
    setNewUrl("");
    setSelectedEvents([]);
    setIsCreating(false);
  }

  function toggleActive(webhookId: string) {
    setWebhooks((prev) =>
      prev.map((wh) =>
        wh.id === webhookId ? { ...wh, active: !wh.active } : wh,
      ),
    );
  }

  function handleDelete(webhookId: string) {
    setWebhooks((prev) => prev.filter((wh) => wh.id !== webhookId));
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2].map((n) => (
          <div
            key={n}
            className="h-24 animate-pulse rounded-2xl bg-[var(--surface-soft)]"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header + Create Button */}
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-[var(--text-secondary)]">
          등록된 웹훅: {webhooks.length}개
        </p>
        <Button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="gap-2"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 5v14" />
            <path d="M5 12h14" />
          </svg>
          새 웹훅 추가
        </Button>
      </div>

      {/* Create form */}
      {showCreateForm && (
        <Card className="border-[var(--accent-strong)]/30">
          <CardContent className="p-6">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
              새 웹훅 등록
            </p>
            <form className="mt-4 space-y-4" onSubmit={handleCreate}>
              <Input
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                placeholder="https://example.com/webhook"
              />

              <div className="space-y-2">
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
                  이벤트 선택
                </p>
                <div className="flex flex-wrap gap-2">
                  {EVENT_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => toggleEvent(opt.value)}
                      className={`rounded-xl px-3 py-1.5 text-xs font-medium border transition-all ${
                        selectedEvents.includes(opt.value)
                          ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                          : "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:border-[var(--text-tertiary)]"
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {error && (
                <p className="text-xs text-[var(--spot)]">{error}</p>
              )}

              <div className="flex gap-3">
                <Button type="submit" disabled={isCreating}>
                  {isCreating ? "등록 중..." : "웹훅 등록"}
                </Button>
                <Button
                  type="button"
                  onClick={() => {
                    setShowCreateForm(false);
                    setError("");
                  }}
                  className="bg-[var(--surface-soft)] text-[var(--text-secondary)]"
                >
                  취소
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Webhook list */}
      {webhooks.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-sm text-[var(--text-secondary)]">
              등록된 웹훅이 없습니다. 새 웹훅을 추가해 보세요.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {webhooks.map((wh) => (
            <Card key={wh.id}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1 space-y-2">
                    {/* URL and status */}
                    <div className="flex items-center gap-3">
                      <div
                        className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                          wh.active
                            ? "bg-emerald-500 animate-pulse"
                            : "bg-[var(--text-hint)]"
                        }`}
                      />
                      <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
                        {wh.url}
                      </p>
                    </div>

                    {/* Events */}
                    <div className="flex flex-wrap gap-1.5">
                      {(wh.events ?? []).map((evt) => {
                        const label =
                          EVENT_OPTIONS.find((o) => o.value === evt)?.label ??
                          evt;
                        return (
                          <span
                            key={evt}
                            className="rounded-lg bg-[var(--surface-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]"
                          >
                            {label}
                          </span>
                        );
                      })}
                    </div>

                    {/* Last delivery */}
                    <div className="flex items-center gap-4 text-xs text-[var(--text-hint)]">
                      {wh.last_delivery_status && (
                        <span>
                          마지막 전송:{" "}
                          <span
                            className={
                              DELIVERY_STATUS_LABELS[wh.last_delivery_status]
                                ?.color ?? ""
                            }
                          >
                            {DELIVERY_STATUS_LABELS[wh.last_delivery_status]
                              ?.label ?? wh.last_delivery_status}
                          </span>
                        </span>
                      )}
                      {wh.last_delivered_at && (
                        <span>
                          {new Intl.DateTimeFormat("ko-KR", {
                            dateStyle: "short",
                            timeStyle: "short",
                          }).format(new Date(wh.last_delivered_at))}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      onClick={() => toggleActive(wh.id)}
                      className={`rounded-xl px-3 py-1.5 text-xs font-bold transition-all ${
                        wh.active
                          ? "bg-emerald-500/10 text-emerald-500"
                          : "bg-[var(--surface-soft)] text-[var(--text-hint)]"
                      }`}
                    >
                      {wh.active ? "활성" : "비활성"}
                    </button>
                    <button
                      onClick={() => handleDelete(wh.id)}
                      className="rounded-xl px-3 py-1.5 text-xs font-bold text-red-500 transition-all hover:bg-red-500/10"
                    >
                      삭제
                    </button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
