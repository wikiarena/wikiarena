from __future__ import annotations

import gzip
from pathlib import Path

from wikiarena.graph import (
    DumpTrimKind,
    iter_combined_grouped_link_rows,
    iter_normalized_link_rows,
    iter_pruned_page_rows,
    iter_resolved_redirect_rows,
    iter_trimmed_dump_rows,
    write_trimmed_dump,
)


def _write_gzip_text(
    file_path: Path,
    content: str,
) -> None:
    with gzip.open(
        file_path,
        "wt",
        encoding="utf-8",
    ) as file_handle:
        file_handle.write(
            content,
        )


def test_write_trimmed_dump_extracts_expected_page_rows(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "page.sql.gz"
    output_path = tmp_path / "pages.txt.gz"
    _write_gzip_text(
        input_path,
        "INSERT INTO `page` VALUES (1,0,'Apple',0,'x'),(2,1,'Talk:Apple',0,'y');\n",
    )

    processed_lines, written_rows = write_trimmed_dump(
        kind=DumpTrimKind.PAGES,
        input_file_path=input_path,
        output_file_path=output_path,
    )

    assert processed_lines == 1
    assert written_rows == 2
    with gzip.open(
        output_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        assert file_handle.read().splitlines() == [
            "1\t0\tApple\t0",
            "2\t1\tTalk:Apple\t0",
        ]


def test_write_trimmed_dump_unescapes_sql_escaped_page_titles(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "page.sql.gz"
    output_path = tmp_path / "pages.txt.gz"
    _write_gzip_text(
        input_path,
        "INSERT INTO `page` VALUES (1,0,'Girls\\'_Generation_(2011_album)',0,'x'),(2,0,'St_Clement\\'s_Church,_Sutton-on-Sea',0,'y');\n",
    )

    write_trimmed_dump(
        kind=DumpTrimKind.PAGES,
        input_file_path=input_path,
        output_file_path=output_path,
    )

    with gzip.open(
        output_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        assert file_handle.read().splitlines() == [
            "1\t0\tGirls'_Generation_(2011_album)\t0",
            "2\t0\tSt_Clement's_Church,_Sutton-on-Sea\t0",
        ]


def test_iter_trimmed_dump_rows_preserves_page_titles_containing_tuple_separator_text() -> (
    None
):
    raw_line = (
        "INSERT INTO `page` VALUES "
        "(71701640,0,'104-2,3,(6),(7),11',0,'x'),"
        "(71701649,0,'2022_Binh_Duong_karaoke_bar_fire',0,'y');\n"
    )

    assert list(
        iter_trimmed_dump_rows(
            kind=DumpTrimKind.PAGES,
            raw_lines=[raw_line],
        ),
    ) == [
        "71701640\t0\t104-2,3,(6),(7),11\t0",
        "71701649\t0\t2022_Binh_Duong_karaoke_bar_fire\t0",
    ]


def test_iter_trimmed_dump_rows_preserves_redirect_titles_containing_tuple_separator_text() -> (
    None
):
    raw_line = (
        "INSERT INTO `redirect` VALUES "
        "(5,0,'104-2,3,(6),(7),11',NULL,NULL),"
        "(6,0,'Fruit',NULL,NULL);\n"
    )

    assert list(
        iter_trimmed_dump_rows(
            kind=DumpTrimKind.REDIRECTS,
            raw_lines=[raw_line],
        ),
    ) == [
        "5\t0\t104-2,3,(6),(7),11",
        "6\t0\tFruit",
    ]


def test_iter_trimmed_dump_rows_preserves_linktarget_titles_containing_tuple_separator_text() -> (
    None
):
    raw_line = (
        "INSERT INTO `linktarget` VALUES (11,0,'104-2,3,(6),(7),11'),(12,0,'Fruit');\n"
    )

    assert list(
        iter_trimmed_dump_rows(
            kind=DumpTrimKind.TARGETS,
            raw_lines=[raw_line],
        ),
    ) == [
        "11\t0\t104-2,3,(6),(7),11",
        "12\t0\tFruit",
    ]


def test_iter_combined_grouped_link_rows_merges_sorted_inputs(
    tmp_path: Path,
) -> None:
    outgoing_path = tmp_path / "outgoing.txt.gz"
    incoming_path = tmp_path / "incoming.txt.gz"
    _write_gzip_text(
        outgoing_path,
        "1\t2|3\n3\t4\n5\t8|9|10\n",
    )
    _write_gzip_text(
        incoming_path,
        "2\t1\n3\t1|7\n5\t2\n6\t5\n",
    )

    assert list(
        iter_combined_grouped_link_rows(
            outgoing_file_path=outgoing_path,
            incoming_file_path=incoming_path,
        ),
    ) == [
        "1\t2\t0\t2|3\t",
        "2\t0\t1\t\t1",
        "3\t1\t2\t4\t1|7",
        "5\t3\t1\t8|9|10\t2",
        "6\t0\t1\t\t5",
    ]


def test_iter_resolved_redirect_rows_filters_to_article_namespace(
    tmp_path: Path,
) -> None:
    pages_path = tmp_path / "pages.txt.gz"
    redirects_path = tmp_path / "redirects.txt.gz"
    _write_gzip_text(
        pages_path,
        "1\t0\tApple\t0\n2\t0\tFruit\t0\n3\t0\tApple_(company)\t0\n4\t1\tTalk:Apple\t0\n5\t0\tApple_redirect\t1\n",
    )
    _write_gzip_text(
        redirects_path,
        "5\t0\tApple\n4\t0\tFruit\n1\t1\tTalk:Apple\n",
    )

    assert list(
        iter_resolved_redirect_rows(
            pages_file_path=pages_path,
            redirects_file_path=redirects_path,
        ),
    ) == ["5\t1"]


def test_iter_pruned_page_rows_keeps_article_pages_and_valid_redirects(
    tmp_path: Path,
) -> None:
    pages_path = tmp_path / "pages.txt.gz"
    redirects_path = tmp_path / "redirects_with_ids.txt.gz"
    _write_gzip_text(
        pages_path,
        "1\t0\tApple\t0\n2\t0\tFruit\t0\n3\t1\tTalk:Apple\t0\n4\t0\tRedirected\t1\n5\t0\tBrokenRedirect\t1\n",
    )
    _write_gzip_text(
        redirects_path,
        "4\t2\n",
    )

    assert list(
        iter_pruned_page_rows(
            pages_file_path=pages_path,
            resolved_redirects_file_path=redirects_path,
        ),
    ) == [
        "1\t0\tApple\t0",
        "2\t0\tFruit\t0",
        "4\t0\tRedirected\t1",
    ]


def test_iter_normalized_link_rows_applies_target_redirects_and_drops_redirect_sources(
    tmp_path: Path,
) -> None:
    pages_path = tmp_path / "pages.pruned.txt.gz"
    redirects_path = tmp_path / "redirects.resolved_ids.txt.gz"
    links_path = tmp_path / "links.raw_ids.txt.gz"
    _write_gzip_text(
        pages_path,
        "1\t0\tApple\t0\n2\t0\tFruit\t0\n3\t0\tPear\t0\n4\t0\tRedirected\t1\n",
    )
    _write_gzip_text(
        redirects_path,
        "4\t2\n",
    )
    _write_gzip_text(
        links_path,
        "1\t4\n4\t3\n3\t99\n2\t2\n",
    )

    assert list(
        iter_normalized_link_rows(
            pages_file_path=pages_path,
            redirects_file_path=redirects_path,
            links_file_path=links_path,
        ),
    ) == [
        "1\t2",
    ]


def test_iter_normalized_link_rows_does_not_merge_redirect_source_links_into_canonical_page(
    tmp_path: Path,
) -> None:
    pages_path = tmp_path / "pages.pruned.txt.gz"
    redirects_path = tmp_path / "redirects.resolved_ids.txt.gz"
    links_path = tmp_path / "links.raw_ids.txt.gz"
    _write_gzip_text(
        pages_path,
        "1\t0\tCanonical\t0\n2\t0\tTarget\t0\n3\t0\tAlias\t1\n",
    )
    _write_gzip_text(
        redirects_path,
        "3\t1\n",
    )
    _write_gzip_text(
        links_path,
        "3\t2\n",
    )

    assert (
        list(
            iter_normalized_link_rows(
                pages_file_path=pages_path,
                redirects_file_path=redirects_path,
                links_file_path=links_path,
            ),
        )
        == []
    )
