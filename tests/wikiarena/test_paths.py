from __future__ import annotations

from pathlib import Path

import wikiarena.paths as paths


def test_get_default_graph_install_dir_uses_user_data_dir(monkeypatch) -> None:
    user_data_dir = Path("/tmp/wikiarena-data")
    captured: dict[str, object] = {}

    def fake_user_data_dir(appname: str, appauthor: bool) -> str:
        captured["appname"] = appname
        captured["appauthor"] = appauthor
        return str(user_data_dir)

    monkeypatch.setattr(
        paths,
        "user_data_dir",
        fake_user_data_dir,
    )

    assert paths.get_default_graph_install_dir() == user_data_dir / "graphs"
    assert captured == {
        "appname": "wikiarena",
        "appauthor": False,
    }
