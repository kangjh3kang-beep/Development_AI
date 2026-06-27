"""기하 불변식 하드게이트 — 설계 매스/폴리곤이 '무효 결과'로 통과하는 것을 차단한다.

이 모듈은 무엇을 하나(쉬운 설명):
- 설계 자동생성이 내놓은 '건물 매스(dict)'나 '폴리곤(점 목록)'을 받아서,
  ① 폴리곤이 실제로 올바른 도형인지 ② 건물이 대지보다 크지 않은지 ③ 면적 계산이
  서로 맞는지 ④ 층수가 말이 되는지 ⑤ 주거 건물인데 0세대가 아닌지 ⑥ 건폐율/용적률이
  법정 한도를 넘지 않았는지를 점검한다.
- 점검 결과를 PASS / PASS_WITH_WARNINGS / FAIL 세 등급으로 돌려준다.

★1차 운영은 '그림자(shadow)' 방식이다 — 이 모듈은 판정만 하고 절대 차단하지 않는다.
  실제로 막을지(차단)는 호출부(auto_design_engine)가 config 플래그
  GEOMETRY_INVARIANT_ENFORCE를 보고 결정한다. 기본값 False라 정상 흐름은 그대로다.

★무날조 원칙: 입력에 필요한 값이 없으면 그 체크는 SKIP한다(가짜 PASS/FAIL을 만들지 않음).
  모든 수치는 0/None/NaN을 가드한다.

신규 의존성 0: shapely는 이미 cad 다른 서비스에서 쓰는 기존 의존성이며, 여기서는
  폴리곤 체크에서만 '지연 import'한다(shapely 미설치 환경에선 폴리곤 체크만 SKIP).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 허용 오차(상대) — 부동소수점·반올림 누적으로 인한 미세 불일치를 정상으로 본다.
_DEFAULT_TOL = 0.02  # 2%

# 주거(공동주택 등)로 보는 용도 — 0세대 차단(INV-GEO-UNITS)에 쓴다.
_RESIDENTIAL_USES = frozenset({"공동주택", "주거", "아파트", "주상복합", "다세대", "연립"})


class GeoStatus(str, Enum):  # noqa: UP042 — StrEnum은 3.11+ 전용이라 3.10 호환 위해 (str, Enum) 사용(기존 7개 enum과 정합)
    """기하 점검 등급 — 숫자가 클수록 나쁨(최악 집계에 사용)."""

    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"


# 등급 심각도 순위(최악 집계용) — FAIL이 가장 나쁨.
_SEVERITY: dict[GeoStatus, int] = {
    GeoStatus.PASS: 0,
    GeoStatus.PASS_WITH_WARNINGS: 1,
    GeoStatus.FAIL: 2,
}


@dataclass
class InvariantCheck:
    """개별 불변식 한 건의 점검 결과."""

    code: str  # 예: "INV-GEO-001"
    name: str  # 사람이 읽는 이름(쉬운 한국어)
    status: GeoStatus
    detail: str  # 무엇을 봤고 왜 이 등급인지 한 줄 설명

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass
class GeometryInvariantResult:
    """전체 기하 점검 결과 묶음(최악 등급 + 개별 체크 + 경고/오류 목록)."""

    status: GeoStatus = GeoStatus.PASS
    checks: list[InvariantCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, check: InvariantCheck) -> None:
        """체크 한 건을 추가하고 전체 최악 등급·경고/오류 목록을 갱신한다.

        SKIP(=입력 부족으로 미점검)은 따로 등급에 영향을 주지 않으려고, 상태가
        PASS인 SKIP 표기 체크라도 등급은 PASS로만 본다(가짜 FAIL 방지).
        """
        self.checks.append(check)
        # 전체 최악 등급 갱신
        if _SEVERITY[check.status] > _SEVERITY[self.status]:
            self.status = check.status
        # 경고/오류 텍스트 누적(소비처에서 바로 표기용)
        if check.status is GeoStatus.FAIL:
            self.errors.append(f"[{check.code}] {check.detail}")
        elif check.status is GeoStatus.PASS_WITH_WARNINGS:
            self.warnings.append(f"[{check.code}] {check.detail}")

    @property
    def is_fail(self) -> bool:
        return self.status is GeoStatus.FAIL

    def to_dict(self) -> dict[str, Any]:
        """매스 dict에 부착(additive)하거나 후속 증분 재사용을 위한 직렬화."""
        return {
            "status": self.status.value,
            "checks": [c.to_dict() for c in self.checks],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


# ── 작은 수치 헬퍼(무날조 가드) ──

def _num(value: Any) -> float | None:
    """값이 유한한 숫자면 float로, 아니면 None(=미상→SKIP 신호)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _rel_close(a: float, b: float, tol: float = _DEFAULT_TOL) -> bool:
    """상대오차 tol 이내로 두 값이 같은지(분모 0 가드)."""
    if a == 0 and b == 0:
        return True
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom <= tol


# ── 폴리곤 좌표 정규화 ──

def _normalize_coords(
    coords: list[tuple[float, float]] | list[dict[str, Any]] | None,
) -> list[tuple[float, float]]:
    """[(x,y),...] 또는 [{x,y},...] 입력을 (x,y) 튜플 리스트로 통일한다(무효 점은 버림)."""
    out: list[tuple[float, float]] = []
    if not coords:
        return out
    for pt in coords:
        if isinstance(pt, dict):
            x = _num(pt.get("x"))
            y = _num(pt.get("y"))
        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
            x = _num(pt[0])
            y = _num(pt[1])
        else:
            x = y = None
        if x is not None and y is not None:
            out.append((x, y))
    return out


# ── 개별 체크 함수들(모두 InvariantCheck 또는 None 반환 — None=SKIP) ──

def _check_polygon_validity(mass: dict[str, Any]) -> InvariantCheck | None:
    """INV-GEO-001 폴리곤 유효성: building_shape 폴리곤이 있으면 shapely로 검증.

    폴리곤 정보가 전혀 없으면 None(SKIP) — footprint만 있는 단순 사각형 매스는
    별도 폴리곤 도형이 아니므로 이 체크 대상이 아니다(가짜 경고 금지).
    """
    shape = mass.get("building_shape") or mass.get("polygon") or mass.get("footprint_polygon")
    coords = _normalize_coords(shape if isinstance(shape, list) else None)
    if len(coords) < 3:
        return None  # 폴리곤 정보 없음 → SKIP(경고 아님)
    return _check_polygon_validity_coords("INV-GEO-001", coords)


def _check_polygon_validity_coords(code: str, coords: list[tuple[float, float]]) -> InvariantCheck:
    """좌표 리스트의 폴리곤 유효성(닫힘·단순·자기교차)을 shapely로 점검한다.

    shapely 미설치 환경에선 라이브러리를 못 쓰므로 정직하게 SKIP 의미의 PASS+설명을
    돌려준다(가짜 FAIL 금지). 운영 환경엔 shapely가 설치돼 있어 정상 검증된다.
    """
    name = "폴리곤 유효성(닫힘·단순·자기교차 없음)"
    try:
        from shapely.geometry import Polygon  # 지연 import — 미설치 환경 가드
    except ImportError:
        return InvariantCheck(code, name, GeoStatus.PASS, "shapely 미가용 — 폴리곤 검증 생략(SKIP)")

    try:
        poly = Polygon(coords)
    except (ValueError, TypeError) as exc:  # 좌표가 폴리곤이 안 됨
        return InvariantCheck(code, name, GeoStatus.FAIL, f"폴리곤 구성 실패 — {exc}")

    if not poly.is_valid:
        # 자기교차 등 무효 — make_valid로 복구 가능한지만 정직 표기(여기선 FAIL 처리)
        try:
            from shapely.validation import make_valid

            fixed = make_valid(poly)
            note = "복구 가능" if (fixed is not None and not fixed.is_empty) else "복구 불가"
        except Exception:  # noqa: BLE001 — make_valid 실패도 무효로 본다
            note = "복구 불가"
        return InvariantCheck(code, name, GeoStatus.FAIL, f"폴리곤이 유효하지 않음(자기교차 등) — {note}")

    if not poly.is_simple:
        return InvariantCheck(code, name, GeoStatus.FAIL, "폴리곤이 단순하지 않음(self-intersection)")

    return InvariantCheck(code, name, GeoStatus.PASS, "폴리곤 유효(닫힘·단순)")


def _check_footprint_within_site(
    mass: dict[str, Any], site_area_sqm: float | None
) -> InvariantCheck | None:
    """INV-GEO-002 footprint ≤ 부지면적: 건축면적이 대지보다 크면 무효(FAIL)."""
    code, name = "INV-GEO-002", "건축면적 ≤ 대지면적"
    site = _num(site_area_sqm)
    fp = _num(mass.get("building_footprint_sqm"))
    if site is None or site <= 0 or fp is None:
        return None  # 대지면적/건축면적 미상 → SKIP
    if fp > site * (1 + _DEFAULT_TOL):
        return InvariantCheck(
            code, name, GeoStatus.FAIL,
            f"건축면적 {fp:.1f}㎡가 대지면적 {site:.1f}㎡를 초과 — 무효 매스",
        )
    return InvariantCheck(code, name, GeoStatus.PASS, f"건축면적 {fp:.1f}㎡ ≤ 대지 {site:.1f}㎡")


def _check_area_conservation(mass: dict[str, Any]) -> InvariantCheck | None:
    """INV-GEO-006 면적보존: footprint ≈ width × depth(상대오차 2%).

    podium-tower 매스면 tower/podium 각각의 width×depth가 그 footprint와 맞는지 본다.
    불일치는 '엔진 내부 정합 경고'라 FAIL이 아니라 PASS_WITH_WARNINGS다(차단 대상 아님).
    """
    code, name = "INV-GEO-006", "면적 보존(footprint=width×depth)"
    profile = mass.get("massing_profile")

    # podium-tower면 각 박스 footprint 보존을 검사
    if profile == "podium_tower":
        problems: list[str] = []
        for label, box in (("tower", mass.get("tower")), ("podium", mass.get("podium"))):
            if not isinstance(box, dict):
                continue
            w = _num(box.get("width_m"))
            d = _num(box.get("depth_m"))
            bfp = _num(box.get("footprint_sqm"))
            if w is None or d is None or bfp is None or w <= 0 or d <= 0:
                continue  # 부분 미상 → 그 박스만 건너뜀
            if not _rel_close(bfp, w * d):
                problems.append(f"{label}: {bfp:.1f}≠{w:.1f}×{d:.1f}={w * d:.1f}")
        if problems:
            return InvariantCheck(
                code, name, GeoStatus.PASS_WITH_WARNINGS,
                "podium-tower 면적 불일치(엔진 내부 정합 경고) — " + "; ".join(problems),
            )
        return InvariantCheck(code, name, GeoStatus.PASS, "podium-tower 면적 보존 정합")

    # 단일박스: footprint ≈ width × depth
    w = _num(mass.get("building_width_m"))
    d = _num(mass.get("building_depth_m"))
    fp = _num(mass.get("building_footprint_sqm"))
    if w is None or d is None or fp is None or w <= 0 or d <= 0:
        return None  # 치수/면적 미상 → SKIP
    if not _rel_close(fp, w * d):
        return InvariantCheck(
            code, name, GeoStatus.PASS_WITH_WARNINGS,
            f"면적 불일치(경고) — footprint {fp:.1f} ≠ {w:.1f}×{d:.1f}={w * d:.1f}",
        )
    return InvariantCheck(code, name, GeoStatus.PASS, f"면적 보존 — footprint≈{w:.1f}×{d:.1f}")


def _check_floors(mass: dict[str, Any]) -> InvariantCheck | None:
    """INV-GEO-FLOORS 층수 정합: num_floors>0, floors_for_units가 0<…≤num_floors.

    floors_for_units가 num_floors를 초과하면 podium 층까지 주거로 중복계산한 것 →
    세대수 과대산정 위험이라 FAIL로 차단한다.
    """
    code, name = "INV-GEO-FLOORS", "층수 정합"
    nf = _num(mass.get("num_floors"))
    if nf is None:
        return None  # 층수 미상 → SKIP
    if nf <= 0:
        return InvariantCheck(code, name, GeoStatus.FAIL, f"층수 {nf:.0f} — 0 이하 무효")

    ffu_raw = mass.get("floors_for_units")
    ffu = _num(ffu_raw)
    if ffu_raw is not None and ffu is not None:
        if ffu <= 0:
            return InvariantCheck(code, name, GeoStatus.FAIL, f"주거층수 {ffu:.0f} — 0 이하 무효")
        if ffu > nf + 1e-9:
            return InvariantCheck(
                code, name, GeoStatus.FAIL,
                f"주거층수 {ffu:.0f}가 전체층수 {nf:.0f} 초과 — podium 중복계산 의심",
            )
    return InvariantCheck(code, name, GeoStatus.PASS, f"층수 {nf:.0f} 정합")


def _check_units(
    mass: dict[str, Any],
    total_units: int | None,
    building_use: str | None,
    units_feasible: bool | None = None,
) -> InvariantCheck | None:
    """INV-GEO-UNITS 세대 성립(★0세대 버그 차단).

    주거 매스이고 연면적>0·층수>0인데 total_units==0이면 코어/면적 산정 '버그'로 본다(FAIL).
    ★단 units_feasible=False면(작은 부지에서 순면적<최소평형이라 엔진이 '정직하게' 0세대를 반환한
      정상 결과) 버그가 아니므로 FAIL이 아니라 PASS_WITH_WARNINGS로 둔다(승격 시 소형부지 대량 오탐 방지).
    total_units가 미상이면 SKIP(가짜 판정 금지).
    """
    code, name = "INV-GEO-UNITS", "세대 성립(0세대 차단)"
    if total_units is None:
        return None  # 세대수 미상 → SKIP
    units = _num(total_units)
    if units is None:
        return None
    use = (building_use or "").strip()
    if use not in _RESIDENTIAL_USES:
        return None  # 비주거 매스는 0세대(상가만)가 정상일 수 있음 → SKIP

    tfa = _num(mass.get("total_floor_area_sqm"))
    nf = _num(mass.get("num_floors"))
    if tfa is None or nf is None:
        return None  # 연면적/층수 미상 → SKIP
    if tfa > 0 and nf > 0 and units == 0:
        if units_feasible is False:
            # 엔진이 '성립 불가'를 정직하게 표기한 정상 0세대(작은 부지) — 버그 아님. 경고만.
            return InvariantCheck(
                code, name, GeoStatus.PASS_WITH_WARNINGS,
                "0세대(순면적<최소평형 — 정직한 성립 불가, 버그 아님)",
            )
        return InvariantCheck(
            code, name, GeoStatus.FAIL,
            "주거 매스인데 0세대 — 코어/면적 산정 오류(버그)",
        )
    return InvariantCheck(code, name, GeoStatus.PASS, f"세대 {units:.0f}세대 성립")


def _check_legal(mass: dict[str, Any]) -> InvariantCheck | None:
    """INV-GEO-LEGAL 법정 이내: bcr_pct/far_pct가 적용 법정 한도(+tol) 이내인지.

    applied_max_* 한도가 미상이면 SKIP. 초과는 법정초과 과대표시라 FAIL.
    """
    code, name = "INV-GEO-LEGAL", "법정 한도 이내(건폐율·용적률)"
    problems: list[str] = []
    skipped_all = True

    bcr = _num(mass.get("bcr_pct"))
    max_bcr = _num(mass.get("applied_max_bcr_pct"))
    if bcr is not None and max_bcr is not None and max_bcr > 0:
        skipped_all = False
        if bcr > max_bcr * (1 + _DEFAULT_TOL):
            problems.append(f"건폐율 {bcr:.1f}% > 한도 {max_bcr:.1f}%")

    far = _num(mass.get("far_pct"))
    max_far = _num(mass.get("applied_max_far_pct"))
    if far is not None and max_far is not None and max_far > 0:
        skipped_all = False
        if far > max_far * (1 + _DEFAULT_TOL):
            problems.append(f"용적률 {far:.1f}% > 한도 {max_far:.1f}%")

    if skipped_all:
        return None  # 적용 한도 미상 → SKIP
    if problems:
        return InvariantCheck(code, name, GeoStatus.FAIL, "법정 초과 — " + "; ".join(problems))
    return InvariantCheck(code, name, GeoStatus.PASS, "건폐율·용적률 법정 이내")


# ── 공용 진입점 ──

def check_mass_invariants(
    mass: dict[str, Any],
    *,
    site_area_sqm: float | None = None,
    total_units: int | None = None,
    building_use: str | None = None,
    units_feasible: bool | None = None,
) -> GeometryInvariantResult:
    """건물 매스 dict의 기하 불변식을 모두 점검해 결과 묶음을 돌려준다.

    무날조: 입력 키가 미상이면 해당 체크는 SKIP(결과 묶음에 포함되지 않음).
    무회귀: 이 함수는 판정만 한다 — 차단/예외는 호출부가 플래그를 보고 결정한다.
    """
    result = GeometryInvariantResult()
    if not isinstance(mass, dict):
        return result  # 매스가 dict가 아니면 점검할 게 없음(빈 PASS)

    for check in (
        _check_polygon_validity(mass),
        _check_footprint_within_site(mass, site_area_sqm),
        _check_area_conservation(mass),
        _check_floors(mass),
        _check_units(mass, total_units, building_use, units_feasible),
        _check_legal(mass),
    ):
        if check is not None:  # None=SKIP(미상)
            result.add(check)
    return result


def check_polygon_invariants(
    coords: list[tuple[float, float]] | list[dict[str, Any]],
) -> GeometryInvariantResult:
    """DesignGeometry 폴리곤(점 목록)의 유효성을 점검한다(닫힘·단순·자기교차).

    좌표가 3점 미만이면 폴리곤이 못 되므로 SKIP(빈 PASS) — 가짜 FAIL을 만들지 않는다.
    """
    result = GeometryInvariantResult()
    norm = _normalize_coords(coords)
    if len(norm) < 3:
        return result  # 폴리곤 정보 부족 → SKIP
    result.add(_check_polygon_validity_coords("INV-GEO-001", norm))
    return result
