"""AI Hub(aihub.or.kr) 자동 다운로드(aihubshell CLI) → design_ingest 시드 인제스트.

★실제 메커니즘(사용자 제공 공식 문서): aihubshell CLI를 쓴다.
  - CLI 받기: curl -o aihubshell https://api.aihub.or.kr/api/aihubshell.do  (+chmod +x)
  - 목록:   aihubshell -mode l [-datasetkey {k}]            → 데이터셋/파일트리(파일명|용량|filekey)
  - 다운로드: aihubshell -mode d -datasetkey {k} [-filekey {a,b}] -aihubapikey '{key}'
            → zip parts 자동 병합·압축해제·아카이브 제거(다운 위치=실행 CWD). 미지정 filekey=전체.
전제(일회성·관리자): apikey 발급(AIHUB_API_KEY 시크릿) + 데이터셋 '활용신청 승인'(완료).
디스크 안전: 전체(TB) 대신 '특정 filekey 1~수개'만 임시폴더에 받아 도면 인제스트 후 정리(bounded).
무목업: 키미설정·미승인·실패는 정직 상태(가짜 시드 금지).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_SHELL_URL = "https://api.aihub.or.kr/api/aihubshell.do"
_DRAWING_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".dwg", ".dxf", ".tif", ".tiff")


class AihubSeedService:
    """AI Hub aihubshell CLI 자동 다운로드 + 도면 시드 인제스트."""

    @staticmethod
    def _key() -> str:
        # 관리자 시크릿(secret_store)은 런타임 os.environ 반영 → os.getenv 우선.
        from app.core.config import settings
        return (os.getenv("AIHUB_API_KEY") or getattr(settings, "AIHUB_API_KEY", "") or "").strip()

    async def _ensure_shell(self, workdir: Path) -> Path | None:
        """aihubshell CLI를 workdir에 받고 실행권한 부여. 실패 시 None."""
        shell = workdir / "aihubshell"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as c:
                r = await c.get(_SHELL_URL)
                r.raise_for_status()
                shell.write_bytes(r.content)
            shell.chmod(0o755)
            return shell
        except Exception as e:  # noqa: BLE001
            logger.warning("aihub.shell_fetch_failed", err=f"{type(e).__name__}: {str(e)[:120]}")
            return None

    async def _run(self, shell: Path, args: list[str], cwd: Path, timeout: int = 1800) -> tuple[int, str]:
        """aihubshell 실행(apikey 주입). (returncode, 출력)."""
        key = self._key()
        cmd = ["bash", str(shell), *args, "-aihubapikey", key]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode or 0, (out or b"").decode("utf-8", "replace")
        except asyncio.TimeoutError:
            return 124, "시간초과(다운로드 지연 — 더 작은 filekey로 분할 권장)"
        except Exception as e:  # noqa: BLE001
            return 1, f"{type(e).__name__}: {str(e)[:160]}"

    async def list_datasets(self, dataset_key: str | None = None) -> dict[str, Any]:
        """데이터셋/파일트리 목록(aihubshell -mode l). datasetkey 주면 파일트리(filekey 확인)."""
        if not self._key():
            return {"available": False, "reason": "AIHUB_API_KEY 미설정"}
        tmp = Path(tempfile.mkdtemp(prefix="aihub_"))
        try:
            shell = await self._ensure_shell(tmp)
            if not shell:
                return {"available": False, "reason": "aihubshell CLI 다운로드 실패"}
            args = ["-mode", "l"] + (["-datasetkey", str(dataset_key)] if dataset_key else [])
            rc, out = await self._run(shell, args, tmp, timeout=120)
            # 건축/도면/설계 관련 라인은 항상 추려 반환(전체 목록은 길어 절단될 수 있어 키워드 우선 노출).
            kw = [ln.strip() for ln in out.splitlines()
                  if any(k in ln for k in ("건축", "도면", "설계", "평면", "단면", "입면"))]
            return {"available": rc == 0, "dataset_key": dataset_key, "rc": rc,
                    "matched": kw[:40], "output": out[:60000]}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    async def ingest_dataset(
        self, dataset_key: str, file_key: str | None = None, *,
        max_files: int = 100, tenant_id: str | None = None, timeout: int = 1800,
    ) -> dict[str, Any]:
        """특정 filekey 다운로드(aihubshell -mode d) → 압축해제 도면 → design_ingest 인제스트.

        디스크 안전: file_key는 ★권장(미지정 시 전체=TB). 임시폴더 작업 후 정리.
        """
        if not self._key():
            return {"available": False, "reason": "AIHUB_API_KEY 미설정 — 관리자 시크릿 입력 필요", "ingested": 0}
        tmp = Path(tempfile.mkdtemp(prefix="aihub_dl_"))
        try:
            shell = await self._ensure_shell(tmp)
            if not shell:
                return {"available": False, "reason": "aihubshell CLI 다운로드 실패", "ingested": 0}
            args = ["-mode", "d", "-datasetkey", str(dataset_key)]
            if file_key:
                args += ["-filekey", str(file_key)]
            rc, out = await self._run(shell, args, tmp, timeout=timeout)
            if rc != 0:
                return {"available": True, "ingested": 0, "rc": rc,
                        "reason": "다운로드 실패 — 활용신청 승인·datasetkey·filekey·디스크 확인",
                        "output_tail": out[-1500:]}

            # ★컨테이너에 unzip 미설치 → aihubshell이 cat-병합한 .zip을 못 푼다. 파이썬 zipfile로 직접
            #   압축해제(시스템 의존 제거). 중첩(zip-in-zip) 3단계까지. 추출 후 원본 zip 제거(디스크 절약).
            import zipfile
            archives_extracted = 0
            for _ in range(3):
                zips = [p for p in tmp.rglob("*.zip") if p.is_file()]
                if not zips:
                    break
                for z in zips:
                    try:
                        with zipfile.ZipFile(z) as zf:
                            zf.extractall(z.parent / f"{z.stem}_x")
                        z.unlink()
                        archives_extracted += 1
                    except Exception:  # noqa: BLE001 — 손상/부분 zip은 건너뜀(정직).
                        continue

            # 압축해제된 도면 파일 walk → 인제스트(max_files 상한).
            from app.services.design_ingest.ingest_service import ingest_design_file
            ingested, skipped, failed, total = 0, 0, 0, 0
            samples: list[dict[str, Any]] = []
            for p in sorted(tmp.rglob("*")):
                if not p.is_file() or p.name == "aihubshell":
                    continue
                if not p.suffix.lower() in _DRAWING_EXT:
                    continue
                total += 1
                if ingested >= max_files:
                    continue
                try:
                    res = await ingest_design_file(filename=p.name, content=p.read_bytes(), tenant_id=tenant_id)
                    if res.get("indexed"):
                        ingested += 1
                    else:
                        skipped += 1
                    if len(samples) < 10:
                        samples.append({"file": p.name, "indexed": res.get("indexed"), "type": res.get("drawing_type")})
                except Exception:  # noqa: BLE001
                    failed += 1
            return {
                "available": True, "dataset_key": dataset_key, "file_key": file_key,
                "archives_extracted": archives_extracted,
                "total_drawings": total, "ingested": ingested, "skipped": skipped, "failed": failed,
                "samples": samples,
                "note": "aihubshell로 다운로드·압축해제한 도면을 design_drawings(Qdrant)에 시드 인제스트. 도면 확장자만(라벨 JSON 제외).",
            }
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
