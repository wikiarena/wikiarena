from __future__ import annotations

from pathlib import Path

import pytest

import wikiarena.wiki_runtime as wiki_runtime


def test_resolve_graph_file_path_uses_single_installed_dated_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(b"graph")
    monkeypatch.setattr(
        wiki_runtime,
        "get_default_graph_install_dir",
        lambda: tmp_path,
    )
    monkeypatch.delenv(wiki_runtime.GRAPH_PATH_ENV_VAR, raising=False)

    resolved_path = wiki_runtime.resolve_graph_file_path(None)

    assert resolved_path == graph_path.resolve()


def test_resolve_graph_file_path_rejects_legacy_install_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_graph_path = tmp_path / "wikiarena_graph.bin"
    legacy_graph_path.write_bytes(b"graph")
    monkeypatch.setattr(
        wiki_runtime,
        "get_default_graph_install_dir",
        lambda: tmp_path,
    )
    monkeypatch.delenv(wiki_runtime.GRAPH_PATH_ENV_VAR, raising=False)

    with pytest.raises(FileNotFoundError, match="no installed dated graph file found"):
        wiki_runtime.resolve_graph_file_path(None)


def test_resolve_graph_file_path_uses_latest_installed_graph_when_multiple_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    older_graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    newer_graph_path = tmp_path / "wikiarena_graph_enwiki_20260401.bin"
    older_graph_path.write_bytes(b"graph-a")
    newer_graph_path.write_bytes(b"graph-b")
    monkeypatch.setattr(
        wiki_runtime,
        "get_default_graph_install_dir",
        lambda: tmp_path,
    )
    monkeypatch.delenv(wiki_runtime.GRAPH_PATH_ENV_VAR, raising=False)

    resolved_path = wiki_runtime.resolve_graph_file_path(None)

    assert resolved_path == newer_graph_path.resolve()


def test_resolve_graph_file_path_uses_pinned_installed_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    older_graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    newer_graph_path = tmp_path / "wikiarena_graph_enwiki_20260401.bin"
    older_graph_path.write_bytes(b"graph-a")
    newer_graph_path.write_bytes(b"graph-b")
    monkeypatch.setattr(
        wiki_runtime,
        "get_default_graph_install_dir",
        lambda: tmp_path,
    )
    monkeypatch.delenv(wiki_runtime.GRAPH_PATH_ENV_VAR, raising=False)

    graph_selection = wiki_runtime.resolve_graph_selection(
        None,
        snapshot_id="enwiki-20260301",
    )

    assert graph_selection.graph_path == older_graph_path.resolve()
    assert graph_selection.selected_via == "installed_snapshot"


def test_resolve_graph_file_path_missing_pinned_snapshot_mentions_install_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed_graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    installed_graph_path.write_bytes(b"graph")
    monkeypatch.setattr(
        wiki_runtime,
        "get_default_graph_install_dir",
        lambda: tmp_path,
    )
    monkeypatch.delenv(wiki_runtime.GRAPH_PATH_ENV_VAR, raising=False)

    with pytest.raises(FileNotFoundError) as error_info:
        wiki_runtime.resolve_graph_file_path(
            None,
            snapshot_id="enwiki-20260401",
        )

    error_message = str(error_info.value)
    assert "enwiki-20260401" in error_message
    assert "wikiarena graph install --tag graph-enwiki-20260401" in error_message


def test_resolve_graph_file_path_rejects_snapshot_mismatch(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260401.bin"
    graph_path.write_bytes(b"graph")

    with pytest.raises(ValueError, match="snapshot_id mismatch"):
        wiki_runtime.resolve_graph_file_path(
            graph_path,
            snapshot_id="enwiki-20260301",
        )


def test_resolve_graph_file_path_missing_graph_mentions_default_install_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_dir = tmp_path / "Library" / "Application Support" / "wikiarena" / "graphs"
    monkeypatch.setattr(
        wiki_runtime,
        "get_default_graph_install_dir",
        lambda: install_dir,
    )
    monkeypatch.delenv(wiki_runtime.GRAPH_PATH_ENV_VAR, raising=False)

    with pytest.raises(FileNotFoundError) as error_info:
        wiki_runtime.resolve_graph_file_path(None)

    error_message = str(error_info.value)
    assert str(install_dir) in error_message
    assert "wikiarena graph install" in error_message


def test_resolve_graph_snapshot_id_infers_from_graph_file_name(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(b"graph")

    resolved_snapshot_id = wiki_runtime.resolve_graph_snapshot_id(
        graph_path,
        None,
    )

    assert resolved_snapshot_id == "enwiki-20260301"


def test_resolve_graph_file_path_accepts_legacy_symlink_alias_for_dated_graph(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    alias_path = tmp_path / "wikiarena_graph.bin"
    graph_path.write_bytes(b"graph")
    alias_path.symlink_to(graph_path.name)

    resolved_path = wiki_runtime.resolve_graph_file_path(
        alias_path,
    )

    assert resolved_path == graph_path.resolve()
