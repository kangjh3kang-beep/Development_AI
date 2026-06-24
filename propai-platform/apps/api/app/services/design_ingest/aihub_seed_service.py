"""AI Hub(aihub.or.kr) 데이터 자동 다운로드 → design_ingest 시드 인제스트.

사용자 확인: AI Hub는 자동 다운로드 API가 있다(aihubshell CLI가 래핑하는 REST).
  - 데이터셋 정보/파일트리: GET {base}/info/{datasetkey}.do   (헤더 apikey)
  - 파일 다운로드:        GET {base}/down/{datasetkey}.do?fileSn={fileSn}  (헤더 apikey) → tar(또는 파일)
전제(일회성·관리자): ①AI Hub 계정 ②마이페이지 apikey 발급(AIHUB_API_KEY 시크릿) ③해당 데이터셋
  '활용신청 승인'. 이후 본 서비스로 **완전 자동** 다운로드+인제스트(건축 도면 48,033장 등) → Qdrant
  design_drawings(설계생성 콜드스타트 시드).
무목업: apikey 미설정·승인 전·다운로드 실패는 정직 상태 반환(가짜 시드 금지). 도면류만 인제스트.
"""
from __future__ import annotations

import io
import tarfile
from typing import Any

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# 도면 인제스트 대상 확장자(이미지·PDF·CAD). 라벨링 JSON 등 비도면은 제외.
_DRAWING_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".dwg", ".dxf", ".tif", ".tiff")


class AihubSeedService:
    """AI Hub 데이터셋 자동 다운로드 + 도면 인제스트(시드)."""

    @staticmethod
    def _key() -> str:
        return (getattr(settings, "AIHUB_API_KEY", "") or "").strip()

    @staticmethod
    def _base() -> str:
        return (getattr(settings, "AIHUB_BASE_URL", "") or "https://api.aihub.or.kr").rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"apikey": self._key()}

    async def dataset_info(self, dataset_key: str) -> dict[str, Any]:
        """데이터셋 파일트리 조회(fileSn·이름) — 다운로드 전 무엇을 받을지 확인."""
        if not self._key():
            return {"available": False, "reason": "AIHUB_API_KEY 미설정(마이페이지 apikey 발급 필요)"}
        try:
            async with httpx.AsyncClient(timeout=30.0, headers=self._headers()) as c:
                r = await c.get(f"{self._base()}/info/{dataset_key}.do")
                r.raise_for_status()
                text = r.text
            return {"available": True, "dataset_key": dataset_key, "raw": text[:4000]}
        except Exception as e:  # noqa: BLE001
            logger.warning("aihub.info_failed", err=f"{type(e).__name__}: {str(e)[:120]}")
            return {"available": False, "reason": "AI Hub info 호출 실패(승인·키 확인)"}

    async def _download_bytes(self, dataset_key: str, file_sn: str) -> bytes | None:
        """파일(보통 tar) 다운로드 → bytes. 미승인/오류 시 None(정직)."""
        try:
            async with httpx.AsyncClient(timeout=300.0, headers=self._headers()) as c:
                r = await c.get(f"{self._base()}/down/{dataset_key}.do", params={"fileSn": file_sn})
                r.raise_for_status()
                ctype = (r.headers.get("content-type") or "").lower()
                # 다운로드 실패는 보통 JSON/HTML 에러로 온다 → 도면 바이너리만 인정.
                if "json" in ctype or "html" in ctype:
                    logger.warning("aihub.down_not_binary", dataset=dataset_key, file_sn=file_sn, ctype=ctype)
                    return None
                return r.content
        except Exception as e:  # noqa: BLE001
            logger.warning("aihub.down_failed", err=f"{type(e).__name__}: {str(e)[:120]}")
            return None

    async def ingest_dataset(
        self, dataset_key: str, file_sn: str, *,
        max_files: int = 100, tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """데이터셋 파일(tar) 다운로드 → 도면 추출 → design_ingest 인제스트(최대 max_files).

        무목업: apikey/승인/다운로드 실패는 정직 상태. 도면 확장자만 인제스트(라벨 JSON 제외).
        """
        if not self._key():
            return {"available": False, "reason": "AIHUB_API_KEY 미설정 — 마이페이지 apikey 발급 후 관리자 시크릿 입력 필요",
                    "ingested": 0}
        blob = await self._download_bytes(dataset_key, file_sn)
        if not blob:
            return {"available": False,
                    "reason": "다운로드 실패 — 데이터셋 '활용신청 승인' 여부·apikey·fileSn 확인",
                    "ingested": 0}

        from app.services.design_ingest.ingest_service import ingest_design_file

        ingested, skipped, failed = 0, 0, 0
        results: list[dict[str, Any]] = []
        # tar면 내부 도면을 순회, 아니면 단일 파일로 취급.
        try:
            tf = tarfile.open(fileobj=io.BytesIO(blob), mode="r:*")
            members = [m for m in tf.getmembers() if m.isfile() and m.name.lower().endswith(_DRAWING_EXT)]
            for m in members:
                if ingested >= max_files:
                    break
                fobj = tf.extractfile(m)
                if fobj is None:
                    continue
                content = fobj.read()
                try:
                    res = await ingest_design_file(filename=m.name.split("/")[-1], content=content,
                                                   tenant_id=tenant_id)
                    if res.get("indexed"):
                        ingested += 1
                    else:
                        skipped += 1
                    results.append({"file": m.name.split("/")[-1], "indexed": res.get("indexed"),
                                    "type": res.get("drawing_type")})
                except Exception:  # noqa: BLE001
                    failed += 1
            tf.close()
            total_drawings = len(members)
        except tarfile.TarError:
            # tar 아님 = 단일 도면 파일. 확장자 무관하게 1건 인제스트 시도.
            try:
                res = await ingest_design_file(filename=f"aihub_{dataset_key}_{file_sn}", content=blob,
                                               tenant_id=tenant_id)
                ingested = 1 if res.get("indexed") else 0
                skipped = 0 if res.get("indexed") else 1
                results.append({"file": f"{dataset_key}/{file_sn}", "indexed": res.get("indexed")})
                total_drawings = 1
            except Exception:  # noqa: BLE001
                return {"available": True, "ingested": 0, "reason": "단일 파일 인제스트 실패"}

        return {
            "available": True, "dataset_key": dataset_key, "file_sn": file_sn,
            "total_drawings": total_drawings, "ingested": ingested, "skipped": skipped, "failed": failed,
            "samples": results[:10],
            "note": "AI Hub 도면 → design_drawings(Qdrant) 시드 인제스트. 승인된 데이터셋만(무목업).",
        }
