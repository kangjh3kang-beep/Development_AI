"use client";

import { useParams } from "next/navigation";
import { AuctionWorkspace } from "@/components/auction/AuctionWorkspace";
import { isValidLocale, type Locale } from "@/i18n/config";

export default function AuctionPage() {
  const { locale } = useParams() as { locale: string };
  const safeLocale: Locale = isValidLocale(locale) ? locale : "ko";

  return <AuctionWorkspace locale={safeLocale} />;
}
