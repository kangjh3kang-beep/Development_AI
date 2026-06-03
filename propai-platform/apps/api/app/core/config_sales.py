"""v62 sales 전용 설정(서브도메인/외부연계 키). 미설정 시 해당 기능 graceful skip."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class SalesSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sales_subdomain_base: str = "sales.propai.kr"
    desk_subdomain_base: str = "desk.propai.kr"
    redis_stream_prefix: str = "sales"
    fcm_credentials_json: str | None = None
    kakao_biz_key: str | None = None
    kakao_sender_key: str | None = None
    clova_ocr_url: str | None = None
    clova_ocr_secret: str | None = None
    default_withholding_rate: float = 0.033


sales_settings = SalesSettings()
