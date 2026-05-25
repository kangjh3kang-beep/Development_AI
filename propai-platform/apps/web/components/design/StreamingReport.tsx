"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import { StreamingText } from "@/components/ui/StreamingText";
import type { ReportSection } from "@/mocks/module-data";

type StreamingReportProps = {
  sections: ReportSection[];
  labels: {
    title: string;
    description: string;
  };
};

export function StreamingReport({
  sections,
  labels,
}: StreamingReportProps) {
  return (
    <Card className="bg-[var(--surface-strong)]">
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
        <p className="text-sm leading-7 text-[var(--text-secondary)]">
          {labels.description}
        </p>
      </CardHeader>
      <CardContent className="grid gap-4 pt-0">
        {sections.map((section, index) => (
          <div
            key={section.id}
            className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-5 py-4"
          >
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {section.title}
            </p>
            <StreamingText
              key={`${section.id}-${section.content}`}
              stepMs={14 + index * 4}
              text={section.content}
              className="mt-3 text-sm leading-7 text-[var(--text-secondary)]"
            />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
