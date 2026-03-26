"""MQTT 드론 구독자 테스트."""

import json
from unittest.mock import MagicMock, patch

import pytest


def test_mqtt_subscriber_init():
    """구독자 초기화."""
    from apps.worker.tasks.mqtt_subscriber import MQTTDroneSubscriber

    sub = MQTTDroneSubscriber(
        broker_host="localhost",
        broker_port=1883,
        username="user",
        password="pass",
    )
    assert sub.broker_host == "localhost"
    assert sub.broker_port == 1883
    assert sub.username == "user"


def test_on_connect_success():
    """브로커 연결 성공 → 토픽 구독."""
    from apps.worker.tasks.mqtt_subscriber import DRONE_IMAGE_TOPIC, MQTTDroneSubscriber

    sub = MQTTDroneSubscriber(broker_host="localhost")
    mock_client = MagicMock()

    sub._on_connect(mock_client, None, None, 0)

    mock_client.subscribe.assert_called_once_with(DRONE_IMAGE_TOPIC)


def test_on_connect_failure():
    """브로커 연결 실패 — 구독 안 함."""
    from apps.worker.tasks.mqtt_subscriber import MQTTDroneSubscriber

    sub = MQTTDroneSubscriber(broker_host="localhost")
    mock_client = MagicMock()

    sub._on_connect(mock_client, None, None, 5)

    mock_client.subscribe.assert_not_called()


def test_on_message_valid():
    """유효한 드론 이미지 메시지 처리."""
    from apps.worker.tasks.mqtt_subscriber import MQTTDroneSubscriber

    sub = MQTTDroneSubscriber(broker_host="localhost")
    mock_client = MagicMock()

    msg = MagicMock()
    msg.topic = "propai/drone/project-123/image"
    msg.payload = json.dumps({
        "image_url": "https://minio.local/drone/image1.jpg",
        "lat": 37.5665,
        "lng": 126.9780,
    }).encode("utf-8")

    sub._on_message(mock_client, None, msg)


def test_on_message_invalid_topic():
    """잘못된 토픽 형식."""
    from apps.worker.tasks.mqtt_subscriber import MQTTDroneSubscriber

    sub = MQTTDroneSubscriber(broker_host="localhost")
    mock_client = MagicMock()

    msg = MagicMock()
    msg.topic = "propai/drone"
    msg.payload = b"{}"

    sub._on_message(mock_client, None, msg)


def test_on_message_missing_image_url():
    """이미지 URL 누락."""
    from apps.worker.tasks.mqtt_subscriber import MQTTDroneSubscriber

    sub = MQTTDroneSubscriber(broker_host="localhost")
    mock_client = MagicMock()

    msg = MagicMock()
    msg.topic = "propai/drone/project-123/image"
    msg.payload = json.dumps({"lat": 37.0}).encode("utf-8")

    sub._on_message(mock_client, None, msg)


def test_on_message_invalid_json():
    """JSON 디코딩 실패."""
    from apps.worker.tasks.mqtt_subscriber import MQTTDroneSubscriber

    sub = MQTTDroneSubscriber(broker_host="localhost")
    mock_client = MagicMock()

    msg = MagicMock()
    msg.topic = "propai/drone/project-123/image"
    msg.payload = b"not-json"

    sub._on_message(mock_client, None, msg)


def test_start_and_stop():
    """구독 시작/종료."""
    import sys

    from apps.worker.tasks.mqtt_subscriber import MQTTDroneSubscriber

    sub = MQTTDroneSubscriber(broker_host="localhost")

    mock_mqtt_client = MagicMock()
    # conftest가 sys.modules에 계층적 MagicMock 트리를 주입하므로
    # patch() 대신 직접 Client 속성을 교체한다.
    paho_client_mod = sys.modules["paho.mqtt.client"]
    original = paho_client_mod.Client
    paho_client_mod.Client = MagicMock(return_value=mock_mqtt_client)
    try:
        sub.start()
    finally:
        paho_client_mod.Client = original

    mock_mqtt_client.connect.assert_called_once()
    mock_mqtt_client.loop_start.assert_called_once()

    sub.stop()
    mock_mqtt_client.loop_stop.assert_called_once()
    mock_mqtt_client.disconnect.assert_called_once()
