"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, AlertTriangle, MapPinOff } from "lucide-react";
import { loadKakaoMap } from "@/lib/kakao-map";

interface KakaoRoadviewProps {
  lat: number;
  lon: number;
  /** 컨테이너 높이 (기본값: 250px) */
  height?: number | string;
}

export function KakaoRoadview({ lat, lon, height = 250 }: KakaoRoadviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [noData, setNoData] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;
    
    setLoading(true);
    setError(null);
    setNoData(false);

    let cancelled = false;

    loadKakaoMap()
      .then(() => {
        if (cancelled) return;
        
        // Kakao SDK 로드 성공. (window.kakao 객체 보장됨)
        const kakao = (window as any).kakao;
        if (!kakao?.maps?.Roadview || !kakao?.maps?.RoadviewClient) {
          throw new Error("로드뷰 모듈을 불러올 수 없습니다.");
        }

        const position = new kakao.maps.LatLng(lat, lon);
        const roadviewClient = new kakao.maps.RoadviewClient();
        
        // 50m 반경 내 가장 가까운 로드뷰 촬영 위치 탐색
        roadviewClient.getNearestPanoId(position, 50, (panoId: number | null) => {
          if (cancelled) return;
          
          if (panoId !== null) {
            // 로드뷰 존재 시 컨테이너에 초기화
            const roadview = new kakao.maps.Roadview(containerRef.current!);
            roadview.setPanoId(panoId, position);
            setLoading(false);
          } else {
            // 해당 위치(산간, 사유지, 미촬영지 등) 주변에 로드뷰가 없는 경우
            setNoData(true);
            setLoading(false);
          }
        });
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("로드뷰 초기화 실패:", err);
          setError(err.message || "카카오맵 SDK를 불러오지 못했습니다.");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [lat, lon]);

  return (
    <div
      className="relative w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-100"
      style={{ height }}
    >
      {loading && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-100/80 backdrop-blur-sm">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          <p className="mt-2 text-xs font-medium text-slate-500">로드뷰 불러오는 중...</p>
        </div>
      )}

      {error && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-50 p-4 text-center">
          <AlertTriangle className="mb-2 h-6 w-6 text-red-500" />
          <p className="text-sm font-bold text-red-600">로드뷰 연동 오류</p>
          <p className="mt-1 text-xs text-slate-600">{error}</p>
        </div>
      )}

      {noData && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-50 p-4 text-center">
          <MapPinOff className="mb-2 h-6 w-6 text-slate-400" />
          <p className="text-sm font-bold text-slate-700">제공되지 않는 지역입니다</p>
          <p className="mt-1 text-xs text-slate-500">
            주변 50m 이내에 카카오 로드뷰 촬영 데이터가 없습니다. (산간, 오지, 사유지 등)
          </p>
        </div>
      )}

      {/* 로드뷰 렌더링 컨테이너 */}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}
