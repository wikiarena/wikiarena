from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

GRAPH_METADATA_PATH_ENV_VAR = "WIKIARENA_GRAPH_METADATA_PATH"
SNAPSHOT_ID_ENV_VAR = "WIKIARENA_SNAPSHOT_ID"
SERVICE_VERSION_ENV_VAR = "WIKIARENA_SERVICE_VERSION"
CORS_ORIGINS_ENV_VAR = "WIKIARENA_SERVER_CORS_ORIGINS"
HOST_ENV_VAR = "WIKIARENA_SERVER_HOST"
PORT_ENV_VAR = "WIKIARENA_SERVER_PORT"
ARTIFACT_DIR_ENV_VAR = "WIKIARENA_ARTIFACT_DIR"

DEFAULT_CORS_ORIGINS = (
    "https://wikiarena.org",
    "https://www.wikiarena.org",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


@dataclass(frozen=True)
class ServerConfig:
    graph_path: Path | None = None
    graph_metadata_path: Path | None = None
    snapshot_id: str | None = None
    service_version: str = "0.0.1"
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    host: str = "0.0.0.0"
    port: int = 8000
    artifact_dir: Path = Path("artifacts")

    @classmethod
    def from_env(
        cls,
    ) -> "ServerConfig":
        graph_path_value = os.getenv(
            "WIKIARENA_GRAPH_PATH",
        )
        graph_metadata_path_value = os.getenv(
            GRAPH_METADATA_PATH_ENV_VAR,
        )

        return cls(
            graph_path=_expand_optional_path(
                graph_path_value,
            ),
            graph_metadata_path=_expand_optional_path(
                graph_metadata_path_value,
            ),
            snapshot_id=os.getenv(
                SNAPSHOT_ID_ENV_VAR,
            ),
            service_version=os.getenv(
                SERVICE_VERSION_ENV_VAR,
                _default_service_version(),
            ),
            cors_origins=_parse_cors_origins(
                os.getenv(
                    CORS_ORIGINS_ENV_VAR,
                ),
            ),
            host=os.getenv(
                HOST_ENV_VAR,
                os.getenv(
                    "HOST",
                    "0.0.0.0",
                ),
            ),
            port=int(
                os.getenv(
                    PORT_ENV_VAR,
                    os.getenv(
                        "PORT",
                        "8000",
                    ),
                ),
            ),
            artifact_dir=Path(
                os.getenv(
                    ARTIFACT_DIR_ENV_VAR,
                    "artifacts",
                ),
            ).expanduser(),
        )


def _expand_optional_path(
    raw_value: str | None,
) -> Path | None:
    if raw_value is None or not raw_value.strip():
        return None
    return Path(
        raw_value,
    ).expanduser()


def _default_service_version(
    package_name: str = "wikiarena",
) -> str:
    try:
        return version(
            package_name,
        )
    except PackageNotFoundError:
        return "0.0.1"


def _parse_cors_origins(
    raw_value: str | None,
) -> tuple[str, ...]:
    if raw_value is None or not raw_value.strip():
        return DEFAULT_CORS_ORIGINS

    parsed_values = tuple(
        part.strip()
        for part in raw_value.split(
            ",",
        )
        if part.strip()
    )
    if not parsed_values:
        return DEFAULT_CORS_ORIGINS
    return parsed_values
