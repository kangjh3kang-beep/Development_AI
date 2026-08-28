"""다필지가 **주소 문자열 붕괴**로 단필지가 되는 것을 드러낸다.

## 왜 (2026-08-28 사용자 신고 + 라이브 재현)

프로젝트가 **77필지 · 86,755㎡** 인데 「최적 개발방식 시뮬레이션」이 **44㎡(약 13평)** 로
계산했다. 같은 페이지의 다른 절(실효용적률·적정공급면적)은 86,755㎡ 를 썼다 —
**한 화면이 1,972배 다른 두 면적으로 말했다.**

    라이브 재현: address="경기도 오산시 내삼미동", parcels 없음
      → parcel_count=1 · total_area_sqm=44.0 · pyeong=13.3 · tier=T1
        area_is_partial=False · resolved_parcel_count=1     ← **경고가 안 뜬다**

그 44㎡ 가 「도시개발사업: 총면적 44m² < 1만m² 요건 미달」 등 **19개 개발방식을 거짓
'불가'** 로 막았다. 86,755㎡ 였다면 그 판정은 뒤집힌다.

## 근본 원인

`_merge` 는 **주소 문자열**로 중복제거한다. 그 자체는 옳지만(같은 주소 = 같은 필지),
주소에 **지번이 없으면** 서로 다른 필지가 같은 문자열이 되어 통째로 붕괴한다.
그리고 `parcel_count` 는 **중복제거 후** 값이라, 응답이 *"77을 요청했는데 1을 썼다"* 를
**표현할 방법 자체가 없었다** — 그래서 기존 정직 장치(`area_is_partial`)도 발화하지 않는다
(백엔드 관점에선 «1필지 요청 → 1필지 성공» 이다).

★같은 파일이 이미 적어 둔 원칙에 **붕괴라는 두 번째 얼굴**을 더한다:
**조용한 축소가 조용한 오답을 만든다.**
"""

from __future__ import annotations

from apps.api.app.services.development.scenario_simulator import (
    DevelopmentScenarioSimulator as Sim,
)


class Test요청수를중복제거전에센다:
    def test_같은_주소가_겹치면_요청수가_사용수보다_크다(self) -> None:
        req = Sim._requested_count("A", ["A", "A", "A"])
        used = len(Sim._merge("A", ["A", "A", "A"]))
        # ★3(대표가 목록 안에 있으므로 한 번만) — 첫 판은 4 를 기대했는데, 그 4 가 바로
        #   **대표주소 이중 계수**였고 정상 다필지에 거짓 경보를 냈다(독립 리뷰 실측).
        assert req == 3, f"요청 수가 틀렸다: {req}"
        assert used == 1
        assert req > used, "붕괴를 표현할 분모가 없다"

    def test_정상_다필지는_붕괴가_없다(self) -> None:
        """★음성 대조군 — 「항상 붕괴」라고 신고하는 구현은 정상 코드를 막는다.

        ★★**프로덕션이 실제로 보내는 형태**로 태운다 — 대표주소가 `parcels` **선두에 들어 있다**
          (`buildAnalysisParcelAddrs`: `[target, ...]`). 첫 판은 `("A", ["B","C"])` 였는데
          그건 프로덕션이 보내지 않는 형태라, `address` 이중 계수를 **원리적으로 못 잡았다**
          — 독립 리뷰가 이 픽스처로 **정상 다필지 전부에 거짓 붕괴 경보**를 실증했다.
        """
        req = Sim._requested_count("A", ["A", "B", "C"])   # ← address ∈ parcels
        used = len(Sim._merge("A", ["A", "B", "C"]))
        assert req == used == 3, f"정상 케이스에서 붕괴로 오신고: 요청 {req} vs 사용 {used}"

    def test_대표주소가_목록에_있어도_한_번만_센다(self) -> None:
        """★같은 뿌리의 다른 얼굴 — 대표가 목록 **밖**이면 정상적으로 +1 이어야 한다."""
        assert Sim._requested_count("A", ["A", "B"]) == 2   # 안에 있음 → 2
        assert Sim._requested_count("A", ["B", "C"]) == 3   # 밖에 있음 → 3

    def test_dict_행도_센다(self) -> None:
        """호출자가 `ParcelsIn` dict 를 보내는 경로(면적 포함)도 같은 분모를 만든다."""
        rows = [{"address": "A", "area_sqm": 100}, {"address": "A", "area_sqm": 200}]
        assert Sim._requested_count("A", rows) == 2   # 대표는 목록 안 → 이중 계수 금지
        assert len(Sim._merge("A", rows)) == 1

    def test_주소_없는_행은_세지_않는다(self) -> None:
        """빈 주소·비문자 타입은 필지가 아니다(무날조) — `_merge` 와 같은 정책."""
        assert Sim._requested_count("A", [{"area_sqm": 100}, "", "   ", 42]) == 1


class Test붕괴가응답에드러난다:
    """★계약 락 — 값이 실리는지를 본다(키가 있는지가 아니라).

    ctx 조립은 비동기 I/O 를 타므로, 여기서는 **ctx 를 만드는 산식**을 그대로 재현해
    두 모집단이 **다른 값**을 내는지 단언한다(붕괴 有/無).
    """

    @staticmethod
    def _flags(requested: int, used: int, unresolved: list) -> dict:
        # `simulate` 가 ctx 에 싣는 것과 동일한 산식.
        return {
            "requested_parcel_count": requested,
            "collapsed_parcel_count": max(0, requested - used),
            "area_is_partial": bool(unresolved) or requested > used,
        }

    def test_붕괴하면_부분집계로_표시된다(self) -> None:
        f = self._flags(requested=77, used=1, unresolved=[])
        assert f["collapsed_parcel_count"] == 76
        assert f["area_is_partial"] is True, (
            "77필지가 1필지로 붕괴했는데 부분집계로 표시되지 않는다 — 44㎡ 사고의 그 자리"
        )

    def test_붕괴가_없으면_종전과_같다(self) -> None:
        """★무회귀 — 조회 실패가 없으면 부분집계가 아니어야 한다(과잉 경고 금지)."""
        f = self._flags(requested=3, used=3, unresolved=[])
        assert f["collapsed_parcel_count"] == 0
        assert f["area_is_partial"] is False

    def test_조회실패_경로는_종전대로_살아있다(self) -> None:
        """★두 경로가 **각각** 부분집계를 만든다 — 하나로 뭉치면 나머지가 조용해진다."""
        붕괴 = self._flags(requested=77, used=1, unresolved=[])
        실패 = self._flags(requested=2, used=2, unresolved=[{"address": "B"}])
        assert 붕괴["area_is_partial"] and 실패["area_is_partial"]
        # 그러나 **사유는 구별된다** — 화면이 다른 말을 해야 하기 때문이다.
        assert 붕괴["collapsed_parcel_count"] > 0
        assert 실패["collapsed_parcel_count"] == 0


class Test배선:
    """★`simulate` **함수 안에서** 실제로 그렇게 배선돼 있는가.

    2026-08-28 실측: 위 테스트들이 `_requested_count` 를 **직접** 부르고 ctx 산식을
    **재구현**해서, `requested_count = len(addrs)` 로 되돌리는 변이가 **SURVIVED** 했다.
    그러면 분모가 중복제거 **후** 값이 되어 **붕괴가 영원히 0으로 보인다** — 고친 것이 아니다.
    (저장소 전례 미러: `test_realtx_report_service.py::Test배선`)
    """

    @staticmethod
    def _simulate_fn():
        import ast
        import inspect

        from apps.api.app.services.development import scenario_simulator as mod

        tree = ast.parse(inspect.getsource(mod))
        return ast, next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == "simulate"
        )

    def test_요청수는_전용_계수기에서_온다(self) -> None:
        ast, fn = self._simulate_fn()
        assigns = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "requested_count" for t in n.targets)
        ]
        assert assigns, "simulate 가 requested_count 를 만들지 않는다 — 분모가 없다"
        assert all(
            isinstance(a.value, ast.Call)
            and isinstance(a.value.func, ast.Attribute)
            and a.value.func.attr == "_requested_count"
            for a in assigns
        ), (
            "requested_count 가 `_requested_count` 가 아닌 것에서 온다 — "
            "`len(addrs)` 로 되돌리면 중복제거 **후** 값이라 붕괴가 영원히 0이 된다"
        )

    def test_부분집계가_붕괴_경로를_읽는다(self) -> None:
        """★F4 — 44㎡ 사고에서 **실제로 침묵한 필드**는 `area_is_partial` 이다.

        첫 판은 `requested_parcel_count`·`collapsed_parcel_count` 두 키만 봤고,
        `area_is_partial` 을 `bool(unresolved)` 로 되돌리는 변이가 **SURVIVED** 했다
        (독립 리뷰 실측). 그러면 붕괴해도 화면이 **다시 침묵한다** — 고친 것이 아니다.
        """
        ast, fn = self._simulate_fn()
        pairs: dict[str, object] = {}
        for n in ast.walk(fn):
            if isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values, strict=False):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        pairs.setdefault(k.value, v)
        assert "area_is_partial" in pairs, "ctx 에 area_is_partial 이 없다"
        names = {n.id for n in ast.walk(pairs["area_is_partial"]) if isinstance(n, ast.Name)}
        assert "unresolved" in names, "조회실패 경로가 빠졌다(종전 회귀)"
        assert "requested_count" in names, (
            "붕괴 경로가 빠졌다 — 77필지가 1로 줄어도 부분집계로 표시되지 않는다"
        )

    def test_ctx_가_요청수와_붕괴수를_싣는다(self) -> None:
        """★키가 있는지가 아니라 **값이 실리는지** — 리터럴 0 을 박으면 실패해야 한다."""
        ast, fn = self._simulate_fn()
        pairs: dict[str, object] = {}
        for n in ast.walk(fn):
            if isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values, strict=False):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        pairs.setdefault(k.value, v)
        for key in ("requested_parcel_count", "collapsed_parcel_count"):
            assert key in pairs, f"ctx 에 {key} 가 없다"
            assert not isinstance(pairs[key], ast.Constant), (
                f"{key} 가 상수다 — 붕괴를 재지 않고 값을 지어낸다"
            )
        # 붕괴수는 요청수와 사용수의 **차**여야 한다(둘 중 하나만 읽으면 항상 0/항상 양수다).
        names = {
            n.id for n in ast.walk(pairs["collapsed_parcel_count"]) if isinstance(n, ast.Name)
        }
        assert "requested_count" in names and "addrs" in names, (
            f"collapsed_parcel_count 가 요청수·사용수를 둘 다 읽지 않는다: {sorted(names)}"
        )
