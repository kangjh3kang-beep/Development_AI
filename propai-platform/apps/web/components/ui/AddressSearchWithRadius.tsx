"use client";

import { useState, useCallback } from "react";
import { Button, Card, CardContent, Input, Select } from "@propai/ui";

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

export interface AddressSearchResult {
  address: string;
  lawdCd: string;
  radius: number;
  period: "3m" | "6m" | "1y";
}

interface AddressSearchWithRadiusProps {
  onSearch: (result: AddressSearchResult) => void;
  isLoading?: boolean;
  placeholder?: string;
}

/* ------------------------------------------------------------------ */
/*  District mapping (법정동 코드)                                      */
/* ------------------------------------------------------------------ */

const DISTRICT_MAP: Record<string, string> = {
  강남: "11680",
  서초: "11650",
  송파: "11710",
  강동: "11740",
  마포: "11440",
  용산: "11170",
  성동: "11200",
  광진: "11215",
  동대문: "11230",
  중랑: "11260",
  성북: "11290",
  강북: "11305",
  도봉: "11320",
  노원: "11350",
  은평: "11380",
  서대문: "11410",
  종로: "11110",
  중구: "11140",
  동작: "11590",
  관악: "11620",
  영등포: "11560",
  금천: "11545",
  구로: "11530",
  양천: "11500",
  강서: "11500",
  의정부: "41150",
  수원: "41110",
  성남: "41130",
  고양: "41280",
  부산: "26000",
  대구: "27000",
  인천: "28000",
};

function extractLawdCd(address: string): string {
  for (const [district, code] of Object.entries(DISTRICT_MAP)) {
    if (address.includes(district)) {
      return code;
    }
  }
  return "11680"; // 기본값: 강남구
}

/* ------------------------------------------------------------------ */
/*  Radius / Period options                                           */
/* ------------------------------------------------------------------ */

const RADIUS_OPTIONS = [
  { value: "500", label: "반경 500m" },
  { value: "1000", label: "반경 1km" },
  { value: "3000", label: "반경 3km" },
  { value: "5000", label: "반경 5km" },
] as const;

const PERIOD_OPTIONS = [
  { value: "3m", label: "최근 3개월" },
  { value: "6m", label: "최근 6개월" },
  { value: "1y", label: "최근 1년" },
] as const;

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function AddressSearchWithRadius({
  onSearch,
  isLoading = false,
  placeholder = "주소를 입력하세요 (예: 서울특별시 강남구 삼성동)",
}: AddressSearchWithRadiusProps) {
  const [address, setAddress] = useState("");
  const [radius, setRadius] = useState("1000");
  const [period, setPeriod] = useState<"3m" | "6m" | "1y">("6m");

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = address.trim();
      if (!trimmed) return;

      onSearch({
        address: trimmed,
        lawdCd: extractLawdCd(trimmed),
        radius: Number(radius),
        period,
      });
    },
    [address, radius, period, onSearch],
  );

  return (
    <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
      <CardContent className="p-6">
        <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
          검색 조건
        </p>
        <form onSubmit={handleSubmit} className="grid gap-4">
          {/* 주소 입력 */}
          <Input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder={placeholder}
            className="w-full"
          />

          {/* 필터 행 */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {/* 반경 선택 */}
            <div>
              <label className="mb-1 block text-xs text-[var(--text-secondary)]">
                검색 반경
              </label>
              <Select
                value={radius}
                onChange={(e) => setRadius(e.target.value)}
              >
                {RADIUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Select>
            </div>

            {/* 기간 선택 */}
            <div>
              <label className="mb-1 block text-xs text-[var(--text-secondary)]">
                조회 기간
              </label>
              <Select
                value={period}
                onChange={(e) =>
                  setPeriod(e.target.value as "3m" | "6m" | "1y")
                }
              >
                {PERIOD_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Select>
            </div>

            {/* 검색 버튼 */}
            <div className="flex items-end">
              <Button
                type="submit"
                disabled={isLoading || !address.trim()}
                className="w-full"
              >
                {isLoading ? "분석 중..." : "검색"}
              </Button>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
