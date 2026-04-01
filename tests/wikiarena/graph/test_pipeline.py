from __future__ import annotations

import io
import json
import subprocess
from contextlib import nullcontext
from pathlib import Path

from wikiarena.graph import pipeline


def test_resolve_dump_date_uses_dump_directory_date_from_index(
    monkeypatch,
) -> None:
    dump_index_payload = {
        "wikis": {
            "enwiki": {
                "jobs": {
                    "pagelinkstable": {
                        "updated": "2026-03-05 13:18:42",
                        "status": "done",
                        "files": {
                            "enwiki-20260301-pagelinks.sql.gz": {
                                "url": "/enwiki/20260301/enwiki-20260301-pagelinks.sql.gz",
                            },
                        },
                    },
                },
            },
        },
    }

    monkeypatch.setattr(
        pipeline,
        "urlopen",
        lambda _url: nullcontext(
            io.BytesIO(
                json.dumps(
                    dump_index_payload,
                ).encode("utf-8"),
            ),
        ),
    )

    assert (
        pipeline.resolve_dump_date(
            wiki="enwiki",
            requested_dump_date=None,
        )
        == "20260301"
    )


def test_download_file_if_missing_falls_back_to_direct_download_when_torrent_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_file_path = tmp_path / "enwiki-20260301-redirect.sql.gz"
    download_calls: list[list[str]] = []

    def fake_which(
        tool_name: str,
    ) -> str | None:
        tool_paths = {
            "aria2c": "/usr/bin/aria2c",
            "wget": "/usr/bin/wget",
        }
        return tool_paths.get(
            tool_name,
        )

    def fake_run(
        command: list[str],
        *,
        check: bool,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        assert check is True
        download_calls.append(
            command,
        )
        if command[0] == "/usr/bin/aria2c":
            assert cwd == output_file_path.parent
            raise subprocess.CalledProcessError(
                returncode=22,
                cmd=command,
            )
        if command[0] == "/usr/bin/wget":
            Path(
                command[3],
            ).write_bytes(b"downloaded-directly")
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
            )
        raise AssertionError(
            f"unexpected command: {command}",
        )

    monkeypatch.setattr(
        pipeline.shutil,
        "which",
        fake_which,
    )
    monkeypatch.setattr(
        pipeline.subprocess,
        "run",
        fake_run,
    )

    pipeline._download_file_if_missing(
        url="https://dumps.wikimedia.org/enwiki/20260301/enwiki-20260301-redirect.sql.gz",
        output_file_path=output_file_path,
        use_torrent=True,
        torrent_url="https://tools.wmflabs.org/dump-torrents/enwiki/20260301",
        progress_reporter=None,
    )

    assert output_file_path.read_bytes() == b"downloaded-directly"
    assert [command[0] for command in download_calls] == [
        "/usr/bin/aria2c",
        "/usr/bin/wget",
    ]
