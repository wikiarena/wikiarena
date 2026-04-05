from __future__ import annotations

import gzip
from collections.abc import Iterable, Iterator
from enum import StrEnum
from pathlib import Path
from typing import Callable, TextIO

ARTICLE_NAMESPACE = "0"


class DumpTrimKind(StrEnum):
    PAGES = "pages"
    LINKS = "links"
    REDIRECTS = "redirects"
    TARGETS = "targets"


TRIM_SPECS = {
    DumpTrimKind.PAGES: {
        "insert_prefix": "INSERT INTO `page` VALUES ",
        "selected_fields": (0, 1, 2, 3),
    },
    DumpTrimKind.LINKS: {
        "insert_prefix": "INSERT INTO `pagelinks` VALUES ",
        "selected_fields": (0, 1, 2),
    },
    DumpTrimKind.REDIRECTS: {
        "insert_prefix": "INSERT INTO `redirect` VALUES ",
        "selected_fields": (0, 1, 2),
    },
    DumpTrimKind.TARGETS: {
        "insert_prefix": "INSERT INTO `linktarget` VALUES ",
        "selected_fields": (0, 1, 2),
    },
}


def write_trimmed_dump(
    *,
    kind: DumpTrimKind,
    input_file_path: Path,
    output_file_path: Path,
    progress_callback: Callable[[str], None] | None = None,
    progress_label: str | None = None,
) -> tuple[int, int]:
    input_path = input_file_path
    output_path = output_file_path
    processed_lines = 0
    written_rows = 0

    with (
        gzip.open(
            input_path,
            "rt",
            encoding="utf-8",
            errors="replace",
        ) as input_file_handle,
        gzip.open(
            output_path,
            "wt",
            encoding="utf-8",
        ) as output_file_handle,
    ):
        insert_prefix = TRIM_SPECS[kind]["insert_prefix"]
        selected_fields = TRIM_SPECS[kind]["selected_fields"]
        for raw_line in input_file_handle:
            processed_lines += 1
            if progress_callback is not None and processed_lines % 250_000 == 0:
                label = progress_label if progress_label is not None else kind.value
                progress_callback(
                    f"{label}: processed {processed_lines:,} SQL lines",
                )
            for trimmed_row in _iter_trimmed_rows_from_sql_line(
                insert_prefix=insert_prefix,
                selected_fields=selected_fields,
                raw_line=raw_line,
            ):
                output_file_handle.write(
                    trimmed_row,
                )
                output_file_handle.write("\n")
                written_rows += 1

    return processed_lines, written_rows


def iter_trimmed_dump_rows(
    *,
    kind: DumpTrimKind,
    raw_lines: Iterable[str],
) -> Iterator[str]:
    insert_prefix = TRIM_SPECS[kind]["insert_prefix"]
    selected_fields = TRIM_SPECS[kind]["selected_fields"]

    for raw_line in raw_lines:
        yield from _iter_trimmed_rows_from_sql_line(
            insert_prefix=insert_prefix,
            selected_fields=selected_fields,
            raw_line=raw_line,
        )


def _iter_trimmed_rows_from_sql_line(
    *,
    insert_prefix: str,
    selected_fields: tuple[int, ...],
    raw_line: str,
) -> Iterator[str]:
    values_payload = _extract_insert_values_payload(
        insert_prefix=insert_prefix,
        raw_line=raw_line,
    )
    if values_payload is None:
        return

    for tuple_fields in _iter_sql_tuple_fields(
        values_payload,
    ):
        yield "\t".join(tuple_fields[field_index] for field_index in selected_fields)


def _extract_insert_values_payload(
    *,
    insert_prefix: str,
    raw_line: str,
) -> str | None:
    stripped_line = raw_line.strip()
    if not stripped_line.startswith(
        insert_prefix,
    ):
        return None
    if not stripped_line.endswith(";"):
        return None
    return stripped_line[len(insert_prefix) : -1]


def _iter_sql_tuple_fields(
    values_payload: str,
) -> Iterator[list[str]]:
    tuple_characters: list[str] = []
    tuple_depth = 0
    inside_string = False
    escape_next = False

    for character in values_payload:
        if inside_string:
            tuple_characters.append(
                character,
            )
            if escape_next:
                escape_next = False
                continue
            if character == "\\":
                escape_next = True
                continue
            if character == "'":
                inside_string = False
            continue

        if character == "'":
            inside_string = True
            tuple_characters.append(
                character,
            )
            continue

        if character == "(":
            if tuple_depth > 0:
                tuple_characters.append(
                    character,
                )
            tuple_depth += 1
            continue

        if character == ")":
            tuple_depth -= 1
            if tuple_depth < 0:
                raise ValueError(
                    "unexpected closing parenthesis while parsing SQL insert tuples",
                )
            if tuple_depth == 0:
                yield _parse_sql_tuple_fields(
                    "".join(tuple_characters),
                )
                tuple_characters = []
            else:
                tuple_characters.append(
                    character,
                )
            continue

        if tuple_depth == 0:
            if character == "," or character.isspace():
                continue
            raise ValueError(
                f"unexpected character outside SQL tuple payload: {character!r}",
            )

        tuple_characters.append(
            character,
        )

    if tuple_depth != 0 or inside_string:
        raise ValueError(
            "unterminated SQL tuple payload",
        )


def _parse_sql_tuple_fields(
    tuple_payload: str,
) -> list[str]:
    field_values: list[str] = []
    field_characters: list[str] = []
    inside_string = False
    escape_next = False
    field_is_quoted = False

    def flush_field() -> None:
        raw_field_value = "".join(
            field_characters,
        )
        if field_is_quoted:
            field_values.append(
                _unescape_sql_field(
                    raw_field_value,
                ),
            )
        else:
            field_values.append(
                raw_field_value.strip(),
            )

    for character in tuple_payload:
        if inside_string:
            if escape_next:
                field_characters.append(
                    character,
                )
                escape_next = False
                continue
            if character == "\\":
                field_characters.append(
                    character,
                )
                escape_next = True
                continue
            if character == "'":
                inside_string = False
                continue
            field_characters.append(
                character,
            )
            continue

        if character == "'":
            if field_characters and any(
                not existing_character.isspace()
                for existing_character in field_characters
            ):
                raise ValueError(
                    "unexpected quoted string start inside unquoted SQL field",
                )
            inside_string = True
            field_is_quoted = True
            continue

        if character == ",":
            flush_field()
            field_characters = []
            field_is_quoted = False
            continue

        field_characters.append(
            character,
        )

    if inside_string:
        raise ValueError(
            "unterminated SQL string field",
        )

    flush_field()
    return field_values


def _unescape_sql_field(
    field_value: str,
) -> str:
    escape_map = {
        "0": "\0",
        "b": "\b",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "Z": "\x1a",
        '"': '"',
        "'": "'",
        "\\": "\\",
    }
    unescaped_characters: list[str] = []
    escape_next = False

    for character in field_value:
        if escape_next:
            unescaped_characters.append(
                escape_map.get(
                    character,
                    character,
                ),
            )
            escape_next = False
            continue
        if character == "\\":
            escape_next = True
            continue
        unescaped_characters.append(
            character,
        )

    if escape_next:
        unescaped_characters.append("\\")

    return "".join(
        unescaped_characters,
    )


def iter_resolved_redirect_rows(
    *,
    pages_file_path: Path,
    redirects_file_path: Path,
) -> Iterator[str]:
    page_id_to_namespace: dict[str, str] = {}
    article_titles_to_ids: dict[str, str] = {}

    with gzip.open(
        pages_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            page_id, page_namespace, page_title, _ = _require_columns(
                line=raw_line,
                expected_columns=4,
                file_label="pages",
                line_number=line_number,
            )
            page_id_to_namespace[page_id] = page_namespace
            if page_namespace == ARTICLE_NAMESPACE:
                article_titles_to_ids[page_title] = page_id

    redirects: dict[str, str] = {}
    with gzip.open(
        redirects_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            source_page_id, target_namespace, target_title = _require_columns(
                line=raw_line,
                expected_columns=3,
                file_label="redirects",
                line_number=line_number,
            )
            source_namespace = page_id_to_namespace.get(
                source_page_id,
            )
            if source_namespace != ARTICLE_NAMESPACE:
                continue
            if target_namespace != ARTICLE_NAMESPACE:
                continue

            target_page_id = article_titles_to_ids.get(
                target_title,
            )
            if target_page_id is not None:
                redirects[source_page_id] = target_page_id

    for source_page_id, target_page_id in redirects.items():
        resolved_target_page_id = _resolve_redirect_target(
            source_page_id=source_page_id,
            starting_target_page_id=target_page_id,
            redirects=redirects,
        )
        if resolved_target_page_id is None:
            continue
        yield f"{source_page_id}\t{resolved_target_page_id}"


def iter_pruned_page_rows(
    *,
    pages_file_path: Path,
    resolved_redirects_file_path: Path,
) -> Iterator[str]:
    valid_redirect_sources: set[str] = set()
    with gzip.open(
        resolved_redirects_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            source_page_id, _ = _require_columns(
                line=raw_line,
                expected_columns=2,
                file_label="resolved redirects",
                line_number=line_number,
            )
            valid_redirect_sources.add(
                source_page_id,
            )

    with gzip.open(
        pages_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            page_id, page_namespace, page_title, is_redirect = _require_columns(
                line=raw_line,
                expected_columns=4,
                file_label="pages",
                line_number=line_number,
            )
            if page_namespace != ARTICLE_NAMESPACE:
                continue
            if is_redirect == "0" or page_id in valid_redirect_sources:
                yield f"{page_id}\t{page_namespace}\t{page_title}\t{is_redirect}"


def iter_normalized_link_rows(
    *,
    pages_file_path: Path,
    redirects_file_path: Path,
    links_file_path: Path,
) -> Iterator[str]:
    valid_page_ids = _load_valid_page_ids(
        pages_file_path,
    )
    redirects = _load_redirect_map(
        redirects_file_path,
    )

    with gzip.open(
        links_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            source_page_id, target_page_id = _require_columns(
                line=raw_line,
                expected_columns=2,
                file_label="links",
                line_number=line_number,
            )

            if source_page_id in redirects:
                continue
            target_page_id = redirects.get(
                target_page_id,
                target_page_id,
            )

            if source_page_id == target_page_id:
                continue
            if source_page_id not in valid_page_ids:
                continue
            if target_page_id not in valid_page_ids:
                continue
            yield f"{source_page_id}\t{target_page_id}"


def iter_combined_grouped_link_rows(
    *,
    outgoing_file_path: Path,
    incoming_file_path: Path,
) -> Iterator[str]:
    outgoing_rows = iter_grouped_rows(
        outgoing_file_path,
    )
    incoming_rows = iter_grouped_rows(
        incoming_file_path,
    )

    next_outgoing = next(
        outgoing_rows,
        None,
    )
    next_incoming = next(
        incoming_rows,
        None,
    )

    while next_outgoing is not None or next_incoming is not None:
        if next_incoming is None or (
            next_outgoing is not None and next_outgoing[0] < next_incoming[0]
        ):
            if next_outgoing is None:
                raise RuntimeError(
                    "outgoing grouped rows unexpectedly missing during merge",
                )
            current_outgoing = next_outgoing
            page_id = current_outgoing[0]
            outgoing_links = current_outgoing[1]
            incoming_links = ""
            next_outgoing = next(
                outgoing_rows,
                None,
            )
        elif next_outgoing is None or next_incoming[0] < next_outgoing[0]:
            if next_incoming is None:
                raise RuntimeError(
                    "incoming grouped rows unexpectedly missing during merge",
                )
            current_incoming = next_incoming
            page_id = current_incoming[0]
            outgoing_links = ""
            incoming_links = current_incoming[1]
            next_incoming = next(
                incoming_rows,
                None,
            )
        else:
            page_id = next_outgoing[0]
            outgoing_links = next_outgoing[1]
            incoming_links = next_incoming[1]
            next_outgoing = next(
                outgoing_rows,
                None,
            )
            next_incoming = next(
                incoming_rows,
                None,
            )

        yield "\t".join(
            [
                str(page_id),
                str(_count_pipe_separated_links(outgoing_links)),
                str(_count_pipe_separated_links(incoming_links)),
                outgoing_links,
                incoming_links,
            ],
        )


def write_rows(
    *,
    rows: Iterable[str],
    output_stream: TextIO,
) -> None:
    for row in rows:
        output_stream.write(
            row,
        )
        output_stream.write("\n")


def iter_grouped_rows(
    input_path: Path,
) -> Iterator[tuple[int, str]]:
    with gzip.open(
        input_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            if not raw_line.strip():
                continue
            yield parse_grouped_line(
                raw_line=raw_line,
                file_label=str(input_path),
                line_number=line_number,
            )


def parse_grouped_line(
    *,
    raw_line: str,
    file_label: str,
    line_number: int,
) -> tuple[int, str]:
    stripped_line = raw_line.rstrip("\n")
    parts = stripped_line.split(
        "\t",
        1,
    )
    if not parts or not parts[0]:
        raise ValueError(
            f"error parsing {file_label} line {line_number}: invalid grouped links line {raw_line!r}",
        )
    page_id = int(
        parts[0],
    )
    links = parts[1] if len(parts) == 2 else ""
    return page_id, links


def _count_pipe_separated_links(
    pipe_separated_links: str,
) -> int:
    if not pipe_separated_links:
        return 0
    return pipe_separated_links.count("|") + 1


def _load_valid_page_ids(
    pages_file_path: Path,
) -> set[str]:
    valid_page_ids: set[str] = set()
    with gzip.open(
        pages_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            page_id, _, _, _ = _require_columns(
                line=raw_line,
                expected_columns=4,
                file_label="pages",
                line_number=line_number,
            )
            valid_page_ids.add(
                page_id,
            )
    return valid_page_ids


def _load_redirect_map(
    redirects_file_path: Path,
) -> dict[str, str]:
    redirects: dict[str, str] = {}
    with gzip.open(
        redirects_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            source_page_id, target_page_id = _require_columns(
                line=raw_line,
                expected_columns=2,
                file_label="redirects",
                line_number=line_number,
            )
            redirects[source_page_id] = target_page_id
    return redirects


def _resolve_redirect_target(
    *,
    source_page_id: str,
    starting_target_page_id: str,
    redirects: dict[str, str],
) -> str | None:
    target_page_id = starting_target_page_id
    redirect_depth = 0

    while target_page_id in redirects:
        target_page_id = redirects[target_page_id]
        redirect_depth += 1
        if target_page_id == starting_target_page_id or redirect_depth > 100:
            return None

    if target_page_id == source_page_id:
        return None
    return target_page_id


def _require_columns(
    *,
    line: str,
    expected_columns: int,
    file_label: str,
    line_number: int,
) -> tuple[str, ...]:
    parts = line.rstrip("\n").split("\t")
    if len(parts) < expected_columns:
        raise ValueError(
            f"Line {line_number} in {file_label} file has {len(parts)} parts, expected {expected_columns}",
        )
    return tuple(
        parts[:expected_columns],
    )
