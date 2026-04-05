from __future__ import annotations

import gzip
from pathlib import Path

import requests

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
        "_fetch_dump_index_payload",
        lambda: dump_index_payload,
    )

    assert (
        pipeline.resolve_dump_date(
            wiki="enwiki",
            requested_dump_date=None,
        )
        == "20260301"
    )


def test_discover_dump_file_metadata_reads_dumpstatus_payload(
    monkeypatch,
) -> None:
    dump_status_payload = {
        "jobs": {
            "redirecttable": {
                "status": "done",
                "files": {
                    "enwiki-20260301-redirect.sql.gz": {
                        "url": "/enwiki/20260301/enwiki-20260301-redirect.sql.gz",
                        "size": 111,
                        "sha1": "redirect-sha1",
                    },
                },
            },
            "pagetable": {
                "status": "done",
                "files": {
                    "enwiki-20260301-page.sql.gz": {
                        "url": "/enwiki/20260301/enwiki-20260301-page.sql.gz",
                        "size": 222,
                        "sha1": "page-sha1",
                    },
                },
            },
            "pagelinkstable": {
                "status": "done",
                "files": {
                    "enwiki-20260301-pagelinks.sql.gz": {
                        "url": "/enwiki/20260301/enwiki-20260301-pagelinks.sql.gz",
                        "size": 333,
                        "sha1": "links-sha1",
                    },
                },
            },
            "linktargettable": {
                "status": "done",
                "files": {
                    "enwiki-20260301-linktarget.sql.gz": {
                        "url": "/enwiki/20260301/enwiki-20260301-linktarget.sql.gz",
                        "size": 444,
                        "sha1": "targets-sha1",
                    },
                },
            },
        },
    }

    monkeypatch.setattr(
        pipeline,
        "_fetch_dump_status_payload",
        lambda *, wiki, dump_date: dump_status_payload,
    )

    dump_files = pipeline._discover_dump_file_metadata(
        wiki="enwiki",
        dump_date="20260301",
    )

    assert dump_files["redirects"].url == (
        "https://dumps.wikimedia.org/enwiki/20260301/enwiki-20260301-redirect.sql.gz"
    )
    assert dump_files["pages"].size_bytes == 222
    assert dump_files["links"].sha1 == "links-sha1"
    assert dump_files["targets"].file_name == "enwiki-20260301-linktarget.sql.gz"


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        chunks: list[bytes] | None = None,
        json_payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._chunks = chunks or []
        self._json_payload = json_payload
        self.headers = headers or {}

    def __enter__(
        self,
    ) -> "_FakeResponse":
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> bool:
        return False

    def raise_for_status(
        self,
    ) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"status {self.status_code}",
            )

    def json(
        self,
    ) -> dict[str, object]:
        assert self._json_payload is not None
        return self._json_payload

    def iter_content(
        self,
        chunk_size: int,
    ):
        assert chunk_size > 0
        yield from self._chunks


class _FakeSession:
    def __init__(
        self,
        responses: list[_FakeResponse],
    ) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def __enter__(
        self,
    ) -> "_FakeSession":
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> bool:
        return False

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        stream: bool = False,
        timeout: int | None = None,
    ) -> _FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "stream": stream,
                "timeout": timeout,
            },
        )
        return self._responses.pop(
            0,
        )


def test_download_file_if_missing_resumes_partial_http_download(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_file_path = tmp_path / "enwiki-20260301-redirect.sql.gz"
    output_file_path.write_bytes(
        b"hello ",
    )
    fake_session = _FakeSession(
        [
            _FakeResponse(
                status_code=206,
                chunks=[b"world"],
                headers={"Content-Length": "5"},
            ),
        ],
    )

    monkeypatch.setattr(
        pipeline.requests,
        "Session",
        lambda: fake_session,
    )

    pipeline._download_file_if_missing(
        url="https://dumps.wikimedia.org/enwiki/20260301/enwiki-20260301-redirect.sql.gz",
        output_file_path=output_file_path,
        expected_size_bytes=11,
        progress_reporter=None,
    )

    assert output_file_path.read_bytes() == b"hello world"
    assert fake_session.calls == [
        {
            "url": "https://dumps.wikimedia.org/enwiki/20260301/enwiki-20260301-redirect.sql.gz",
            "headers": {"Range": "bytes=6-"},
            "stream": True,
            "timeout": pipeline.HTTP_TIMEOUT_SECONDS,
        },
    ]


def test_trim_dump_if_missing_uses_rust_sql_trimmer_when_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_file_path = tmp_path / "page.sql.gz"
    output_file_path = tmp_path / "pages.txt.gz"
    input_file_path.write_bytes(
        b"input",
    )
    rust_call_arguments: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        pipeline,
        "_resolve_sql_trimmer_binary_path",
        lambda: Path("/tmp/wikiarena-sql-trimmer"),
    )

    def fake_rust_trim(
        *,
        kind,
        input_file_path,
        output_file_path,
        sql_trimmer_binary_path,
    ) -> tuple[int, int]:
        rust_call_arguments.append(
            (
                kind,
                input_file_path,
                output_file_path,
                sql_trimmer_binary_path,
            ),
        )
        output_file_path.write_bytes(
            b"trimmed",
        )
        return (7, 11)

    monkeypatch.setattr(
        pipeline,
        "_write_trimmed_dump_with_rust",
        fake_rust_trim,
    )
    monkeypatch.setattr(
        pipeline,
        "write_trimmed_dump",
        lambda **_: (_ for _ in ()).throw(
            AssertionError("python trimmer should not run")
        ),
    )

    pipeline._trim_dump_if_missing(
        kind=pipeline.DumpTrimKind.PAGES,
        input_file_path=input_file_path,
        output_file_path=output_file_path,
        progress_reporter=None,
    )

    assert output_file_path.read_bytes() == b"trimmed"
    assert rust_call_arguments == [
        (
            pipeline.DumpTrimKind.PAGES,
            input_file_path,
            output_file_path,
            Path("/tmp/wikiarena-sql-trimmer"),
        ),
    ]


def test_trim_dump_if_missing_falls_back_to_python_trimmer_without_rust_binary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_file_path = tmp_path / "page.sql.gz"
    output_file_path = tmp_path / "pages.txt.gz"
    input_file_path.write_bytes(
        b"input",
    )
    python_call_arguments: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        pipeline,
        "_resolve_sql_trimmer_binary_path",
        lambda: None,
    )

    def fake_python_trim(
        *,
        kind,
        input_file_path,
        output_file_path,
        progress_callback,
        progress_label,
    ) -> tuple[int, int]:
        python_call_arguments.append(
            (
                kind,
                input_file_path,
                output_file_path,
                progress_callback,
                progress_label,
            ),
        )
        output_file_path.write_bytes(
            b"trimmed",
        )
        return (5, 9)

    monkeypatch.setattr(
        pipeline,
        "write_trimmed_dump",
        fake_python_trim,
    )

    pipeline._trim_dump_if_missing(
        kind=pipeline.DumpTrimKind.PAGES,
        input_file_path=input_file_path,
        output_file_path=output_file_path,
        progress_reporter=None,
    )

    assert output_file_path.read_bytes() == b"trimmed"
    assert python_call_arguments == [
        (
            pipeline.DumpTrimKind.PAGES,
            input_file_path,
            output_file_path,
            None,
            "trim pages",
        ),
    ]


def test_write_trimmed_dump_with_rust_streams_rows_through_binary(
    tmp_path: Path,
) -> None:
    input_file_path = tmp_path / "page.sql.gz"
    output_file_path = tmp_path / "pages.txt.gz"
    sql_trimmer_binary_path = tmp_path / "wikiarena-sql-trimmer"

    with gzip.open(
        input_file_path,
        "wt",
        encoding="utf-8",
    ) as file_handle:
        file_handle.write("INSERT INTO `page` VALUES (1,0,'Apple',0,'x');\n")

    sql_trimmer_binary_path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        "arguments = iter(sys.argv[1:])\n"
        "stats_path = None\n"
        "for argument in arguments:\n"
        "    if argument == '--kind':\n"
        "        next(arguments)\n"
        "    elif argument == '--stats-path':\n"
        "        stats_path = next(arguments)\n"
        "sys.stdin.read()\n"
        "sys.stdout.write('1\\t0\\tApple\\t0\\n')\n"
        "with open(stats_path, 'w', encoding='utf-8') as file_handle:\n"
        "    json.dump({'processed_lines': 1, 'written_rows': 1}, file_handle)\n",
        encoding="utf-8",
    )
    sql_trimmer_binary_path.chmod(
        0o755,
    )

    processed_lines, written_rows = pipeline._write_trimmed_dump_with_rust(
        kind=pipeline.DumpTrimKind.PAGES,
        input_file_path=input_file_path,
        output_file_path=output_file_path,
        sql_trimmer_binary_path=sql_trimmer_binary_path,
    )

    assert (processed_lines, written_rows) == (1, 1)
    with gzip.open(
        output_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        assert file_handle.read() == "1\t0\tApple\t0\n"
