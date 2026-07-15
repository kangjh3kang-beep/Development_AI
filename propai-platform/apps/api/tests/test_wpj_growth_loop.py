"""WP-J 게이트 — P16 성장루프 완결.

검증 대상(무DB·무네트워크 순수/인메모리 — CI py3.12 그대로 통과):
  1) 성장루프 표면 11/11 배선(SSOT 매니페스트 정적 증거) + 미배선 감지(disjoint 재발 가드).
  2) LangSmith 토글 — 기본 OFF·LANGSMITH_TRACING/LANGCHAIN_TRACING_V2 양쪽 인정·키 부재 graceful·
     OFF 시 env 무부작용(무회귀).
  3) asset_rights 배치 조회(N+1 제거)·시딩 upsert 왕복·default-deny·학습게이트(build_dataset_jsonl).
  4) content_inspection 텍스트 확장자 압축비 예외(aihub 고압축 텍스트 시드 통과) + bomb 여전 차단.

무회귀: 기존 content_inspection SEC 스위트·learning_loop·WP-I outbox 는 별도 파일에서 계속 돈다.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import types
import zipfile

import pytest

# apps/api 를 import 경로에 추가(tests/conftest.py 규약과 동일).
_API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)


# ════════════════════════════════════════════════════════════════════════════
# 공용 헬퍼 — 고압축비 zip 엔트리 제작
# ════════════════════════════════════════════════════════════════════════════
def _high_ratio_payload(pad_mb: int = 1) -> bytes:
    """압축비가 큰(>100x) 바이트: 비압축 6KB(랜덤) + 대량 반복(A). 압축크기≈6KB(>ratio_min 4096),
    전개크기≈pad_mb MB → 압축비 ≈ 170x/MB. 랜덤부가 있어 compress_size 가 4096 이상이 되어
    압축비 검사가 '작은 엔트리 예외'로 건너뛰어지지 않는다(실제 ratio 경로를 탄다)."""
    return os.urandom(6000) + (b"A" * (pad_mb * 1024 * 1024))


def _zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    """(이름, 데이터) 목록을 DEFLATE zip 바이트로."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


# ════════════════════════════════════════════════════════════════════════════
# Goal 1 — 성장루프 표면 SSOT 매니페스트 11/11
# ════════════════════════════════════════════════════════════════════════════
from app.services.growth.growth_surfaces import (  # noqa: E402
    GROWTH_LOOP_SURFACES,
    GrowthSurface,
    check_surface,
    unwired_surfaces,
    verify_surface_wiring,
)


def test_manifest_has_exactly_11_surfaces():
    assert len(GROWTH_LOOP_SURFACES) == 11
    keys = [s.key for s in GROWTH_LOOP_SURFACES]
    assert len(set(keys)) == 11  # 키 중복 없음
    # PR#199 폐합 정본 표면이 전부 포함.
    expected = {
        "cost_overview", "avm", "pricing_suggest", "permit_ai", "regulation",
        "desk_appraisal", "pipeline_run", "market_report", "esg_lca",
        "digital_twin", "investor_report",
    }
    assert set(keys) == expected


def test_all_surfaces_wired_11_of_11():
    """실증: 11개 표면 전부 (원장 write + ledger_hash 노출 + analysis_type 일치) 배선."""
    res = verify_surface_wiring()
    assert len(res) == 11
    not_wired = [k for k, v in res.items() if not v["wired"]]
    assert not_wired == [], f"미배선 표면: {not_wired} — 상세 {res}"


def test_unwired_surfaces_is_empty():
    assert unwired_surfaces() == []


@pytest.mark.parametrize("surface", GROWTH_LOOP_SURFACES, ids=lambda s: s.key)
def test_each_surface_individually_wired(surface: GrowthSurface):
    chk = check_surface(surface)
    assert chk["exists"], f"{surface.key} 소스 부재: {surface.source}"
    assert chk["has_write"], f"{surface.key} 원장 write 배선 없음"
    assert chk["has_hash"], f"{surface.key} ledger_hash 노출 없음"
    assert chk["has_type"], f"{surface.key} analysis_type 불일치"
    assert chk["wired"]


def test_check_surface_flags_missing_wiring(tmp_path):
    """가드 실효성: 배선이 빠진 소스는 wired=False 로 잡힌다(disjoint 재발 즉시 실패)."""
    # write/hash 마커가 없는 더미 소스.
    (tmp_path / "dummy.py").write_text("def handler():\n    return {}\n", encoding="utf-8")
    surf = GrowthSurface("dummy", "dummy.py", "POST /dummy", "dummy")
    chk = check_surface(surf, base=tmp_path)
    assert chk["exists"] and not chk["has_write"] and not chk["has_hash"]
    assert chk["wired"] is False

    # 부재 파일도 미배선.
    surf_missing = GrowthSurface("gone", "nope.py", "POST /gone", "gone")
    assert check_surface(surf_missing, base=tmp_path)["wired"] is False


# ════════════════════════════════════════════════════════════════════════════
# Goal 2 — LangSmith 토글(기본 OFF·양쪽 env·키 부재 graceful·OFF 무부작용)
# ════════════════════════════════════════════════════════════════════════════
_LS_ENV_KEYS = (
    "LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY",
    "LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT", "LANGSMITH_PROJECT", "LANGCHAIN_PROJECT",
    "LANGSMITH_WORKSPACE_ID", "LANGSMITH_SAMPLE_RATE", "LANGCHAIN_TRACING_SAMPLING_RATE",
)


class _FakeSettings:
    def __init__(self, tracing=False, endpoint="https://api.smith.langchain.com",
                 project="propai-test", workspace_id=""):
        self.langsmith_tracing = tracing
        self.langsmith_endpoint = endpoint
        self.langsmith_project = project
        self.langsmith_workspace_id = workspace_id


@contextlib.contextmanager
def _fake_config(**settings_kw):
    """apps.api.config.get_settings 를 페이크로 교체(실 pydantic config 미로딩). 종료 시 복원."""
    saved = sys.modules.get("apps.api.config")
    cfg = types.ModuleType("apps.api.config")
    obj = _FakeSettings(**settings_kw)
    setattr(cfg, "get_settings", lambda: obj)  # noqa: B010 — 페이크 모듈 동적 속성
    sys.modules["apps.api.config"] = cfg
    try:
        yield
    finally:
        if saved is None:
            sys.modules.pop("apps.api.config", None)
        else:
            sys.modules["apps.api.config"] = saved


def _load_obs():
    """observability.py 를 고유 이름으로 신선 로드(모듈 전역 _LANGSMITH_ENABLED 격리)."""
    path = os.path.join(_API_DIR, "core", "observability.py")
    spec = importlib.util.spec_from_file_location("obs_wpj_test", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def clean_ls_env():
    """LangSmith/LangChain 관련 env 스냅샷·복원(테스트 간 누출 차단)."""
    saved = {k: os.environ.get(k) for k in _LS_ENV_KEYS}
    for k in _LS_ENV_KEYS:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_truthy_values(clean_ls_env):
    obs = _load_obs()
    assert obs._truthy("true") and obs._truthy("1") and obs._truthy("YES") and obs._truthy("on")
    assert not obs._truthy("0") and not obs._truthy("false") and not obs._truthy(None) and not obs._truthy("")


def test_default_off_disabled(clean_ls_env):
    """기본 OFF: env 없음 + settings.tracing=False → 비활성·부작용 없음."""
    obs = _load_obs()
    with _fake_config(tracing=False):
        res = obs.init_langsmith()
    assert res["enabled"] is False
    assert obs.langsmith_enabled() is False
    # OFF 무부작용: LangChain 표준 env 를 켜지 않는다(무회귀).
    assert os.environ.get("LANGCHAIN_TRACING_V2") != "true"


def test_langsmith_tracing_on_but_no_key_graceful(clean_ls_env):
    """LANGSMITH_TRACING=true 인데 키 부재 → graceful 비활성(예외 없음)."""
    obs = _load_obs()
    os.environ["LANGSMITH_TRACING"] = "true"
    with _fake_config(tracing=False):
        res = obs.init_langsmith()
    assert res["enabled"] is False
    assert res["has_key"] is False
    assert obs.langsmith_enabled() is False


def test_langchain_tracing_v2_on_but_no_key_graceful(clean_ls_env):
    """★신규 토글: LANGCHAIN_TRACING_V2=true 도 활성 의도로 인정하되, 키 부재면 graceful 비활성."""
    obs = _load_obs()
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    with _fake_config(tracing=False):
        res = obs.init_langsmith()
    # tracing 의도는 True 로 인식(신규 토글 경로), 키가 없어 활성화만 보류.
    assert res["tracing"] is True
    assert res["enabled"] is False and res["has_key"] is False


def test_enabled_with_settings_tracing_and_key(clean_ls_env):
    """settings.tracing=True + 키 → 활성·LangChain 표준 env 설정."""
    obs = _load_obs()
    os.environ["LANGSMITH_API_KEY"] = "lsv2_sk_dummy"
    with _fake_config(tracing=True, project="propai-prod"):
        res = obs.init_langsmith()
    assert res["enabled"] is True
    assert obs.langsmith_enabled() is True
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    assert os.environ.get("LANGCHAIN_API_KEY") == "lsv2_sk_dummy"
    assert os.environ.get("LANGCHAIN_PROJECT") == "propai-prod"


def test_langchain_tracing_v2_env_enables_with_key(clean_ls_env):
    """★신규 토글 경로: LANGCHAIN_TRACING_V2=true + 키 → 활성(LANGSMITH_TRACING 없이도)."""
    obs = _load_obs()
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = "lsv2_sk_dummy2"
    with _fake_config(tracing=False):
        res = obs.init_langsmith()
    assert res["enabled"] is True
    assert obs.langsmith_enabled() is True
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"


def test_off_has_no_env_side_effect(clean_ls_env):
    """OFF 시 LANGCHAIN_* env 를 일절 건드리지 않음(_invoke 자동추적 무영향 = 무회귀)."""
    obs = _load_obs()
    with _fake_config(tracing=False):
        obs.init_langsmith()
    for k in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_ENDPOINT", "LANGCHAIN_PROJECT"):
        assert os.environ.get(k) is None


# ════════════════════════════════════════════════════════════════════════════
# Goal 3 — asset_rights 순수 계약 + 배치 조회/시딩 + 학습게이트
# ════════════════════════════════════════════════════════════════════════════
from app.services.growth import learning_loop as ll  # noqa: E402
from app.services.security import asset_rights as ar  # noqa: E402


def test_resolve_default_deny_unknown():
    r = ar.resolve_asset_right("hash-x")
    assert r.scope == "unknown"
    assert r.train_allowed is False and r.export_allowed is False
    assert ar.is_train_allowed(None) is False  # 미등록=불명=금지


def test_resolve_scope_and_explicit_false_zero_falsy():
    assert ar.resolve_asset_right("h", scope="train_ok").train_allowed is True
    assert ar.resolve_asset_right("h", scope="public").export_allowed is True
    # ★0-falsy: 명시 False 는 "거부"로 유효(불명으로 오인해 scope 유추로 덮지 않는다).
    r = ar.resolve_asset_right("h", scope="train_ok", train_allowed=False)
    assert r.train_allowed is False


def test_keep_train_allowed_filters():
    rights = {
        ("a", "t"): ar.resolve_asset_right("a", scope="train_ok"),
        ("b", "t"): ar.resolve_asset_right("b"),  # unknown → 제외
    }
    rows = [("in", "out", ("a", "t")), ("in", "out", ("b", "t")), ("in", "out", ("c", "t"))]
    kept, excluded = ar.keep_train_allowed(rows, rights, key_index=2)
    assert len(kept) == 1 and kept[0][2] == ("a", "t")
    assert excluded == 2  # b(불명)+c(미등록)


# ── 인메모리 fake async DB(asset_rights + learning_examples SQL 모사) ──────────
class _Result:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def all(self):
        return self._rows

    def fetchall(self):
        return self._rows

    def first(self):
        return self._one

    def fetchone(self):
        return self._one


class _FakeDB:
    """asset_rights upsert/get(단건·배치) + learning_examples SELECT 를 모사."""

    def __init__(self, learning_rows=None):
        self.rights: dict[tuple, dict] = {}  # (asset_key, tenant) -> row dict
        self.learning_rows = learning_rows or []
        self.commits = 0
        self.rollbacks = 0
        self.rights_selects = 0  # asset_rights SELECT 실행 횟수(N+1 제거 증명용)

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(getattr(statement, "text", statement))
        p = params or {}
        if "CREATE TABLE" in sql or "CREATE INDEX" in sql:
            return _Result()
        if sql.strip().startswith("INSERT INTO asset_rights"):
            self.rights[(p["k"], p["t"])] = {
                "scope": p["sc"], "train": p["tr"], "export": p["ex"],
                "source": p["src"], "note": p["note"], "meta": p["meta"],
            }
            return _Result()
        if "FROM asset_rights" in sql and "IN (" in sql:  # 배치 조회
            self.rights_selects += 1
            n = sum(1 for kk in p if kk.startswith("k") and kk[1:].isdigit())
            out = []
            for i in range(n):
                key = (p[f"k{i}"], p[f"t{i}"])
                r = self.rights.get(key)
                if r is not None:
                    out.append((key[0], key[1], r["scope"], r["train"],
                                r["export"], r["source"], r["note"], {}))
            return _Result(rows=out)
        if "FROM asset_rights" in sql:  # 단건 조회
            self.rights_selects += 1
            r = self.rights.get((p["k"], p["t"]))
            if r is None:
                return _Result(one=None)
            return _Result(one=(r["scope"], r["train"], r["export"],
                                r["source"], r["note"], {}))
        if "FROM learning_examples" in sql:
            return _Result(rows=self.learning_rows)
        return _Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture(autouse=True)
def _schema_ready():
    """ensure_schema 를 no-op(준비됨)로 고정 — fake DB 에서 DDL 왕복 불필요·복원."""
    saved = ar._SCHEMA_READY
    ar._SCHEMA_READY = True
    yield
    ar._SCHEMA_READY = saved


async def test_upsert_batch_and_get_batch_roundtrip():
    """배치 upsert 1 트랜잭션 + 배치 조회 1 질의 왕복."""
    db = _FakeDB()
    rights = [
        ar.AssetRight(asset_key="h1", scope="train_ok", train_allowed=True, source="aihub-license"),
        ar.AssetRight(asset_key="h2", scope="train_ok", train_allowed=True, source="aihub-license"),
    ]
    n = await ar.upsert_asset_rights_batch(db, rights)
    assert n == 2
    assert db.commits == 1  # ★배치=단일 커밋(행마다 커밋 아님)

    got = await ar.get_asset_rights_batch(db, [("h1", None), ("h2", None), ("h3", None)])
    assert db.rights_selects == 1  # ★N+1 제거: 3키를 1질의로
    assert got[("h1", None)].train_allowed is True
    assert got[("h2", None)].train_allowed is True
    # 미등록 h3 → default-deny(항상 값 반환·train False).
    assert got[("h3", None)].train_allowed is False


async def test_get_batch_preserves_original_tenant_key():
    """반환 dict 키는 입력 원본 (asset_key, tenant) 그대로(정규화 전)."""
    db = _FakeDB()
    await ar.upsert_asset_rights_batch(
        db, [ar.AssetRight(asset_key="h", tenant_id="acme", scope="train_ok", train_allowed=True)]
    )
    got = await ar.get_asset_rights_batch(db, [("h", "acme")])
    assert ("h", "acme") in got and got[("h", "acme")].train_allowed is True


async def test_get_batch_empty_no_query():
    db = _FakeDB()
    got = await ar.get_asset_rights_batch(db, [])
    assert got == {} and db.rights_selects == 0


async def test_aihub_style_seed_roundtrip():
    """시딩 의미론: aihub-license 소스 → train_allowed 채움 → 이후 조회로 학습 허용 확인."""
    db = _FakeDB()
    seeded = [
        ar.AssetRight(asset_key=f"dwg-{i}", scope="train_ok", train_allowed=True,
                      export_allowed=False, source="aihub-license", note="AI Hub 시드")
        for i in range(3)
    ]
    assert await ar.upsert_asset_rights_batch(db, seeded) == 3
    got = await ar.get_asset_rights_batch(db, [(f"dwg-{i}", None) for i in range(3)])
    assert all(got[(f"dwg-{i}", None)].train_allowed for i in range(3))
    assert all(not got[(f"dwg-{i}", None)].export_allowed for i in range(3))  # 내보내기는 여전히 금지


async def test_build_dataset_enforce_false_includes_all():
    """게이트 OFF(기본): 권리 무관하게 전 행 포함·rights 질의 없음(무회귀)."""
    rows = [("in1", "out1", "hh1", "t"), ("in2", "out2", "hh2", "t")]
    db = _FakeDB(learning_rows=rows)
    res = await ll.build_dataset_jsonl(db, enforce_asset_rights=False)
    assert res["count"] == 2
    assert res["rights_enforced"] is False
    assert res["excluded_no_rights"] == 0
    assert db.rights_selects == 0  # 권리 조회 자체를 안 함


async def test_build_dataset_enforce_true_gate_single_batch_query():
    """게이트 ON: train_allowed 자산만 통과·미등록 제외·권리조회는 배치 1질의(N+1 제거 실증)."""
    rows = [
        ("in1", "out1", "hh1", "t"),  # 등록·train_ok → 포함
        ("in2", "out2", "hh2", "t"),  # 미등록 → 제외
        ("in3", "out3", "hh3", "t"),  # 등록·train False(명시거부) → 제외
    ]
    db = _FakeDB(learning_rows=rows)
    await ar.upsert_asset_rights_batch(db, [
        ar.AssetRight(asset_key="hh1", tenant_id="t", scope="train_ok", train_allowed=True),
        ar.AssetRight(asset_key="hh3", tenant_id="t", scope="internal_only", train_allowed=False),
    ])
    db.rights_selects = 0  # upsert 후 카운터 리셋(조회만 계측)
    res = await ll.build_dataset_jsonl(db, enforce_asset_rights=True)
    assert res["rights_enforced"] is True
    assert res["count"] == 1  # hh1 만 통과
    assert res["excluded_no_rights"] == 2  # hh2(미등록)+hh3(명시거부)
    assert db.rights_selects == 1  # ★3행 권리를 1질의로(행마다 조회 아님)


# ════════════════════════════════════════════════════════════════════════════
# Goal 4 — content_inspection 텍스트 확장자 압축비 예외(+ bomb 여전 차단)
# ════════════════════════════════════════════════════════════════════════════
from app.services.security.content_inspection import (  # noqa: E402
    TEXT_RATIO_EXEMPT_EXTS,
    ArchiveLimits,
    inspect_archive,
    safe_extract_archive,
)


def test_text_exempt_exts_contains_expected():
    for ext in ("dxf", "json", "csv", "txt"):
        assert ext in TEXT_RATIO_EXEMPT_EXTS


def _assert_ratio_path_active(zip_bytes: bytes, entry: str):
    """구성 검증: 해당 엔트리의 compress_size 가 ratio_min(4096) 이상이어야 압축비 검사가
    '작은 엔트리 예외'로 건너뛰어지지 않고 실제 ratio 경로를 탄다(테스트 유의미성 보장)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zi = zf.getinfo(entry)
        assert zi.compress_size >= 4096
        assert zi.file_size / max(zi.compress_size, 1) > 100  # 실제 고압축비


def test_text_ext_high_ratio_exempt_inspect_archive():
    """★핵심: 고압축비 DXF(텍스트) 엔트리는 압축비 검사 예외 → 통과(aihub 시드 유실 봉합)."""
    data = _high_ratio_payload(pad_mb=1)
    zb = _zip_bytes([("model.dxf", data)])
    _assert_ratio_path_active(zb, "model.dxf")
    limits = ArchiveLimits(max_ratio=100)  # 총량 상한은 기본 500MB(> 1MB) 유지
    res = inspect_archive(zb, limits)
    assert res.allowed, f"텍스트 확장자가 압축비로 오거부됨: {res.code}/{res.reason}"


def test_binary_high_ratio_still_bomb_inspect_archive():
    """동일 데이터라도 비-텍스트(.bin) 확장자는 압축비 검사 적용 → 여전히 archive_bomb 차단."""
    data = _high_ratio_payload(pad_mb=1)
    zb = _zip_bytes([("payload.bin", data)])
    _assert_ratio_path_active(zb, "payload.bin")
    res = inspect_archive(zb, ArchiveLimits(max_ratio=100))
    assert not res.allowed and res.code == "archive_bomb"


def test_text_ext_total_cap_still_blocks():
    """텍스트 예외라도 **절대 전개 총량 상한**은 유지 — 텍스트 위장 압축폭탄도 총량으로 차단."""
    data = _high_ratio_payload(pad_mb=2)  # 전개 ~2MB
    zb = _zip_bytes([("huge.dxf", data)])
    # 총량 상한을 512KB 로 낮추면, 텍스트라도 전개총량 초과로 bomb.
    res = inspect_archive(zb, ArchiveLimits(max_ratio=100, max_total_uncompressed=512 * 1024))
    assert not res.allowed and res.code == "archive_bomb"


def test_safe_extract_text_ext_exempt(tmp_path):
    """safe_extract_archive 도 동일: 고압축비 CSV(텍스트) 추출 통과(경로별 전역 일관)."""
    data = _high_ratio_payload(pad_mb=1)
    zb = _zip_bytes([("rows.csv", data)])
    res = safe_extract_archive(zb, tmp_path, limits=ArchiveLimits(max_ratio=100))
    assert res.ok, f"텍스트 확장자 추출 오거부: {res.code}/{res.reason}"
    assert (tmp_path / "rows.csv").exists()


def test_safe_extract_binary_bomb_blocked(tmp_path):
    """safe_extract_archive: 비-텍스트 고압축비는 여전히 bomb 차단·부분추출물 정리."""
    data = _high_ratio_payload(pad_mb=1)
    zb = _zip_bytes([("payload.bin", data)])
    res = safe_extract_archive(zb, tmp_path, limits=ArchiveLimits(max_ratio=100))
    assert not res.ok and res.code == "archive_bomb"
    assert not (tmp_path / "payload.bin").exists()  # 거부 시 미기록


def test_normal_zip_fp_zero():
    """무회귀: 정상 소형 zip 은 FP 0 으로 통과(예외/오거부 없음)."""
    zb = _zip_bytes([("readme.txt", b"hello world\n" * 10), ("a.json", b"{\"k\": 1}")])
    assert inspect_archive(zb).allowed
