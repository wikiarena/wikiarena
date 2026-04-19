from __future__ import annotations

from pathlib import Path

import pytest


_VNEXT_TEST_ROOT = (Path(__file__).parent / "wikiarena").resolve()


def pytest_addoption(
    parser: pytest.Parser,
) -> None:
    parser.addoption(
        "--run-legacy",
        action="store_true",
        default=False,
        help="Run deprecated legacy tests outside tests/wikiarena",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    run_legacy = config.getoption(
        "--run-legacy",
    )

    legacy_skip_marker = pytest.mark.skip(
        reason=("Legacy tests are deprecated; run with --run-legacy to include them"),
    )

    for item in items:
        test_path = Path(
            str(item.fspath),
        ).resolve()
        is_vnext_test = _is_path_under(
            test_path,
            _VNEXT_TEST_ROOT,
        )
        if is_vnext_test:
            continue

        item.add_marker(
            "legacy",
        )
        if not run_legacy:
            item.add_marker(
                legacy_skip_marker,
            )


def pytest_ignore_collect(
    collection_path: Path,
    config: pytest.Config,
) -> bool:
    if config.getoption(
        "--run-legacy",
    ):
        return False

    resolved_path = Path(
        collection_path,
    ).resolve()
    return not _is_path_under(
        resolved_path,
        _VNEXT_TEST_ROOT,
    )


def _is_path_under(
    child_path: Path,
    parent_path: Path,
) -> bool:
    try:
        child_path.relative_to(
            parent_path,
        )
    except ValueError:
        return False
    return True
