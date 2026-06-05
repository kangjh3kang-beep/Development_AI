"use client";

import { useParams } from "next/navigation";
import { DesignStudio } from "@/components/design/DesignStudio";

export default function DesignPage() {
  const params = useParams();
  const projectId = (params?.id as string) || "";
  return (
    <div className="p-6">
      <DesignStudio projectId={projectId} />
    </div>
  );
}
