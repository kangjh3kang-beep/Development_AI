"""BOQ(공내역서) 실사용자 시나리오 시뮬레이션 — 라이브 서버 E2E (B6).

시나리오(실무 적산 담당자 관점):
  0. /openapi.json 으로 B3 BOQ 라우터 경로 자동탐지(기본 가정: /api/v1/boq/*)
  1. 인증 확인 — 기존 cost.py 라우터 패턴(무인증) 가정.
     401/403 응답 시 테스트유저 가입(/api/v1/auth/register)·로그인 후 재시도.
  2. master/summary → 5공종(건축·기계소방·전기통신소방·조경·토목) 확인
  3. draft 생성 — gfa 52,000㎡ · 300세대 (의정부424 238,504㎡ 대비 ×0.218022...)
     → 건축 항목 수 > 900, 연면적기준 앵커 항목('임시동력+가설전기시설',
        qty_sample=238,504) qty ≈ 52,000 스케일 검증
  4. export → xlsx 저장 + PK 시그니처(b"PK\\x03\\x04") + 크기 > 50KB 확인
  5. apply-cost → 총액(total*) 양수 확인

실행: .venv/bin/python scripts/simulate_boq_user.py
환경변수:
  BOQ_SIM_BASE  대상 서버(기본 http://localhost:8000)
  BOQ_SIM_OUT   xlsx 저장 경로(기본 ./boq_draft_gfa52000_hh300.xlsx)
  BOQ_SIM_EMAIL 인증 필요 시 사용할 테스트유저 이메일(기본 타임스탬프 자동생성)

의존: stdlib + httpx 만. 단계별 [PASS]/[FAIL] 출력, 하나라도 실패 시 exit 1.
출처 정직성: 기준 수치(238,504㎡·앵커 항목)는 services/cost/data/boq_master/
architecture.json(실적 공내역서 1건, n=1)에서 추출된 값과 동일 기준이다.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:  # noqa: PIE786
    print("[FAIL] 사전조건 — httpx 미설치 (.venv/bin/pip install httpx)")
    sys.exit(1)

BASE = os.environ.get("BOQ_SIM_BASE", "http://localhost:8000").rstrip("/")
OUT_XLSX = Path(os.environ.get("BOQ_SIM_OUT", "boq_draft_gfa52000_hh300.xlsx"))

# ── 시나리오 상수(의정부424 마스터 기준) ──
GFA_SQM = 52000.0
HOUSEHOLDS = 300
SAMPLE_GFA_SQM = 238504.0          # 마스터 project.gfa_sqm (실적 1건)
GFA_RATIO = GFA_SQM / SAMPLE_GFA_SQM  # ≈ 0.21802...
ANCHOR_NAME = "임시동력+가설전기시설"   # 건축-0013, spec=연면적기준, qty_sample=238504
MIN_ARCH_ITEMS = 900               # 건축 마스터 고유항목 961 → 초안도 900 초과 기대
MIN_XLSX_BYTES = 50 * 1024

# draft/export/apply-cost 요청 본문 후보(첫 비-422 응답 채택 — B2/B3 키명 변형 흡수)
# B3 정식 계약(중첩 params{gfa_sqm,...})이 최우선 — 평탄형은 레거시 변형 흡수용.
PARAM_BODIES: list[dict[str, Any]] = [
    {"params": {"gfa_sqm": GFA_SQM, "households": HOUSEHOLDS}},
    {"gfa_sqm": GFA_SQM, "households": HOUSEHOLDS},
    {"gfa_sqm": GFA_SQM, "household_count": HOUSEHOLDS},
    {"total_gfa_sqm": GFA_SQM, "households": HOUSEHOLDS},
]

_RESULTS: list[tuple[str, bool, str]] = []


def _report(step: str, ok: bool, detail: str) -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {step} — {detail}")
    _RESULTS.append((step, ok, detail))


# ──────────────────────────────────────
# 경로 탐지 (OpenAPI)
# ──────────────────────────────────────

def _discover_paths(client: httpx.Client) -> dict[str, tuple[str, str]]:
    """openapi.json에서 BOQ 라우터 경로를 탐지한다.

    반환: {"summary"|"draft"|"export"|"apply_cost": (path, method)}
    탐지 실패 시 기본 가정 경로(/api/v1/boq/*)로 폴백한다.
    """
    defaults: dict[str, tuple[str, str]] = {
        "summary": ("/api/v1/boq/master/summary", "GET"),
        "draft": ("/api/v1/boq/draft", "POST"),
        "export": ("/api/v1/boq/export", "POST"),
        "apply_cost": ("/api/v1/boq/apply-cost", "POST"),
    }
    try:
        spec = client.get(f"{BASE}/openapi.json", timeout=30).json()
        paths = spec.get("paths", {})
    except httpx.TransportError:
        raise  # 연결 실패는 step 0에서 정직하게 FAIL 처리
    except Exception as e:  # noqa: BLE001
        print(f"  · openapi.json 탐지 실패({type(e).__name__}) — 기본 경로 가정 사용")
        return defaults

    found: dict[str, tuple[str, str]] = {}
    for path, ops in sorted(paths.items()):
        if "boq" not in path or "{" in path or not isinstance(ops, dict):
            continue
        methods = {m.upper() for m in ops}
        if path.endswith("/summary") and ("GET" in methods or "POST" in methods):
            found.setdefault("summary", (path, "GET" if "GET" in methods else "POST"))
        elif path.endswith("/draft") and ("POST" in methods or "GET" in methods):
            found.setdefault("draft", (path, "POST" if "POST" in methods else "GET"))
        elif path.endswith("/export") and ("POST" in methods or "GET" in methods):
            found.setdefault("export", (path, "POST" if "POST" in methods else "GET"))
        elif path.endswith("/apply-cost") and ("POST" in methods or "GET" in methods):
            found.setdefault("apply_cost", (path, "POST" if "POST" in methods else "GET"))
    for key, default in defaults.items():
        found.setdefault(key, default)
    return found


# ──────────────────────────────────────
# 인증 (필요 시에만)
# ──────────────────────────────────────

def _ensure_auth(client: httpx.Client, probe_path: str, probe_method: str) -> str:
    """무인증 우선 — 401/403일 때만 테스트유저 가입·로그인 후 토큰 장착."""
    resp = client.request(probe_method, f"{BASE}{probe_path}")
    if resp.status_code not in (401, 403):
        return "무인증 접근 가능(기존 cost.py 라우터 패턴과 동일)"

    email = os.environ.get("BOQ_SIM_EMAIL", f"boq-sim-{int(time.time())}@propai.test")
    password = "BoqSim!20260612"
    reg = client.post(f"{BASE}/api/v1/auth/register", json={
        "email": email, "password": password,
        "name": "BOQ 시뮬레이션", "company_name": "",
    })
    token: str | None = None
    if reg.status_code in (200, 201):
        token = reg.json().get("access_token")
    else:  # 기존 유저 등 — 로그인 폴백
        login = client.post(f"{BASE}/api/v1/auth/login",
                            json={"email": email, "password": password})
        if login.status_code == 200:
            token = login.json().get("access_token")
    if not token:
        raise RuntimeError(
            f"인증 필요하나 가입/로그인 실패 (register={reg.status_code}) — "
            "BOQ_SIM_EMAIL/기동 DB 상태 확인")
    client.headers["Authorization"] = f"Bearer {token}"
    return f"테스트유저 인증 사용({email})"


# ──────────────────────────────────────
# 응답 형태 표준화 헬퍼 (B2/B3 응답 키 변형 흡수)
# ──────────────────────────────────────

def _norm_disc(raw: str) -> str:
    s = str(raw).lower()
    if "건축" in s or "arch" in s:
        return "architecture"
    if "기계" in s or "mech" in s:
        return "mechanical"
    if "전기" in s or "elec" in s:
        return "electrical"
    if "조경" in s or "land" in s:
        return "landscape"
    if "토목" in s or "civil" in s:
        return "civil"
    return s


def _discipline_names(summary: Any) -> list[str]:
    d = summary.get("disciplines") if isinstance(summary, dict) else None
    if isinstance(d, dict):
        return [str(k) for k in d]
    if isinstance(d, list):
        names = []
        for e in d:
            if isinstance(e, dict):
                names.append(str(e.get("discipline") or e.get("name")
                                 or e.get("key") or e.get("file") or ""))
            else:
                names.append(str(e))
        return names
    return []


def _items_by_discipline(draft: Any) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(draft, dict):
        return out
    disc = draft.get("disciplines")
    if isinstance(disc, dict):
        for k, v in disc.items():
            items = v.get("items") if isinstance(v, dict) else (v if isinstance(v, list) else [])
            out.setdefault(_norm_disc(k), []).extend(
                i for i in (items or []) if isinstance(i, dict))
        return out
    if isinstance(disc, list):
        for e in disc:
            if not isinstance(e, dict):
                continue
            k = e.get("discipline") or e.get("key") or e.get("name") or ""
            out.setdefault(_norm_disc(str(k)), []).extend(
                i for i in (e.get("items") or []) if isinstance(i, dict))
        return out
    items = draft.get("items")
    if isinstance(items, list):
        for i in items:
            if not isinstance(i, dict):
                continue
            k = i.get("discipline") or i.get("disc") or str(i.get("id", ""))[:2]
            out.setdefault(_norm_disc(str(k)), []).append(i)
    return out


def _qty(item: dict[str, Any]) -> float | None:
    for key in ("qty", "quantity", "qty_scaled", "scaled_qty", "qty_draft", "draft_qty"):
        v = item.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def _find_positive_total(obj: Any, depth: int = 0) -> tuple[str, float] | None:
    """응답 JSON에서 키명에 total이 포함된 첫 양수 수치를 찾는다(중첩 탐색)."""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if (isinstance(v, (int, float)) and not isinstance(v, bool)
                    and "total" in str(k).lower() and v > 0):
                return str(k), float(v)
        for v in obj.values():
            r = _find_positive_total(v, depth + 1)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj[:50]:
            r = _find_positive_total(v, depth + 1)
            if r:
                return r
    return None


def _call(client: httpx.Client, path: str, method: str,
          bodies: list[dict[str, Any]]) -> httpx.Response:
    """본문 후보를 순서대로 시도 — 400/422가 아니면 즉시 채택."""
    resp: httpx.Response | None = None
    for body in bodies:
        if method == "GET":
            resp = client.get(f"{BASE}{path}",
                              params={k: v for k, v in body.items()
                                      if isinstance(v, (int, float, str))})
        else:
            resp = client.post(f"{BASE}{path}", json=body)
        if resp.status_code not in (400, 422):
            return resp
    assert resp is not None
    return resp


# ──────────────────────────────────────
# 메인 시나리오
# ──────────────────────────────────────

def main() -> int:
    print(f"BOQ 사용자 시나리오 시뮬레이션 — 대상: {BASE}")
    print(f"  파라미터: gfa={GFA_SQM:,.0f}㎡ · {HOUSEHOLDS}세대 "
          f"(의정부424 {SAMPLE_GFA_SQM:,.0f}㎡ 대비 ×{GFA_RATIO:.6f})")

    client = httpx.Client(timeout=120)
    try:
        # 0) 서버 연결 + 경로 탐지
        try:
            paths = _discover_paths(client)
        except httpx.TransportError as e:
            _report("0.연결", False, f"{BASE} 연결 실패({type(e).__name__}) — "
                                     "서버 기동 후 재실행 "
                                     "(uvicorn apps.api.main:app --port 8000)")
            return 1
        _report("0.연결", True, "경로 탐지: " + ", ".join(
            f"{k}={p}({m})" for k, (p, m) in sorted(paths.items())))

        # 1) 인증 패턴 확인
        try:
            auth_mode = _ensure_auth(client, *paths["summary"])
            _report("1.인증", True, auth_mode)
        except Exception as e:  # noqa: BLE001
            _report("1.인증", False, str(e))
            return 1

        # 2) master/summary → 5공종
        sp, sm = paths["summary"]
        resp = client.request(sm, f"{BASE}{sp}")
        if resp.status_code != 200:
            _report("2.master/summary", False,
                    f"HTTP {resp.status_code} — {resp.text[:200]}")
            return 1
        names = _discipline_names(resp.json())
        normed = {_norm_disc(n) for n in names}
        expected = {"architecture", "mechanical", "electrical", "landscape", "civil"}
        ok = len(names) == 5 and normed == expected
        _report("2.master/summary", ok,
                f"공종 {len(names)}개: {names}" + ("" if ok else f" (기대 5공종 {sorted(expected)})"))
        if not ok:
            return 1

        # 3) draft 생성 + 스케일 검증
        dp, dm = paths["draft"]
        resp = _call(client, dp, dm, PARAM_BODIES)
        if resp.status_code != 200:
            _report("3.draft", False, f"HTTP {resp.status_code} — {resp.text[:200]}")
            return 1
        draft = resp.json()
        by_disc = _items_by_discipline(draft)
        arch = by_disc.get("architecture", [])
        ok_count = len(arch) > MIN_ARCH_ITEMS
        _report("3.draft 건축 항목수", ok_count,
                f"{len(arch)}개 (기준 > {MIN_ARCH_ITEMS})")

        anchors = [i for i in arch if ANCHOR_NAME in str(i.get("name") or i.get("item_name") or "")]
        anchor_qty = _qty(anchors[0]) if anchors else None
        ok_scale = anchor_qty is not None and abs(anchor_qty - GFA_SQM) <= 1.0
        _report("3.draft 수량 스케일(연면적기준 앵커)", ok_scale,
                f"'{ANCHOR_NAME}' qty={anchor_qty} (기대 ≈ {GFA_SQM:,.0f} "
                f"= 238,504 × {GFA_RATIO:.6f})" if anchors
                else f"앵커 항목 '{ANCHOR_NAME}' 미발견")
        if not (ok_count and ok_scale):
            return 1

        # 4) export → xlsx 저장·검증
        ep, em = paths["export"]
        resp = _call(client, ep, em, PARAM_BODIES + [{"draft": draft}])
        if resp.status_code != 200:
            _report("4.export", False, f"HTTP {resp.status_code} — {resp.text[:200]}")
            return 1
        content = resp.content
        is_xlsx = content[:4] == b"PK\x03\x04"
        big_enough = len(content) > MIN_XLSX_BYTES
        saved = ""
        if is_xlsx:
            try:
                OUT_XLSX.write_bytes(content)
                saved = f" → 저장 {OUT_XLSX}"
            except OSError as e:
                saved = f" (저장 실패: {e} — BOQ_SIM_OUT 경로 확인)"
        _report("4.export xlsx", is_xlsx and big_enough,
                f"PK시그니처={'OK' if is_xlsx else 'NO'} · {len(content):,}B "
                f"(기준 > {MIN_XLSX_BYTES:,}B)" + saved)
        if not (is_xlsx and big_enough):
            return 1

        # 5) apply-cost → 총액 양수 (B3 정식 계약: + project_id 필수)
        ap, am = paths["apply_cost"]
        ap_bodies = [{**b, "project_id": "sim-user"} for b in PARAM_BODIES]
        resp = _call(client, ap, am, ap_bodies + [{"draft": draft}])
        if resp.status_code != 200:
            _report("5.apply-cost", False, f"HTTP {resp.status_code} — {resp.text[:200]}")
            return 1
        total = _find_positive_total(resp.json())
        _report("5.apply-cost 총액", total is not None,
                f"{total[0]}={total[1]:,.0f} (양수)" if total
                else "total* 양수 키 미발견 — 응답: " + json.dumps(
                    resp.json(), ensure_ascii=False)[:200])
        if total is None:
            return 1
    finally:
        client.close()
        passed = sum(1 for _, ok, _ in _RESULTS if ok)
        print(f"\n결과: {passed}/{len(_RESULTS)} PASS")

    return 0 if all(ok for _, ok, _ in _RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
