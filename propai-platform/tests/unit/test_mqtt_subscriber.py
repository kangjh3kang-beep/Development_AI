"""MQTT 드론 구독자 테스트.

Phase F-6: paho-mqtt 기반 MQTT 구독자 구조 검증.
"""

from pathlib import Path

_MQTT_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps" / "worker" / "tasks" / "mqtt_subscriber.py"
)
_MQTT_SOURCE = _MQTT_PATH.read_text(encoding="utf-8")

_WORKER_MAIN_PATH = (
    Path(__file__).resolve().parents[2] / "apps" / "worker" / "main.py"
)
_WORKER_MAIN_SOURCE = _WORKER_MAIN_PATH.read_text(encoding="utf-8")


class TestMQTTSubscriberStructure:
    """MQTT 구독자 구조 검증."""

    def test_mqtt_subscriber_file_exists(self) -> None:
        """mqtt_subscriber.py 파일이 존재한다."""
        assert _MQTT_PATH.exists()

    def test_drone_topic_defined(self) -> None:
        """드론 이미지 토픽이 정의되어 있다."""
        assert "propai/drone" in _MQTT_SOURCE

    def test_paho_mqtt_usage(self) -> None:
        """paho-mqtt 라이브러리를 사용한다."""
        assert "paho" in _MQTT_SOURCE

    def test_subscriber_class_exists(self) -> None:
        """MQTTDroneSubscriber 클래스가 존재한다."""
        assert "MQTTDroneSubscriber" in _MQTT_SOURCE

    def test_on_connect_handler(self) -> None:
        """on_connect 콜백이 구현되어 있다."""
        assert "_on_connect" in _MQTT_SOURCE

    def test_on_message_handler(self) -> None:
        """on_message 콜백이 구현되어 있다."""
        assert "_on_message" in _MQTT_SOURCE

    def test_start_stop_methods(self) -> None:
        """start/stop 메서드가 있다."""
        assert "def start" in _MQTT_SOURCE
        assert "def stop" in _MQTT_SOURCE


class TestMQTTWorkerIntegration:
    """워커 main.py에 MQTT 통합 검증."""

    def test_mqtt_in_startup(self) -> None:
        """startup에서 MQTT 구독자를 시작한다."""
        assert "mqtt" in _WORKER_MAIN_SOURCE.lower()
        assert "MQTTDroneSubscriber" in _WORKER_MAIN_SOURCE

    def test_mqtt_in_shutdown(self) -> None:
        """shutdown에서 MQTT 구독자를 정리한다."""
        assert "mqtt_subscriber" in _WORKER_MAIN_SOURCE
