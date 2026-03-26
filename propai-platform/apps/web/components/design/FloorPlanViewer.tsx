import { Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import type { FloorPlanDraft } from "@/mocks/module-data";

type FloorPlanViewerProps = {
  plan: FloorPlanDraft;
  labels: {
    title: string;
    areaLabel: string;
    roomsLabel: string;
    statusTitle: string;
    statusValue: string;
  };
};

export function FloorPlanViewer({ plan, labels }: FloorPlanViewerProps) {
  return (
    <Card className="bg-[var(--surface-strong)]">
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-5 pt-0">
        <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-[1.75rem] border border-[var(--line)] bg-[linear-gradient(180deg,rgba(19,33,47,0.05),rgba(14,116,144,0.08))] p-5">
            <div className="grid min-h-[300px] grid-cols-3 gap-3 rounded-[1.5rem] border border-white/80 bg-white/78 p-3">
              {plan.rooms.map((room, index) => (
                <div
                  key={room}
                  className={`rounded-[1.25rem] border border-[var(--line)] px-4 py-4 text-sm font-medium text-[rgba(19,33,47,0.76)] ${
                    index === 0
                      ? "col-span-2 bg-[rgba(14,116,144,0.12)]"
                      : index === plan.rooms.length - 1
                        ? "col-span-2 bg-[rgba(217,119,6,0.12)]"
                        : "bg-[rgba(19,33,47,0.04)]"
                  }`}
                >
                  {room}
                </div>
              ))}
            </div>
          </div>
          <div className="grid gap-3">
            <div className="rounded-[1.25rem] border border-[var(--line)] bg-white/80 px-4 py-4">
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
                {labels.statusTitle}
              </p>
              <p className="mt-3 text-sm font-semibold text-[var(--foreground)]">
                {labels.statusValue}
              </p>
            </div>
            <div className="rounded-[1.25rem] border border-[var(--line)] bg-white/80 px-4 py-4">
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
                {labels.areaLabel}
              </p>
              <p className="mt-3 text-sm font-semibold text-[rgba(19,33,47,0.78)]">
                {plan.areaLabel}
              </p>
            </div>
            <div className="rounded-[1.25rem] border border-[var(--line)] bg-white/80 px-4 py-4">
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
                {labels.roomsLabel}
              </p>
              <ul className="mt-3 grid gap-2">
                {plan.rooms.map((room) => (
                  <li
                    key={room}
                    className="rounded-full bg-[rgba(19,33,47,0.05)] px-3 py-2 text-sm text-[rgba(19,33,47,0.74)]"
                  >
                    {room}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
        <div className="rounded-[1.5rem] border border-[var(--line)] bg-white/80 px-5 py-4">
          <p className="text-sm font-semibold text-[var(--foreground)]">
            {plan.name}
          </p>
          <p className="text-sm leading-7 text-[rgba(19,33,47,0.76)]">
            {plan.summary}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
