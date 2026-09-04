"""PNU 유효성 판정은 **한 곳**이다 — 손수 길이 검사를 금지하는 파생형 래칫.

## 왜 생겼나 (2026-09-02 실측)

`app/utils/pnu.py` 는 스스로를 *"프론트 `apps/web/lib/pnu.ts` 의 **백엔드 미러**"* 라 선언하는데
`is_valid_pnu` 의 **프로덕션 소비처가 0** 이었다(자기 파일과 자기 테스트뿐).
같은 판정을 손으로 쓴 자리가 **18벌**이었고 **옳은 것은 2벌**이었다:

    단방향 10벌   `len(pnu) < 19` · `>= 19`   → ★**26자 오염값이 통과**한다
    길이만  6벌   `len(pnu) == 19`            → ★**19자 비숫자가 통과**한다
    정확     2벌   `!= 19 or not isdigit()`

★단방향은 이 저장소가 이미 배운 것의 **거울상**이다 — 회귀망 §D-19
*"경계를 걸면 양방향으로 걸어라. 상한만 걸었더니 하한이 0으로 붕괴했다"*. 여기서는 **하한만** 걸었다.

통과 직후 무엇을 하는지가 문제다 — **자르거나 외부로 보낸다**:
`sigungu_cd = pnu[:5]` · `sgg, bjd = pnu[:5], pnu[5:10]` · `vworld.get_land_info(pnu)`.
라이브 오염값 `'store-rep-용인시 수지구 신봉동 56-1'`(**26자**)은 `< 19` 가드를 통과해
`sigungu_cd = "store"` 를 만들고, 그것이 **건축물대장 API 로 나간다.**

## 이 락이 잠그는 것

1. **손수 길이 검사 0건** — `ast` 로 `len(<pnu…>) <op> 19` 를 **파생 수집**한다(손 목록 아님).
2. **★공허진리 방지** — 모집단이 0 이 되면 «위반 0» 이 참이 되므로 `is_valid_pnu` **호출부 하한**을
   함께 단언한다. 배선을 통째로 지우면 이쪽이 빨개진다.
3. **판정 자체** — 두 구멍(단방향·길이만)을 **서로 다른 입력**으로 가른다.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from apps.api.app.utils.pnu import is_valid_pnu, normalize_pnu

API_ROOT = pathlib.Path(__file__).resolve().parents[1]

# ★2026-09-02 배선 시점 **호출부** 실측 28. 축이 호출부라 한 개만 지워도 줄어든다.
#   (종전 하한은 축이 «파일» 이라 11 이었고, 한 파일 안 호출부를 지워도 반응하지 않았다.)
_MIN_CALL_SITES = 28


def _py_files() -> list[pathlib.Path]:
    out = []
    for p in API_ROOT.rglob("*.py"):
        s = str(p)
        if "/tests/" in s or p.name.startswith("test_") or "/.venv/" in s or "/migrations/" in s:
            continue
        out.append(p)
    return out


# ★PNU 를 자르는 상수는 19 하나가 아니다 — 5(시군구) · 10(법정동) · 19(전체).
#   종전 수집기는 **19 만** 봐서 `len(pnu) >= 5` 7건과 `>= 10` 1건을 **통째로 놓쳤다**.
_PNU_SLICE_CONSTS = (5, 10, 19)

# ★의도가 코드에 적혀 있고 **자릿수까지 검사하는** 자리는 예외로 등재한다(사유 필수).
#   fail-closed: 여기 없는 새 손수 검사는 무조건 빨개진다.
_EXEMPT: dict[str, str] = {
    # ★2026-09-04 — 코드가 `sale_price_resolver` 로 **이관**되며 경로가 바뀌었다.
    #   래칫이 그것을 정확히 잡았다(파생형이라 새 파일이 자동으로 감시망에 들어온다).
    #   **사유는 그대로다** — 코드도 의도도 안 바뀌고 **자리만** 옮겼다.
    "app/services/feasibility/sale_price_resolver.py:72":
        "의도된 관대함 — 주석이 'PNU가 짧아도 앞 5자리가 숫자면 시군구코드로 사용(자체 충족)'이라 "
        "명시하고 `pnu[:5].isdigit()` 로 자릿수를 검사한다. 좁히면 정상 폴백이 죽는다.",
    "services/avm_service.py:511":
        "`request.pnu[:5].isdigit()` 로 자릿수를 함께 검사한다 — 오염 문자열은 통과하지 못한다.",
}


def _hand_rolled_length_guards() -> list[tuple[str, int, str]]:
    """PNU 를 자르기 위한 **손수 길이 검사**를 파생 수집한다.

    ★축이 «이름» 이 아니라 «역할» 이다(적대 리뷰 C-1 실측 반영):
      ①비교의 **양변 모두**에서 `len()` 을 찾는다 — 종전엔 `n.left` 만 봐서
        `19 > len(pnu)`(피연산자 순서만 뒤집은 동일 의미)가 **SURVIVED** 했다.
      ②상수는 **5·10·19 전부** — 종전엔 19 만 봐서 `>= 5`·`>= 10` 를 놓쳤다.
    """
    hits: list[tuple[str, int, str]] = []
    for p in _py_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:  # ★못 읽으면 조용히 0 으로 세지 않는다 — 시끄럽게 실패시킨다.
            pytest.fail(f"파싱 불가로 판정할 수 없다: {p}")
        for n in ast.walk(tree):
            if not isinstance(n, ast.Compare):
                continue
            sides = [n.left, *n.comparators]
            if not any(
                isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == "len"
                for x in sides
            ):
                continue
            expr = ast.unparse(n)
            if "pnu" not in expr.lower():
                continue
            if not any(
                isinstance(c, ast.Constant) and c.value in _PNU_SLICE_CONSTS for c in sides
            ):
                continue
            key = f"{p.relative_to(API_ROOT)}:{n.lineno}"
            if key in _EXEMPT:
                continue
            hits.append((str(p.relative_to(API_ROOT)), n.lineno, expr[:90]))
    return hits


_SSOT_FUNCS = {"is_valid_pnu", "normalize_pnu", "bcode_from_pnu", "lawd_cd_from_pnu"}


def _ssot_call_sites() -> list[str]:
    """SSOT 함수 **호출부**를 `파일:줄` 로 수집한다(정의 파일 제외).

    ★축이 «파일» 이 아니라 «호출부» 다(적대 리뷰 C-2 실측 반영):
      종전엔 파일당 `break` 라 1 로 셌고, 그래서 **한 파일 안의 호출부 3개 중 2개를
      통째로 지워도** 개수가 안 줄어 락이 초록이었다(가드 삭제 변이 SURVIVED).
    """
    out: list[str] = []
    for p in _py_files():
        if p.name == "pnu.py" and p.parent.name == "utils":
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            pytest.fail(f"파싱 불가로 판정할 수 없다: {p}")
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id in _SSOT_FUNCS
            ):
                out.append(f"{p.relative_to(API_ROOT)}:{n.lineno}")
    return out


class Test판정은한곳이다:
    def test_손수_길이검사가_남아있지_않다(self):
        hits = _hand_rolled_length_guards()
        assert hits == [], (
            "PNU 길이를 손으로 재는 자리가 남았다 — `is_valid_pnu` 를 쓸 것.\n"
            "★`< 19`·`>= 19` 는 **하한만** 걸어 26자 오염값을 통과시키고,\n"
            "  `== 19` 는 숫자를 안 봐 19자 비숫자를 통과시킨다.\n"
            + "\n".join(f"  {f}:{ln}  {e}" for f, ln, e in hits)
        )

    def test_공허진리_방지_배선이_실재한다(self):
        """★모집단이 0 이면 위 단언은 참이 된다 — **호출부** 하한을 따로 못 박는다."""
        sites = _ssot_call_sites()
        # 2026-09-02 배선 시점 실측. ★축이 호출부이므로 **한 호출부만 지워도** 줄어든다.
        assert len(sites) >= _MIN_CALL_SITES, (
            f"SSOT 호출부가 {len(sites)}개다(하한 {_MIN_CALL_SITES}) — 배선이 걷혔다.\n"
            "★이 하한이 없으면 위 「손수 검사 0건」이 **모집단 0** 으로도 참이 된다.\n"
            + "\n".join(f"  {s}" for s in sorted(sites))
        )

    def test_수집기가_살아있다_대조군(self):
        """★조회기 생존 — 일부러 넣은 손수 검사가 **잡히는지** 본다(없으면 위 0건이 무의미)."""
        src = "def f(pnu):\n    if len(pnu) < 19:\n        return None\n"
        tree = ast.parse(src)
        found = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Compare)
            and isinstance(n.left, ast.Call)
            and isinstance(n.left.func, ast.Name)
            and n.left.func.id == "len"
            and "pnu" in ast.unparse(n).lower()
            and any(isinstance(c, ast.Constant) and c.value == 19 for c in n.comparators)
        ]
        assert len(found) == 1, "수집기가 죽었다 — 위 「위반 0건」은 근거가 아니다"


class Test두구멍을다른입력으로가른다:
    """★단방향 구멍과 길이만 구멍은 **서로 다른 입력**으로 드러난다 — 하나로 뭉치면
    한쪽만 고쳐도 초록이다."""

    def test_구멍A_하한만_걸면_통과하던_값(self):
        # 라이브 실측 오염값 — 26자라 `len(pnu) < 19` 를 **통과**했다.
        bad = "store-rep-용인시 수지구 신봉동 56-1"
        assert len(bad) >= 19, "픽스처가 옛 단방향 가드를 통과하지 못하면 이 케이스는 공허하다"
        assert is_valid_pnu(bad) is False

    def test_구멍B_길이만_보면_통과하던_값(self):
        # 19자이지만 숫자가 아니다 — `len(pnu) == 19` 를 **통과**했다.
        bad = "413701100010467000a"
        assert len(bad) == 19, "픽스처가 옛 길이 가드를 통과하지 못하면 이 케이스는 공허하다"
        assert is_valid_pnu(bad) is False

    def test_음성대조_진짜는_통과한다(self):
        """★모두 False 를 주는 죽은 검사기와 구별한다."""
        assert is_valid_pnu("4137011000104670001") is True

    def test_구멍C_유니코드_숫자(self):
        """★파이썬 `\\d` 는 **유니코드 십진수를 포함**한다 — 전각 19자가 통과했다.

        실측: `re.compile(r"^\\d{19}$")` 가 `'１２３４５６７８９０１２３４５６７８９'` 를 통과시켜
        `sigungu_cd='１２３４５'` 가 **MOLIT 건축물대장 API 인자**로 나갔다.
        ★이 저장소는 그 함정을 **이미 알고 있었다** — `agents/engine_inputs.py:24` 의 `_pnu19` 가
        독스트링에 *"19자리 **ASCII** 숫자만"* 이라 적고 `isascii()` 로 막고 있었다.
        형제를 훑지 않고 더 약한 쪽을 SSOT 로 채택할 뻔했다(§회귀망 29).
        """
        for bad in ("１２３４５６７８９０１２３４５６７８９", "١٢٣٤٥٦٧٨٩٠١٢٣٤٥٦٧٨٩"):
            assert len(bad) == 19, "픽스처가 19자가 아니면 이 케이스는 공허하다"
            assert bad.isdigit() is True, "★`isdigit()` 은 참이다 — 그래서 `\\d` 로는 못 막는다"
            assert is_valid_pnu(bad) is False
            assert normalize_pnu(bad) is None

    def test_구멍D_판정과_소비가_같은_문자열이어야_한다(self):
        """★종전엔 `strip()` 후 판정하고 **소비처는 원본을 슬라이싱**했다.

        `' 4137011000104670001 '` → 판정 통과 · 소비 `[:5]` = `' 4137'` →
        시군구·법정동·본번·부번이 **전부 한 칸 밀린다.** **거부보다 나쁘다** —
        그럴듯한 코드로 **다른 필지를 조회**하고 조용히 틀린다.
        """
        padded = " 4137011000104670001 "
        # 판정은 **소비될 그 문자열**을 본다 → 거짓
        assert is_valid_pnu(padded) is False
        # 벗겨 쓰고 싶으면 정규화 결과를 **소비**한다
        norm = normalize_pnu(padded)
        assert norm == "4137011000104670001"
        assert norm[:5] == "41370"  # ★밀리지 않는다
        assert padded[:5] == " 4137"  # 대조군 — 원본을 자르면 밀린다

    def test_경계_양방향(self):
        """★§D-19 — 경계는 한 쌍이다. 18자·20자 **둘 다** 막는다."""
        assert is_valid_pnu("4" * 18) is False
        assert is_valid_pnu("4" * 20) is False
        assert is_valid_pnu("4" * 19) is True


class Test배선된함수를실제로태운다:
    """★재료(`is_valid_pnu`)만 태우면 **배선은 안 잠긴다.**

    적대 리뷰 실측: `building_registry_service` 의 가드를 **통째로 삭제**해도 락 7건 전부 초록이었다
    (길이검사 재도입도 없으니 수집기에도 안 걸린다). 그래서 **프로덕션 함수의 행위**를 태운다.
    """

    @staticmethod
    def _svc():
        from app.services.external_api.building_registry_service import BuildingRegistryService

        return BuildingRegistryService()

    @pytest.mark.asyncio
    async def test_오염_PNU_는_외부조회를_아예_시도하지_않는다(self, monkeypatch):
        called: list[tuple] = []

        async def _spy(*a, **k):
            called.append((a, k))
            return {"ok": True}

        svc = self._svc()
        monkeypatch.setattr(svc, "get_building_info", _spy)

        # 라이브 실측 오염값(26자) · 전각숫자 19자 · 공백패딩(소비 시 한 칸 밀림)
        for bad in (
            "store-rep-용인시 수지구 신봉동 56-1",
            "１２３４５６７８９０１２３４５６７８９",
            " 4137011000104670001 ",
        ):
            assert await svc.get_building_by_pnu(bad) is None
        assert called == [], f"오염 PNU 로 외부조회가 나갔다: {called}"

    @pytest.mark.asyncio
    async def test_음성대조_진짜_PNU_는_정확한_인자로_조회한다(self, monkeypatch):
        """★위 테스트만 두면 «항상 None 을 돌려주는» 구현도 만점이다 — 대비를 같은 실행에 둔다."""
        called: list[tuple] = []

        async def _spy(*a, **k):
            called.append(a)
            return {"ok": True}

        svc = self._svc()
        monkeypatch.setattr(svc, "get_building_info", _spy)

        assert await svc.get_building_by_pnu("4137011000104670001") == {"ok": True}
        assert called == [("41370", "11000", "0467", "0001")], (
            f"슬라이싱이 어긋났다: {called}"
        )
