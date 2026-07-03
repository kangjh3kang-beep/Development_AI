"""조례 경사 파서 라이브 검증 도구 (C-live-verify).

OrdinanceService.resolve_slope_criteria(시군구 도시계획조례의 개발행위허가
경사도 기준 파서, app/services/land_intelligence/ordinance_service.py)를
실제 법제처 DRF API에 대고 실행해 파싱 결과를 검증한다.

사용법:
    MOLEG_API_KEY=<발급받은 OC값> .venv/bin/python scripts/verify_ordinance_slope_live.py \
        성남시 용인시 화성시 [--force-refresh] [--json-out <경로>]

    - 인자: 시군구 목록(조례 정본 레벨 명칭 권장 — 예: '성남시', '서울특별시').
    - 성공: slope_deg · 조례명 · evidence_span 을 표로 출력.
    - 실패: None + 사유(키 미설정 / 본문 미확보 / 경사도 조항 미발견).
    - 결과는 JSON으로도 저장(기본: scripts/out/ordinance_slope_live_<ts>.json).

키 요구사항 (★키 필요 — 라이브 검증 전제조건):
    - MOLEG_API_KEY 환경변수(법제처 DRF의 OC 파라미터 값). 미설정/플레이스홀더
      ('your-moleg-api-key', 'dummy-*')면 dry 모드로 안내 후 종료(네트워크 미호출).
    - ordinance_service 는 settings.MOLEG_API_KEY 를 읽으므로, 이 스크립트가
      환경변수 값을 settings 에 주입한 뒤 서비스를 호출한다.

운영 실행 절차 (2026-07-02 실검증 결과에 근거):
    1. https://open.law.go.kr → 회원가입 → OPEN API 활용 신청.
       OC = 신청 계정의 이메일 ID(예: kangjh3kang@naver.com → 'kangjh3kang').
    2. ★신청 시 '호출 서버의 IP주소/도메인'을 등록해야 한다. 미등록 IP에서
       호출하면 "사용자 정보 검증에 실패하였습니다 … 정확한 서버장비의
       IP주소 및 도메인주소를 등록해 주세요" 오류가 반환된다.
       (2026-07-02 본 세션에서 OC=test 로 실호출해 위 오류를 실측 — 법제처
       DRF는 공개 테스트 계정을 허용하지 않음. 무근거 키 사용 금지 원칙에
       따라 라이브 검증은 실키 발급 후에만 가능.)
    3. 발급 승인 후: MOLEG_API_KEY=<OC값> 로 본 스크립트 실행.
    4. persist(ordinance_resolutions 테이블) 는 DB 미가동 시 자동 무시되므로
       DB 없이도 파서 검증 자체는 가능하다. 저장까지 검증하려면 apps/api 의
       DATABASE_URL 이 유효해야 한다.

원칙: 무날조 — 파서 실패는 None 그대로 보고(값 생성 금지), 정적 시드 폴백 없음.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any

# apps/api 루트를 import 경로에 추가(스크립트 직접 실행 지원).
_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

_PLACEHOLDER_KEYS = ("your-moleg-api-key", "dummy-moleg-api-key")


def _resolve_api_key() -> str | None:
    """유효한 MOLEG_API_KEY(OC)를 env → settings 순으로 찾는다. 없으면 None."""
    from app.core.config import settings

    key = (os.environ.get("MOLEG_API_KEY") or "").strip()
    if not key:
        key = (getattr(settings, "MOLEG_API_KEY", "") or "").strip()
    if not key or key.lower() in _PLACEHOLDER_KEYS or key.lower().startswith("dummy"):
        return None
    return key


def _print_dry_exit() -> None:
    print(
        "\n[DRY] MOLEG_API_KEY 미설정(또는 플레이스홀더) — 라이브 검증을 실행할 수 없습니다.\n"
        "  절차: 1) https://open.law.go.kr 에서 OPEN API 활용 신청(OC=계정 이메일 ID)\n"
        "        2) 호출 서버 IP/도메인 등록(미등록 IP는 '사용자 정보 검증 실패' 반환)\n"
        "        3) MOLEG_API_KEY=<OC값> 으로 본 스크립트 재실행\n"
        "  참고: 법제처 DRF는 공개 테스트 계정(OC=test)을 허용하지 않음(2026-07-02 실측).\n"
        "  네트워크 호출 없이 종료합니다(exit 2).\n"
    )


async def _verify_one(service: Any, sigungu: str, force_refresh: bool) -> dict[str, Any]:
    """단일 시군구에 대해 resolve_slope_criteria 를 실행하고 결과/사유를 요약."""
    row: dict[str, Any] = {"sigungu": sigungu}
    try:
        result = await service.resolve_slope_criteria(sigungu, force_refresh=force_refresh)
    except Exception as e:  # noqa: BLE001 — 검증 도구: 예외도 결과로 기록(무음 중단 금지)
        row.update({"ok": False, "reason": f"예외: {type(e).__name__}: {e}"})
        return row
    if result is None:
        # 사유 세분화: 본문 확보 여부를 재확인해 '미발견'과 '미확보'를 구분(정직 보고).
        xml_text = await service._fetch_ordinance_xml(sigungu)  # noqa: SLF001 — 검증 도구의 진단 목적
        if xml_text is None:
            reason = "조례 본문 미확보(목록검색 실패/조례ID 없음/API 오류 — 로그 확인)"
        else:
            reason = "본문 확보했으나 개발행위 문맥 '경사도 N도' 조항 미발견(정직 None)"
        row.update({"ok": False, "reason": reason})
        return row
    row.update(
        {
            "ok": True,
            "slope_deg": result.get("slope_deg"),
            "ordinance_name": result.get("ordinance_name"),
            "evidence_span": result.get("evidence_span"),
            "caveat": result.get("caveat"),
            "source": result.get("source"),
            "reused": bool((result.get("provenance") or {}).get("reused")),
        }
    )
    return row


def _print_table(rows: list[dict[str, Any]]) -> None:
    print("\n=== 조례 경사도 라이브 검증 결과 ===")
    header = f"{'시군구':<12} {'결과':<6} {'경사도':<8} {'조례명 / 사유'}"
    print(header)
    print("-" * 100)
    for r in rows:
        if r.get("ok"):
            deg = f"{r['slope_deg']}도"
            detail = str(r.get("ordinance_name") or "")
            if r.get("caveat"):
                detail += f"  [caveat: {r['caveat']}]"
        else:
            deg = "-"
            detail = str(r.get("reason") or "")
        print(f"{r['sigungu']:<12} {'성공' if r.get('ok') else '실패':<6} {deg:<8} {detail}")
        if r.get("ok") and r.get("evidence_span"):
            print(f"{'':<12} 근거: {r['evidence_span']}")
    print("-" * 100)
    ok_n = sum(1 for r in rows if r.get("ok"))
    print(f"성공 {ok_n} / 전체 {len(rows)}\n")


async def _main_async(args: argparse.Namespace) -> int:
    api_key = _resolve_api_key()
    if api_key is None:
        _print_dry_exit()
        return 2

    # ordinance_service 는 settings.MOLEG_API_KEY 를 읽는다 → env 값 주입.
    from app.core.config import settings

    settings.MOLEG_API_KEY = api_key  # type: ignore[misc]

    from app.services.land_intelligence.ordinance_service import OrdinanceService

    service = OrdinanceService()
    rows = [await _verify_one(service, s, args.force_refresh) for s in args.sigungu]

    _print_table(rows)

    out_path = Path(args.json_out) if args.json_out else (
        Path(__file__).resolve().parent / "out"
        / f"ordinance_slope_live_{_dt.datetime.now():%Y%m%d_%H%M%S}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"ran_at": _dt.datetime.now().isoformat(), "force_refresh": args.force_refresh,
             "results": rows},
            ensure_ascii=False, indent=2, default=str,
        ),
        encoding="utf-8",
    )
    print(f"JSON 저장: {out_path}")
    return 0 if all(r.get("ok") for r in rows) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="조례 경사 파서(resolve_slope_criteria) 라이브 검증")
    parser.add_argument("sigungu", nargs="+", help="시군구 목록(조례 정본 레벨 — 예: 성남시 용인시 화성시)")
    parser.add_argument("--force-refresh", action="store_true",
                        help="저장본 무시하고 실시간 재조회(기본은 persist 재사용)")
    parser.add_argument("--json-out", default=None, help="JSON 저장 경로(기본: scripts/out/…)")
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
