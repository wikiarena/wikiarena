from __future__ import annotations

import random
from collections import defaultdict

from pydantic import BaseModel
from pydantic import Field

from wikiarena.solver.backend import SolverBackend
from wikiarena.solver.runtime_benchmark import RuntimeBenchmarkCase
from wikiarena.wikipedia import LiveWikiService


class SampledSolverCase(BaseModel):
    case: RuntimeBenchmarkCase
    path_length: int
    first_path: list[str] = Field(
        default_factory=list,
    )


async def sample_random_cases_by_path_length(
    *,
    backend: SolverBackend,
    wiki_service: LiveWikiService,
    desired_counts_by_length: dict[int, int],
    random_batch_size: int = 20,
    max_attempts: int = 200,
) -> list[SampledSolverCase]:
    sampled_by_length: dict[int, list[SampledSolverCase]] = defaultdict(list)
    seen_pairs: set[tuple[str, str]] = set()

    for _ in range(max_attempts):
        if _all_buckets_satisfied(
            sampled_by_length,
            desired_counts_by_length,
        ):
            break

        candidate_pages = await wiki_service.get_random_pages(
            count=random_batch_size,
        )
        valid_starts, valid_targets = await _split_valid_random_pages(
            wiki_service,
            candidate_pages,
        )
        if not valid_starts or not valid_targets:
            continue

        random.shuffle(valid_starts)
        random.shuffle(valid_targets)

        for start_page in valid_starts:
            for target_page in valid_targets:
                if start_page == target_page:
                    continue
                pair = (start_page, target_page)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                try:
                    response = await backend.find_shortest_path(
                        start_page,
                        target_page,
                    )
                except ValueError:
                    continue
                path_length = response.path_length
                if path_length not in desired_counts_by_length:
                    continue
                if (
                    len(sampled_by_length[path_length])
                    >= desired_counts_by_length[path_length]
                ):
                    continue

                case_id = (
                    f"random_{path_length}_{len(sampled_by_length[path_length]) + 1}"
                )
                sampled_by_length[path_length].append(
                    SampledSolverCase(
                        case=RuntimeBenchmarkCase(
                            case_id=case_id,
                            start_page=start_page,
                            target_page=target_page,
                        ),
                        path_length=path_length,
                        first_path=response.paths[0] if response.paths else [],
                    ),
                )

                if _all_buckets_satisfied(
                    sampled_by_length,
                    desired_counts_by_length,
                ):
                    break
            if _all_buckets_satisfied(
                sampled_by_length,
                desired_counts_by_length,
            ):
                break

    sampled_cases: list[SampledSolverCase] = []
    for path_length in sorted(desired_counts_by_length):
        sampled_cases.extend(sampled_by_length[path_length])
    return sampled_cases


async def _split_valid_random_pages(
    wiki_service: LiveWikiService,
    candidate_pages: list[str],
) -> tuple[list[str], list[str]]:
    valid_starts: list[str] = []
    valid_targets: list[str] = []
    for page_title in candidate_pages:
        if await wiki_service.has_outgoing_links(page_title):
            valid_starts.append(page_title)
        if await wiki_service.has_incoming_links(page_title):
            valid_targets.append(page_title)
    return valid_starts, valid_targets


def _all_buckets_satisfied(
    sampled_by_length: dict[int, list[SampledSolverCase]],
    desired_counts_by_length: dict[int, int],
) -> bool:
    return all(
        len(sampled_by_length[path_length]) >= desired_count
        for path_length, desired_count in desired_counts_by_length.items()
    )
