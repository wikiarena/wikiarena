from __future__ import annotations

import math
from statistics import mean

from pydantic import BaseModel
from pydantic import Field

from wikiarena.eval import load_run_results
from wikiarena.wikipedia import LiveWikiService


class PageContextInspection(BaseModel):
    page_title: str
    link_count: int
    prompt_char_count: int
    approx_prompt_tokens: int
    first_links: list[str] = Field(
        default_factory=list,
    )


class RunTokenInspection(BaseModel):
    run_id: str
    participant_id: str
    total_step_attempts: int
    total_committed_moves: int
    total_input_tokens: int
    total_output_tokens: int
    average_input_tokens_per_step: float | None
    max_input_tokens_per_step: int | None
    average_response_time_ms: float | None


class RunTokenInspectionSummary(BaseModel):
    runs: list[RunTokenInspection] = Field(
        default_factory=list,
    )


async def inspect_page_contexts(
    page_titles: list[str],
    *,
    language: str = "en",
) -> list[PageContextInspection]:
    wiki_service = LiveWikiService(
        language=language,
    )
    inspections: list[PageContextInspection] = []
    for page_title in page_titles:
        page = await wiki_service.get_page(
            page_title,
            include_all_namespaces=False,
        )
        prompt_text = build_page_links_prompt(
            title=page.title,
            links=page.links,
        )
        inspections.append(
            PageContextInspection(
                page_title=page.title,
                link_count=len(page.links),
                prompt_char_count=len(prompt_text),
                approx_prompt_tokens=approximate_token_count(
                    prompt_text,
                ),
                first_links=page.links[:10],
            ),
        )
    return inspections


def inspect_run_token_usage(
    input_path: str,
) -> RunTokenInspectionSummary:
    run_results = load_run_results(
        input_path,
    )
    run_inspections: list[RunTokenInspection] = []
    for run_result in run_results:
        input_tokens = [
            step_attempt.model_metrics.input_tokens
            for step_attempt in run_result.step_attempts
            if step_attempt.model_metrics is not None
        ]
        output_tokens = [
            step_attempt.model_metrics.output_tokens
            for step_attempt in run_result.step_attempts
            if step_attempt.model_metrics is not None
        ]
        response_times = [
            step_attempt.model_metrics.response_time_ms
            for step_attempt in run_result.step_attempts
            if step_attempt.model_metrics is not None
        ]

        run_inspections.append(
            RunTokenInspection(
                run_id=run_result.run_id,
                participant_id=run_result.participant_id,
                total_step_attempts=run_result.total_step_attempts,
                total_committed_moves=run_result.total_committed_moves,
                total_input_tokens=sum(input_tokens),
                total_output_tokens=sum(output_tokens),
                average_input_tokens_per_step=(
                    mean(input_tokens) if input_tokens else None
                ),
                max_input_tokens_per_step=max(input_tokens) if input_tokens else None,
                average_response_time_ms=(
                    mean(response_times) if response_times else None
                ),
            ),
        )

    return RunTokenInspectionSummary(
        runs=run_inspections,
    )


def build_page_links_prompt(
    *,
    title: str,
    links: list[str],
) -> str:
    return (
        f"You are currently on the page '{title}'.\n"
        f"Here are the available links:\n{links}"
    )


def approximate_token_count(
    text: str,
) -> int:
    return math.ceil(
        len(text) / 4,
    )
