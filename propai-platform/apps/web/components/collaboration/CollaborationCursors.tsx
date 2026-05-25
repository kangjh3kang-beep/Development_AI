"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import type { CollaborationMember } from "@/mocks/module-data";

type CollaborationCursorsProps = {
  members: CollaborationMember[];
  labels: {
    title: string;
    description: string;
  };
};

export function CollaborationCursors({
  members,
  labels,
}: CollaborationCursorsProps) {
  return (
    <Card className="bg-[var(--surface-strong)]">
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
        <p className="text-sm leading-7 text-[var(--text-secondary)]">
          {labels.description}
        </p>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="relative min-h-[220px] overflow-hidden rounded-[var(--radius-xl)] border border-[var(--line)] bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(248,243,233,0.94))]">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(14,116,144,0.12),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(217,119,6,0.12),transparent_28%)]" />
          {members.map((member) => (
            <div
              key={member.id}
              className="absolute"
              style={{
                left: `${member.x}%`,
                top: `${member.y}%`,
                transform: "translate(-50%, -50%)",
              }}
            >
              <div className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: member.color }}
                />
                <div className="rounded-full bg-white/90 px-3 py-2 shadow-[var(--shadow-md)]">
                  <p className="text-xs font-semibold text-[var(--text-primary)]">
                    {member.name}
                  </p>
                  <p className="text-[11px] text-[var(--text-tertiary)]">
                    {member.role}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
