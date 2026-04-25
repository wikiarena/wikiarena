from __future__ import annotations

import json
import lzma
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from wikiarena.graph.naming import (
    graph_metadata_file_name,
    parse_standard_graph_file_name,
)
from wikiarena.graph.release import (
    GraphReleaseMetadata,
    graph_release_metadata_from_dict,
    sha256_file,
)
from wikiarena.paths import get_default_graph_install_dir
from wikiarena.solver.binary import MappedBinarySolverGraph

GITHUB_API_BASE_URL = "https://api.github.com"
GRAPH_ARCHIVE_SUFFIX = ".xz"
CHECKSUM_SUFFIX = ".sha256"
HTTP_TIMEOUT_SECONDS = 60
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
HTTP_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "wikiarena-cli",
}


@dataclass(frozen=True)
class GraphReleaseAssetSet:
    repo: str
    release_tag: str
    release_name: str
    wiki: str
    dump_date: str
    graph_file_name: str
    archive_file_name: str
    checksum_file_name: str
    metadata_file_name: str
    archive_download_url: str
    checksum_download_url: str
    metadata_download_url: str


@dataclass(frozen=True)
class GraphInstallResult:
    release_tag: str
    graph_path: Path
    metadata_path: Path
    snapshot_id: str | None
    node_count: int
    edge_count: int
    already_installed: bool


def resolve_graph_release_assets(
    *,
    repo: str = "wikiarena/wikiarena",
    tag: str | None = None,
) -> GraphReleaseAssetSet:
    release_payloads = _fetch_release_payloads(
        repo=repo,
        tag=tag,
    )
    for release_payload in release_payloads:
        asset_set = _resolve_asset_set_from_release_payload(
            repo=repo,
            release_payload=release_payload,
        )
        if asset_set is not None:
            return asset_set

    if tag is not None:
        raise ValueError(
            f"No published graph release with a complete asset triplet was found for tag {tag} in {repo}.",
        )
    raise ValueError(
        f"No published graph release with a complete asset triplet was found in {repo}.",
    )


def install_graph_release(
    *,
    repo: str = "wikiarena/wikiarena",
    tag: str | None = None,
    install_dir: Path | None = None,
    force: bool = False,
) -> GraphInstallResult:
    asset_set = resolve_graph_release_assets(
        repo=repo,
        tag=tag,
    )
    resolved_install_dir = _resolve_install_dir(
        install_dir,
    )
    resolved_install_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata_bytes = _download_bytes(
        asset_set.metadata_download_url,
    )
    release_metadata = graph_release_metadata_from_dict(
        json.loads(
            metadata_bytes.decode("utf-8"),
        ),
    )
    _validate_metadata_matches_asset_set(
        release_metadata=release_metadata,
        asset_set=asset_set,
    )

    target_graph_path = resolved_install_dir / release_metadata.graph.file_name
    target_metadata_path = resolved_install_dir / asset_set.metadata_file_name

    if not force and _existing_install_matches_release(
        graph_path=target_graph_path,
        metadata_path=target_metadata_path,
        metadata_bytes=metadata_bytes,
        release_metadata=release_metadata,
    ):
        return GraphInstallResult(
            release_tag=asset_set.release_tag,
            graph_path=target_graph_path,
            metadata_path=target_metadata_path,
            snapshot_id=release_metadata.snapshot_id,
            node_count=release_metadata.graph.node_count,
            edge_count=release_metadata.graph.edge_count,
            already_installed=True,
        )

    checksum_bytes = _download_bytes(
        asset_set.checksum_download_url,
    )
    checksum_sha256 = _parse_sha256_checksum_file(
        checksum_bytes.decode("utf-8"),
        expected_file_name=asset_set.archive_file_name,
    )
    if checksum_sha256 != release_metadata.compressed.sha256:
        raise ValueError(
            "compressed graph checksum does not match the release metadata",
        )

    with tempfile.TemporaryDirectory(
        dir=resolved_install_dir,
        prefix="install-",
    ) as temporary_directory:
        temporary_dir = Path(
            temporary_directory,
        )
        temporary_archive_path = temporary_dir / asset_set.archive_file_name
        temporary_graph_path = temporary_dir / release_metadata.graph.file_name
        temporary_metadata_path = temporary_dir / asset_set.metadata_file_name

        _download_file(
            asset_set.archive_download_url,
            temporary_archive_path,
        )
        archive_sha256 = sha256_file(
            temporary_archive_path,
        )
        if archive_sha256 != checksum_sha256:
            raise ValueError(
                "downloaded graph archive checksum does not match the published checksum",
            )

        _decompress_xz_file(
            archive_path=temporary_archive_path,
            output_path=temporary_graph_path,
        )
        _verify_installed_graph_file(
            graph_path=temporary_graph_path,
            release_metadata=release_metadata,
        )

        temporary_metadata_path.write_bytes(
            metadata_bytes,
        )
        os.replace(
            temporary_graph_path,
            target_graph_path,
        )
        os.replace(
            temporary_metadata_path,
            target_metadata_path,
        )

    return GraphInstallResult(
        release_tag=asset_set.release_tag,
        graph_path=target_graph_path,
        metadata_path=target_metadata_path,
        snapshot_id=release_metadata.snapshot_id,
        node_count=release_metadata.graph.node_count,
        edge_count=release_metadata.graph.edge_count,
        already_installed=False,
    )


def _fetch_release_payloads(
    *,
    repo: str,
    tag: str | None,
) -> tuple[dict[str, Any], ...]:
    if tag is not None:
        payload = _get_json(
            f"{GITHUB_API_BASE_URL}/repos/{repo}/releases/tags/{tag}",
        )
        if not isinstance(payload, dict):
            raise ValueError("GitHub release lookup did not return an object payload")
        return (payload,)

    payload = _get_json(
        f"{GITHUB_API_BASE_URL}/repos/{repo}/releases",
    )
    if not isinstance(payload, list):
        raise ValueError("GitHub releases lookup did not return a list payload")
    return tuple(item for item in payload if isinstance(item, dict))


def _get_json(
    url: str,
) -> object:
    response = requests.get(
        url,
        headers=HTTP_HEADERS,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _download_bytes(
    url: str,
) -> bytes:
    response = requests.get(
        url,
        headers=HTTP_HEADERS,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.content


def _download_file(
    url: str,
    output_path: Path,
) -> None:
    response = requests.get(
        url,
        headers=HTTP_HEADERS,
        timeout=HTTP_TIMEOUT_SECONDS,
        stream=True,
    )
    response.raise_for_status()
    with output_path.open(
        "wb",
    ) as file_handle:
        for chunk in response.iter_content(
            chunk_size=DOWNLOAD_CHUNK_SIZE,
        ):
            if chunk:
                file_handle.write(
                    chunk,
                )


def _resolve_asset_set_from_release_payload(
    *,
    repo: str,
    release_payload: dict[str, Any],
) -> GraphReleaseAssetSet | None:
    if release_payload.get("draft") or release_payload.get("prerelease"):
        return None

    release_tag = release_payload.get("tag_name")
    if not isinstance(release_tag, str) or not release_tag:
        return None

    assets = release_payload.get("assets")
    if not isinstance(assets, list):
        return None

    assets_by_name: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_name = asset.get("name")
        if isinstance(asset_name, str) and asset_name:
            assets_by_name[asset_name] = asset

    for archive_file_name in sorted(assets_by_name):
        parsed_archive = _parse_standard_graph_archive_file_name(
            archive_file_name,
        )
        if parsed_archive is None:
            continue
        graph_file_name, wiki, dump_date = parsed_archive
        metadata_file_name = graph_metadata_file_name(
            wiki=wiki,
            dump_date=dump_date,
        )
        checksum_file_name = f"{archive_file_name}{CHECKSUM_SUFFIX}"

        archive_asset = assets_by_name.get(
            archive_file_name,
        )
        checksum_asset = assets_by_name.get(
            checksum_file_name,
        )
        metadata_asset = assets_by_name.get(
            metadata_file_name,
        )
        if archive_asset is None or checksum_asset is None or metadata_asset is None:
            continue

        archive_download_url = _asset_download_url(
            archive_asset,
        )
        checksum_download_url = _asset_download_url(
            checksum_asset,
        )
        metadata_download_url = _asset_download_url(
            metadata_asset,
        )
        if (
            archive_download_url is None
            or checksum_download_url is None
            or metadata_download_url is None
        ):
            continue

        release_name = release_payload.get("name")
        return GraphReleaseAssetSet(
            repo=repo,
            release_tag=release_tag,
            release_name=release_name if isinstance(release_name, str) else release_tag,
            wiki=wiki,
            dump_date=dump_date,
            graph_file_name=graph_file_name,
            archive_file_name=archive_file_name,
            checksum_file_name=checksum_file_name,
            metadata_file_name=metadata_file_name,
            archive_download_url=archive_download_url,
            checksum_download_url=checksum_download_url,
            metadata_download_url=metadata_download_url,
        )

    return None


def _parse_standard_graph_archive_file_name(
    file_name: str,
) -> tuple[str, str, str] | None:
    if not file_name.endswith(GRAPH_ARCHIVE_SUFFIX):
        return None
    graph_file_name = file_name.removesuffix(
        GRAPH_ARCHIVE_SUFFIX,
    )
    parsed = parse_standard_graph_file_name(
        graph_file_name,
    )
    if parsed is None:
        return None
    wiki, dump_date = parsed
    return graph_file_name, wiki, dump_date


def _asset_download_url(
    asset_payload: dict[str, Any],
) -> str | None:
    browser_download_url = asset_payload.get(
        "browser_download_url",
    )
    if isinstance(browser_download_url, str) and browser_download_url:
        return browser_download_url
    return None


def _resolve_install_dir(
    install_dir: Path | None,
) -> Path:
    if install_dir is None:
        return get_default_graph_install_dir()
    return Path(
        install_dir,
    ).expanduser()


def _validate_metadata_matches_asset_set(
    *,
    release_metadata: GraphReleaseMetadata,
    asset_set: GraphReleaseAssetSet,
) -> None:
    if release_metadata.graph.file_name != asset_set.graph_file_name:
        raise ValueError(
            "release metadata graph file name does not match the release asset name",
        )
    if release_metadata.compressed.file_name != asset_set.archive_file_name:
        raise ValueError(
            "release metadata compressed file name does not match the archive asset name",
        )
    if release_metadata.wiki != asset_set.wiki:
        raise ValueError("release metadata wiki does not match the asset naming")
    if release_metadata.dump_date != asset_set.dump_date:
        raise ValueError("release metadata dump_date does not match the asset naming")


def _existing_install_matches_release(
    *,
    graph_path: Path,
    metadata_path: Path,
    metadata_bytes: bytes,
    release_metadata: GraphReleaseMetadata,
) -> bool:
    if not graph_path.exists() or not metadata_path.exists():
        return False
    if metadata_path.read_bytes() != metadata_bytes:
        return False

    try:
        _verify_installed_graph_file(
            graph_path=graph_path,
            release_metadata=release_metadata,
        )
    except (FileNotFoundError, ValueError):
        return False
    return True


def _verify_installed_graph_file(
    *,
    graph_path: Path,
    release_metadata: GraphReleaseMetadata,
) -> None:
    if not graph_path.exists():
        raise FileNotFoundError(f"graph file does not exist: {graph_path}")
    if graph_path.stat().st_size != release_metadata.graph.bytes:
        raise ValueError("graph file size does not match the release metadata")
    if sha256_file(graph_path) != release_metadata.graph.sha256:
        raise ValueError("graph file checksum does not match the release metadata")
    with MappedBinarySolverGraph(
        file_path=graph_path,
    ) as graph:
        if graph.node_count != release_metadata.graph.node_count:
            raise ValueError("graph node_count does not match the release metadata")
        if graph.edge_count != release_metadata.graph.edge_count:
            raise ValueError("graph edge_count does not match the release metadata")


def _parse_sha256_checksum_file(
    checksum_text: str,
    *,
    expected_file_name: str,
) -> str:
    for raw_line in checksum_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        digest, file_name = parts[0], parts[-1].lstrip("*")
        if file_name == expected_file_name:
            return digest
    raise ValueError(
        f"published checksum file did not include {expected_file_name}",
    )


def _decompress_xz_file(
    *,
    archive_path: Path,
    output_path: Path,
) -> None:
    with (
        lzma.open(
            archive_path,
            "rb",
        ) as compressed_file_handle,
        output_path.open(
            "wb",
        ) as output_file_handle,
    ):
        while True:
            chunk = compressed_file_handle.read(
                DOWNLOAD_CHUNK_SIZE,
            )
            if not chunk:
                break
            output_file_handle.write(
                chunk,
            )
