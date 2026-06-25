from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from wikiarena.protocol import RunResult, TerminalOutcome

UnsolvedPairPolicy = Literal["skip", "draw"]


class ParticipantSummary(BaseModel):
    participant_id: str
    runs: int
    ranking_eligible_runs: int
    successes: int
    model_failures: int
    system_failures: int
    average_committed_moves_on_success: float | None = None
    average_duration_ms_on_success: float | None = None
    pairwise_wins: float = 0.0
    pairwise_losses: float = 0.0
    pairwise_draws: float = 0.0
    pairwise_skipped: float = 0.0
    elo: int | None = None


class EvaluationSummary(BaseModel):
    total_runs: int
    total_races: int
    pairwise_comparisons: int
    pairwise_skipped_comparisons: int
    tie_breaker: str
    unsolved_pair_policy: UnsolvedPairPolicy
    ruleset_hashes: list[str]
    taskset_hashes: list[str]
    participants: list[ParticipantSummary]


def load_run_results(
    input_path: str | Path,
) -> list[RunResult]:
    resolved_input_path = (
        Path(
            input_path,
        )
        .expanduser()
        .resolve()
    )
    run_results: list[RunResult] = []
    with resolved_input_path.open(
        "r",
        encoding="utf-8",
    ) as file_handle:
        for line_number, line in enumerate(
            file_handle,
            start=1,
        ):
            stripped_line = line.strip()
            if not stripped_line:
                continue
            try:
                parsed_line = json.loads(
                    stripped_line,
                )
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid JSON on line {line_number} of {resolved_input_path}",
                ) from error

            run_results.append(
                RunResult.model_validate(
                    parsed_line,
                ),
            )
    return run_results


def summarize_run_results(
    run_results: list[RunResult],
    *,
    tie_breaker: str = "fewest_moves_then_draw",
    unsolved_pair_policy: UnsolvedPairPolicy = "skip",
) -> EvaluationSummary:
    race_groups: dict[str, list[RunResult]] = defaultdict(list)
    participant_groups: dict[str, list[RunResult]] = defaultdict(list)
    ruleset_hashes: set[str] = set()
    taskset_hashes: set[str] = set()

    for run_result in run_results:
        race_groups[run_result.race_id].append(
            run_result,
        )
        participant_groups[run_result.participant_id].append(
            run_result,
        )
        if run_result.ruleset_hash:
            ruleset_hashes.add(
                run_result.ruleset_hash,
            )
        if run_result.taskset_hash:
            taskset_hashes.add(
                run_result.taskset_hash,
            )

    pairwise_scores = BradleyTerryRatings()
    participant_pairwise_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "wins": 0.0,
            "losses": 0.0,
            "draws": 0.0,
            "skipped": 0.0,
        },
    )
    pairwise_comparisons = 0
    pairwise_skipped_comparisons = 0

    for race_run_results in race_groups.values():
        eligible_run_results = [
            run_result for run_result in race_run_results if run_result.ranking_eligible
        ]
        for index, run_result_a in enumerate(
            eligible_run_results,
        ):
            for run_result_b in eligible_run_results[index + 1 :]:
                if run_result_a.participant_id == run_result_b.participant_id:
                    continue

                if _should_skip_unsolved_pair(
                    run_result_a,
                    run_result_b,
                    unsolved_pair_policy=unsolved_pair_policy,
                ):
                    participant_pairwise_totals[run_result_a.participant_id][
                        "skipped"
                    ] += 1.0
                    participant_pairwise_totals[run_result_b.participant_id][
                        "skipped"
                    ] += 1.0
                    pairwise_skipped_comparisons += 1
                    continue

                outcome = compare_run_results(
                    run_result_a,
                    run_result_b,
                    tie_breaker=tie_breaker,
                )
                pairwise_comparisons += 1
                pairwise_scores.add_comparison(
                    run_result_a.participant_id,
                    run_result_b.participant_id,
                    outcome,
                )

                if outcome > 0:
                    participant_pairwise_totals[run_result_a.participant_id][
                        "wins"
                    ] += 1.0
                    participant_pairwise_totals[run_result_b.participant_id][
                        "losses"
                    ] += 1.0
                elif outcome < 0:
                    participant_pairwise_totals[run_result_b.participant_id][
                        "wins"
                    ] += 1.0
                    participant_pairwise_totals[run_result_a.participant_id][
                        "losses"
                    ] += 1.0
                else:
                    participant_pairwise_totals[run_result_a.participant_id][
                        "draws"
                    ] += 1.0
                    participant_pairwise_totals[run_result_b.participant_id][
                        "draws"
                    ] += 1.0

    elo_ratings = pairwise_scores.calculate_elo()

    participant_summaries: list[ParticipantSummary] = []
    for participant_id, participant_run_results in participant_groups.items():
        successes = [
            run_result
            for run_result in participant_run_results
            if run_result.terminal_outcome == TerminalOutcome.SUCCESS
        ]
        average_committed_moves_on_success = None
        average_duration_ms_on_success = None
        if successes:
            average_committed_moves_on_success = sum(
                run_result.total_committed_moves for run_result in successes
            ) / len(successes)
            average_duration_ms_on_success = sum(
                run_result.duration_ms or 0.0 for run_result in successes
            ) / len(successes)

        pairwise_totals = participant_pairwise_totals[participant_id]
        participant_summaries.append(
            ParticipantSummary(
                participant_id=participant_id,
                runs=len(participant_run_results),
                ranking_eligible_runs=sum(
                    1
                    for run_result in participant_run_results
                    if run_result.ranking_eligible
                ),
                successes=len(successes),
                model_failures=sum(
                    1
                    for run_result in participant_run_results
                    if run_result.terminal_outcome == TerminalOutcome.MODEL_FAILURE
                ),
                system_failures=sum(
                    1
                    for run_result in participant_run_results
                    if run_result.terminal_outcome == TerminalOutcome.SYSTEM_FAILURE
                ),
                average_committed_moves_on_success=average_committed_moves_on_success,
                average_duration_ms_on_success=average_duration_ms_on_success,
                pairwise_wins=pairwise_totals["wins"],
                pairwise_losses=pairwise_totals["losses"],
                pairwise_draws=pairwise_totals["draws"],
                pairwise_skipped=pairwise_totals["skipped"],
                elo=elo_ratings.get(
                    participant_id,
                ),
            ),
        )

    participant_summaries.sort(
        key=lambda summary: (
            summary.elo if summary.elo is not None else 0,
            summary.successes,
            -summary.system_failures,
        ),
        reverse=True,
    )

    return EvaluationSummary(
        total_runs=len(run_results),
        total_races=len(race_groups),
        pairwise_comparisons=pairwise_comparisons,
        pairwise_skipped_comparisons=pairwise_skipped_comparisons,
        tie_breaker=tie_breaker,
        unsolved_pair_policy=unsolved_pair_policy,
        ruleset_hashes=sorted(
            ruleset_hashes,
        ),
        taskset_hashes=sorted(
            taskset_hashes,
        ),
        participants=participant_summaries,
    )


def _should_skip_unsolved_pair(
    run_result_a: RunResult,
    run_result_b: RunResult,
    *,
    unsolved_pair_policy: UnsolvedPairPolicy,
) -> bool:
    if unsolved_pair_policy == "draw":
        return False
    if unsolved_pair_policy != "skip":
        raise ValueError(
            f"unsupported unsolved_pair_policy: {unsolved_pair_policy!r}",
        )
    return (
        run_result_a.terminal_outcome != TerminalOutcome.SUCCESS
        and run_result_b.terminal_outcome != TerminalOutcome.SUCCESS
    )


def compare_run_results(
    run_result_a: RunResult,
    run_result_b: RunResult,
    *,
    tie_breaker: str,
) -> int:
    if (
        run_result_a.terminal_outcome == TerminalOutcome.SUCCESS
        and run_result_b.terminal_outcome != TerminalOutcome.SUCCESS
    ):
        return 1
    if (
        run_result_b.terminal_outcome == TerminalOutcome.SUCCESS
        and run_result_a.terminal_outcome != TerminalOutcome.SUCCESS
    ):
        return -1

    if (
        run_result_a.terminal_outcome == TerminalOutcome.SUCCESS
        and run_result_b.terminal_outcome == TerminalOutcome.SUCCESS
    ):
        if run_result_a.total_committed_moves < run_result_b.total_committed_moves:
            return 1
        if run_result_b.total_committed_moves < run_result_a.total_committed_moves:
            return -1

        if tie_breaker == "fewest_moves_then_fastest_ms":
            duration_a = run_result_a.duration_ms or 0.0
            duration_b = run_result_b.duration_ms or 0.0
            if duration_a < duration_b:
                return 1
            if duration_b < duration_a:
                return -1

    return 0


class BradleyTerryRatings:
    def __init__(
        self,
    ):
        self.win_matrix: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float),
        )
        self.models: set[str] = set()

    def add_comparison(
        self,
        model_a_key: str,
        model_b_key: str,
        outcome: int,
    ) -> None:
        if model_a_key == model_b_key:
            return

        self.models.add(
            model_a_key,
        )
        self.models.add(
            model_b_key,
        )

        if outcome > 0:
            self.win_matrix[model_a_key][model_b_key] += 1.0
            return
        if outcome < 0:
            self.win_matrix[model_b_key][model_a_key] += 1.0
            return

        self.win_matrix[model_a_key][model_b_key] += 0.5
        self.win_matrix[model_b_key][model_a_key] += 0.5

    def calculate_elo(
        self,
        *,
        iterations: int = 20,
        base_elo: int = 1200,
    ) -> dict[str, int]:
        if not self.models:
            return {}

        strengths = {model: 1.0 for model in self.models}
        for _ in range(iterations):
            updated_strengths: dict[str, float] = {}
            for model_i in self.models:
                wins_i = sum(
                    self.win_matrix[model_i].values(),
                )
                expected_denominator_sum = 0.0
                for model_j in self.models:
                    if model_i == model_j:
                        continue

                    games_ij = (
                        self.win_matrix[model_i][model_j]
                        + self.win_matrix[model_j][model_i]
                    )
                    if games_ij <= 0:
                        continue
                    expected_denominator_sum += games_ij / (
                        strengths[model_i] + strengths[model_j]
                    )

                if expected_denominator_sum > 0:
                    updated_strengths[model_i] = wins_i / expected_denominator_sum
                else:
                    updated_strengths[model_i] = strengths[model_i]

            average_strength = sum(
                updated_strengths.values(),
            ) / len(updated_strengths)
            strengths = {
                model: strength / average_strength
                for model, strength in updated_strengths.items()
            }

        elo_ratings = {}
        for model, strength in strengths.items():
            safe_strength = max(
                strength,
                1e-9,
            )
            elo_ratings[model] = round(
                base_elo + 400 * math.log10(safe_strength),
            )
        return elo_ratings
