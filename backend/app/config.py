from __future__ import annotations

import os

from dotenv import load_dotenv
from dataclasses import dataclass
from functools import lru_cache


load_dotenv()


def read_environment(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default)).strip()


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_environment: str
    cors_origins_text: str
    app_password: str
    session_secret: str
    naver_client_id: str
    naver_client_secret: str
    naver_commerce_client_id: str
    naver_commerce_client_secret: str
    google_sheet_id: str
    gcp_service_account_json: str
    naver_ad_customer_id: str
    naver_ad_access_license: str
    naver_ad_secret_key: str

    @property
    def cors_origins(self) -> list[str]:
        origins = [
            origin.strip().rstrip("/")
            for origin in self.cors_origins_text.split(",")
            if origin.strip()
        ]

        return origins or ["http://localhost:3000"]

    @property
    def required_api_settings_ready(self) -> bool:
        return all(
            (
                self.naver_client_id,
                self.naver_client_secret,
                self.google_sheet_id,
                self.gcp_service_account_json,
            )
        )

    @property
    def commerce_api_settings_ready(self) -> bool:
        return all(
            (
                self.naver_commerce_client_id,
                self.naver_commerce_client_secret,
            )
        )

    @property
    def keyword_api_settings_ready(self) -> bool:
        return all(
            (
                self.naver_ad_customer_id,
                self.naver_ad_access_license,
                self.naver_ad_secret_key,
            )
        )

    @property
    def authentication_ready(self) -> bool:
        return bool(
            self.app_password
            and self.session_secret
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name=read_environment(
            "APP_NAME",
            "피싱템 순위 레이더 API",
        ),
        app_environment=read_environment(
            "APP_ENVIRONMENT",
            "development",
        ),
        cors_origins_text=read_environment(
            "CORS_ORIGINS",
            "http://localhost:3000",
        ),
        app_password=read_environment("APP_PASSWORD"),
        session_secret=read_environment("SESSION_SECRET"),
        naver_client_id=read_environment("NAVER_CLIENT_ID"),
        naver_client_secret=read_environment(
            "NAVER_CLIENT_SECRET"
        ),
        naver_commerce_client_id=read_environment(
            "NAVER_COMMERCE_CLIENT_ID"
        ),
        naver_commerce_client_secret=read_environment(
            "NAVER_COMMERCE_CLIENT_SECRET"
        ),
        google_sheet_id=read_environment("GOOGLE_SHEET_ID"),
        gcp_service_account_json=read_environment(
            "GCP_SERVICE_ACCOUNT_JSON"
        ),
        naver_ad_customer_id=read_environment(
            "NAVER_AD_CUSTOMER_ID"
        ),
        naver_ad_access_license=read_environment(
            "NAVER_AD_ACCESS_LICENSE"
        ),
        naver_ad_secret_key=read_environment(
            "NAVER_AD_SECRET_KEY"
        ),
    )
