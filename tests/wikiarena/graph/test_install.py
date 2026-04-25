from __future__ import annotations

import json
import lzma
from pathlib import Path

import pytest

from wikiarena.graph import (
    build_graph_release_metadata,
    graph_file_name,
    graph_metadata_file_name,
)
from wikiarena.graph.install import install_graph_release, resolve_graph_release_assets
from wikiarena.solver.binary.io import SolverBinaryData, write_solver_binary


def _make_toy_solver_binary_data() -> SolverBinaryData:
    return SolverBinaryData(
        canonical_titles=(
            "Alpha",
            "Bravo",
            "Charlie",
            "Delta",
            "Echo",
            "Foxtrot",
        ),
        out_offsets=(0, 2, 3, 4, 5, 5, 5),
        out_neighbors=(1, 2, 3, 3, 4),
        in_offsets=(0, 0, 1, 2, 4, 5, 5),
        in_neighbors=(0, 0, 1, 2, 3),
    )


class FakeResponse:
    def __init__(
        self,
        *,
        payload: object | None = None,
        content: bytes | None = None,
        status_code: int = 200,
    ) -> None:
        self._payload = payload
        self.content = content or b""
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(
                f"http error {self.status_code}",
            )

    def json(self) -> object:
        if self._payload is None:
            raise AssertionError("missing json payload")
        return self._payload

    def iter_content(
        self,
        chunk_size: int = 8192,
    ):
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index : index + chunk_size]


def _build_release_fixture(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, FakeResponse]]:
    wiki = "enwiki"
    dump_date = "20260301"
    graph_name = graph_file_name(
        wiki=wiki,
        dump_date=dump_date,
    )
    metadata_name = graph_metadata_file_name(
        wiki=wiki,
        dump_date=dump_date,
    )

    graph_path = tmp_path / graph_name
    archive_path = tmp_path / f"{graph_name}.xz"
    write_solver_binary(
        file_path=graph_path,
        data=_make_toy_solver_binary_data(),
    )
    archive_path.write_bytes(
        lzma.compress(
            graph_path.read_bytes(),
        ),
    )

    metadata = build_graph_release_metadata(
        graph_file_path=graph_path,
        compressed_file_path=archive_path,
        dump_date=dump_date,
        snapshot_id=f"{wiki}-{dump_date}",
        wiki=wiki,
        git_sha="abc123",
    )
    metadata_bytes = (
        json.dumps(
            metadata.to_dict(),
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    checksum_bytes = (f"{metadata.compressed.sha256}  {archive_path.name}\n").encode(
        "utf-8"
    )

    api_base = "https://api.github.com/repos/wikiarena/wikiarena"
    asset_base = (
        "https://downloads.example.test/wikiarena/wikiarena/graph-enwiki-20260301"
    )

    release_payload = {
        "tag_name": "graph-enwiki-20260301",
        "name": "enwiki graph 20260301",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": archive_path.name,
                "browser_download_url": f"{asset_base}/{archive_path.name}",
            },
            {
                "name": f"{archive_path.name}.sha256",
                "browser_download_url": f"{asset_base}/{archive_path.name}.sha256",
            },
            {
                "name": metadata_name,
                "browser_download_url": f"{asset_base}/{metadata_name}",
            },
        ],
    }
    responses = {
        f"{api_base}/releases": FakeResponse(
            payload=[
                {
                    "tag_name": "v0.1.0",
                    "name": "code release",
                    "draft": False,
                    "prerelease": False,
                    "assets": [],
                },
                release_payload,
            ],
        ),
        f"{api_base}/releases/tags/graph-enwiki-20260301": FakeResponse(
            payload=release_payload,
        ),
        f"{asset_base}/{archive_path.name}": FakeResponse(
            content=archive_path.read_bytes(),
        ),
        f"{asset_base}/{archive_path.name}.sha256": FakeResponse(
            content=checksum_bytes,
        ),
        f"{asset_base}/{metadata_name}": FakeResponse(
            content=metadata_bytes,
        ),
    }
    return release_payload, responses


def test_resolve_graph_release_assets_selects_first_valid_graph_release(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, responses = _build_release_fixture(
        tmp_path,
    )

    def fake_get(url: str, **_: object) -> FakeResponse:
        return responses[url]

    monkeypatch.setattr(
        "wikiarena.graph.install.requests.get",
        fake_get,
    )

    asset_set = resolve_graph_release_assets(
        repo="wikiarena/wikiarena",
    )

    assert asset_set.release_tag == "graph-enwiki-20260301"
    assert asset_set.archive_file_name == "wikiarena_graph_enwiki_20260301.bin.xz"
    assert (
        asset_set.metadata_file_name == "wikiarena_graph_enwiki_20260301.metadata.json"
    )
    assert (
        asset_set.checksum_file_name == "wikiarena_graph_enwiki_20260301.bin.xz.sha256"
    )


def test_install_graph_release_downloads_verifies_and_installs_graph(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, responses = _build_release_fixture(
        tmp_path,
    )

    def fake_get(url: str, **_: object) -> FakeResponse:
        return responses[url]

    monkeypatch.setattr(
        "wikiarena.graph.install.requests.get",
        fake_get,
    )

    install_dir = tmp_path / "install"
    result = install_graph_release(
        repo="wikiarena/wikiarena",
        install_dir=install_dir,
    )

    assert result.already_installed is False
    assert result.release_tag == "graph-enwiki-20260301"
    assert result.graph_path == install_dir / "wikiarena_graph_enwiki_20260301.bin"
    assert (
        result.metadata_path
        == install_dir / "wikiarena_graph_enwiki_20260301.metadata.json"
    )
    assert result.snapshot_id == "enwiki-20260301"
    assert result.node_count == 6
    assert result.edge_count == 5
    assert result.graph_path.exists()
    assert result.metadata_path.exists()

    installed_metadata = json.loads(
        result.metadata_path.read_text(
            encoding="utf-8",
        ),
    )
    assert installed_metadata["snapshot_id"] == "enwiki-20260301"


def test_install_graph_release_reuses_existing_verified_install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, responses = _build_release_fixture(
        tmp_path,
    )
    requested_urls: list[str] = []

    def fake_get(url: str, **_: object) -> FakeResponse:
        requested_urls.append(url)
        return responses[url]

    monkeypatch.setattr(
        "wikiarena.graph.install.requests.get",
        fake_get,
    )

    install_dir = tmp_path / "install"
    first_result = install_graph_release(
        repo="wikiarena/wikiarena",
        install_dir=install_dir,
    )
    assert first_result.already_installed is False

    requested_urls.clear()
    second_result = install_graph_release(
        repo="wikiarena/wikiarena",
        install_dir=install_dir,
    )

    assert second_result.already_installed is True
    assert second_result.graph_path == first_result.graph_path
    assert all(
        not url.endswith(".xz") and not url.endswith(".xz.sha256")
        for url in requested_urls
    )


def test_resolve_graph_release_assets_rejects_release_without_triplet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **_: object) -> FakeResponse:
        assert url == "https://api.github.com/repos/wikiarena/wikiarena/releases"
        return FakeResponse(
            payload=[
                {
                    "tag_name": "graph-enwiki-20260301",
                    "name": "broken graph release",
                    "draft": False,
                    "prerelease": False,
                    "assets": [
                        {
                            "name": "wikiarena_graph_enwiki_20260301.bin.xz",
                            "browser_download_url": "https://downloads.example.test/archive.xz",
                        },
                    ],
                },
            ],
        )

    monkeypatch.setattr(
        "wikiarena.graph.install.requests.get",
        fake_get,
    )

    with pytest.raises(
        ValueError,
        match="No published graph release",
    ):
        resolve_graph_release_assets(
            repo="wikiarena/wikiarena",
        )
