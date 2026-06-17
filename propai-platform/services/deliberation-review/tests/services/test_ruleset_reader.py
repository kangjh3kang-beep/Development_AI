"""AT-1/AT-6 — 미수집 관할 degraded(비차단)+ETA, 소비측 미러 라이브 트리거 불가.

+ 자기수렴 감사 1회차: 미러 immutability + 공급 비동기 비차단 타이밍.
"""
import time

from app.consume.ruleset_reader import RulesetReader
from app.contracts.mirror import MirrorSnapshot
from app.supply.mirror.mirror_store import MirrorStore

JURISDICTION_NEW = "9999999999"
JURISDICTION_PROVISIONED = "1111011111"


def _provisioned_store() -> MirrorStore:
    store = MirrorStore()
    store.put(MirrorSnapshot(
        snapshot_id="snap-1", jurisdiction=JURISDICTION_PROVISIONED,
        rules=[{"ref": "art-119"}], active_candidate_ids=["c1"]))
    return store


def test_unprovisioned_jurisdiction_degrades_not_block():
    reader = RulesetReader(store=MirrorStore(), enqueue=lambda job: None)
    r = reader.load(JURISDICTION_NEW)
    assert r.degraded is True
    assert r.eta is not None
    assert r.blocked is False


def test_consumer_cannot_trigger_live_fetch(spy_network):
    reader = RulesetReader(store=_provisioned_store(), enqueue=lambda job: None)
    loaded = reader.load(JURISDICTION_PROVISIONED)
    assert loaded.degraded is False
    assert loaded.blocked is False
    assert spy_network.live_calls == 0  # 소비측 라이브 호출 0


def test_mirror_immutable_for_consumer():
    store = _provisioned_store()
    reader = RulesetReader(store=store, enqueue=lambda job: None)
    loaded = reader.load(JURISDICTION_PROVISIONED)
    # 소비자가 받은 룰셋을 변형해도 store 정본은 불변.
    loaded.snapshot.rules.append({"ref": "injected"})
    assert store.get(JURISDICTION_PROVISIONED).rules == [{"ref": "art-119"}]


def test_supply_async_does_not_block_consumer():
    jobs = []
    reader = RulesetReader(store=MirrorStore(), enqueue=jobs.append)
    t0 = time.perf_counter()
    r = reader.load(JURISDICTION_NEW)
    elapsed = time.perf_counter() - t0
    assert r.degraded is True
    assert len(jobs) == 1 and jobs[0].status == "ENQUEUED"  # 동기 수집 미수행, 큐잉만
    assert elapsed < 0.1  # 즉시 반환(공급 비동기가 소비 지연 미유발)
