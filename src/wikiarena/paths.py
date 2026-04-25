from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "wikiarena"
GRAPHS_DIR_NAME = "graphs"


def get_user_data_dir() -> Path:
    return Path(
        user_data_dir(
            appname=APP_NAME,
            appauthor=False,
        ),
    )


def get_default_graph_install_dir() -> Path:
    return get_user_data_dir() / GRAPHS_DIR_NAME
