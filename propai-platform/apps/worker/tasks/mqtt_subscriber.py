"""MQTT 드론 데이터 구독자.

EMQX 브로커로부터 드론 촬영 이미지를 수신하여 점검 태스크를 큐잉한다.
토픽: propai/drone/{project_id}/image
"""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# MQTT 토픽 패턴
DRONE_IMAGE_TOPIC = "propai/drone/+/image"


class MQTTDroneSubscriber:
    """paho-mqtt 기반 드론 데이터 구독자."""

    def __init__(self, broker_host: str, broker_port: int = 1883, *, username: str = "", password: str = "") -> None:
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self._client: Any = None
        self._arq_pool: Any = None

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        """브로커 연결 시 토픽 구독."""
        if rc == 0:
            logger.info("MQTT 브로커 연결 성공", host=self.broker_host)
            client.subscribe(DRONE_IMAGE_TOPIC)
            logger.info("드론 이미지 토픽 구독", topic=DRONE_IMAGE_TOPIC)
        else:
            logger.error("MQTT 브로커 연결 실패", rc=rc)

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """드론 이미지 메시지 수신 → arq 태스크 큐잉."""
        try:
            topic_parts = msg.topic.split("/")
            if len(topic_parts) < 4:
                logger.warning("잘못된 토픽 형식", topic=msg.topic)
                return

            project_id = topic_parts[2]
            payload = json.loads(msg.payload.decode("utf-8"))

            image_url = payload.get("image_url", "")
            if not image_url:
                logger.warning("이미지 URL 누락", project_id=project_id)
                return

            logger.info(
                "드론 이미지 수신",
                project_id=project_id,
                image_url=image_url[:80],
            )

            # arq 태스크 큐잉 (동기 컨텍스트에서는 큐에 직접 넣지 않고 로그만)
            # 실제 운영 시 arq pool을 통해 enqueue
            if self._arq_pool is not None:
                import asyncio

                loop = asyncio.get_event_loop()
                loop.create_task(
                    self._arq_pool.enqueue_job(
                        "inspect_drone_image",
                        project_id=project_id,
                        image_url=image_url,
                        lat=payload.get("lat", 0.0),
                        lng=payload.get("lng", 0.0),
                    ),
                )

        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("MQTT 메시지 디코딩 실패", topic=msg.topic)
        except Exception:
            logger.exception("MQTT 메시지 처리 오류")

    def start(self, arq_pool: Any = None) -> None:
        """MQTT 구독을 시작한다 (블로킹)."""
        import paho.mqtt.client as mqtt

        self._arq_pool = arq_pool
        self._client = mqtt.Client(client_id="propai-drone-subscriber")

        if self.username:
            self._client.username_pw_set(self.username, self.password)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        logger.info("MQTT 구독자 시작", host=self.broker_host, port=self.broker_port)
        self._client.connect(self.broker_host, self.broker_port, keepalive=60)
        self._client.loop_start()

    def stop(self) -> None:
        """MQTT 구독을 중지한다."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("MQTT 구독자 종료")
