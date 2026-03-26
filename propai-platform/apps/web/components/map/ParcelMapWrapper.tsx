"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@propai/ui";
import type { ParcelStatus, ParcelShape } from "@/mocks/module-data";

type ParcelMapWrapperProps = {
  parcels: ParcelShape[];
  labels: {
    title: string;
    description: string;
    legendTitle: string;
    parcelInfoTitle: string;
    areaLabel: string;
    ownerLabel: string;
    statusLabel: string;
    statusLabels: Record<ParcelStatus, string>;
  };
};

const CadastralMap = dynamic<ParcelMapWrapperProps>(
  () => import("./CadastralMap").then((module) => module.CadastralMap),
  {
    ssr: false,
    loading: () => <Skeleton className="h-[500px] w-full rounded-xl" />,
  },
);

export default function ParcelMapWrapper(props: ParcelMapWrapperProps) {
  return <CadastralMap {...props} />;
}
