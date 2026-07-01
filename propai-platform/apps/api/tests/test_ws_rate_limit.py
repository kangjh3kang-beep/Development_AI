"""P2-14: WebSocket 레이트리미터 — /analyze/ws 무제한 연결·고비용 실행 차단(순수 로직).

slowapi 는 WS 미지원이라 전용 in-memory 리미터(WsRateLimiter)를 검증한다:
① IP당 동시 연결 상한 ② IP당 분당 연결시도 상한(슬라이딩 윈도) ③ 테넌트당 분당 실행 상한.
시계 주입(now)으로 결정적 테스트.
"""
from apps.api.rate_limit import WsRateLimiter


def test_concurrent_cap_per_ip():
    rl = WsRateLimiter(max_concurrent_per_ip=2, attempts_per_minute=100,
                       runs_per_minute_per_tenant=100)
    assert rl.try_connect("1.1.1.1") is True
    assert rl.try_connect("1.1.1.1") is True
    assert rl.try_connect("1.1.1.1") is False      # 3번째 동시 연결 거부
    assert rl.try_connect("2.2.2.2") is True       # 다른 IP 독립
    rl.release("1.1.1.1")
    assert rl.try_connect("1.1.1.1") is True       # 해제 후 재허용


def test_attempt_window_per_ip():
    t = [0.0]
    rl = WsRateLimiter(max_concurrent_per_ip=100, attempts_per_minute=3,
                       runs_per_minute_per_tenant=100, now=lambda: t[0])
    for _ in range(3):
        assert rl.try_connect("ip") is True
        rl.release("ip")
    assert rl.try_connect("ip") is False           # 윈도 내 4번째 시도 거부
    t[0] = 61.0
    assert rl.try_connect("ip") is True            # 윈도 경과 후 허용


def test_run_budget_per_tenant():
    t = [0.0]
    rl = WsRateLimiter(runs_per_minute_per_tenant=2, now=lambda: t[0])
    assert rl.try_run("t1") is True
    assert rl.try_run("t1") is True
    assert rl.try_run("t1") is False               # 분당 3번째 실행 거부(LLM 비용 보호)
    assert rl.try_run("t2") is True                # 테넌트 독립
    t[0] = 61.0
    assert rl.try_run("t1") is True                # 윈도 경과 후 허용


def test_release_unknown_ip_is_safe():
    rl = WsRateLimiter()
    rl.release("nope")                             # 미연결 해제 무해(음수 방지)
    assert rl.try_connect("nope") is True


def test_denied_connect_does_not_consume_slot():
    rl = WsRateLimiter(max_concurrent_per_ip=1, attempts_per_minute=100,
                       runs_per_minute_per_tenant=100)
    assert rl.try_connect("ip") is True
    assert rl.try_connect("ip") is False           # 거부
    rl.release("ip")                               # 첫 연결만 해제
    assert rl.try_connect("ip") is True            # 거부된 시도가 슬롯을 소모하지 않았음
