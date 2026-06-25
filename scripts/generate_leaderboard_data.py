from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from wikiarena.eval import load_run_results, summarize_run_results

DISPLAY_NAMES = {
    "gpt_5_5": "GPT-5.5",
    "claude_sonnet_4_6": "Claude Sonnet 4.6",
    "gpt_5_4_xhigh": "GPT-5.4 xhigh",
    "claude_opus_4_6_max": "Claude Opus 4.6 max",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate static frontend leaderboard data from eval results JSONL.",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--benchmark-id", default="wikiarena_v0")
    parser.add_argument("--snapshot-id", default="enwiki-20260401")
    parser.add_argument("--artifact-dir", default="artifacts/wikiarena/v0")
    parser.add_argument(
        "--unsolved-pair-policy",
        choices=("skip", "draw"),
        default="skip",
        help="How to score ranking-eligible pairs where neither run solved the task.",
    )
    parser.add_argument(
        "--exclude-participant",
        "--hide-participant",
        action="append",
        default=[],
        dest="excluded_participants",
        help="Participant id to omit from public leaderboard ranking and metrics.",
    )
    args = parser.parse_args()

    all_run_results = load_run_results(args.input)
    excluded_participants = set(args.excluded_participants)
    run_results = [
        run_result
        for run_result in all_run_results
        if run_result.participant_id not in excluded_participants
    ]
    summary = summarize_run_results(
        run_results,
        unsolved_pair_policy=args.unsolved_pair_policy,
    )
    cost_by_participant: dict[str, float] = {}
    latency_by_participant: dict[str, float] = {}
    step_attempts_by_participant: dict[str, int] = {}
    invalid_attempts_by_participant: dict[str, int] = {}

    for run_result in run_results:
        run_result_payload = run_result.model_dump(mode="python")
        cost_by_participant[run_result.participant_id] = (
            cost_by_participant.get(run_result.participant_id, 0.0)
            + _run_estimated_cost_usd(run_result_payload)
        )
        latency_by_participant[run_result.participant_id] = (
            latency_by_participant.get(run_result.participant_id, 0.0)
            + _run_model_response_time_ms(run_result_payload)
        )
        step_attempts_by_participant[run_result.participant_id] = (
            step_attempts_by_participant.get(run_result.participant_id, 0)
            + run_result.total_step_attempts
        )
        invalid_attempts_by_participant[run_result.participant_id] = (
            invalid_attempts_by_participant.get(run_result.participant_id, 0)
            + run_result.total_invalid_attempts
        )

    participants: list[dict[str, Any]] = []
    for participant in summary.participants:
        total_cost = cost_by_participant.get(participant.participant_id, 0.0)
        total_latency = latency_by_participant.get(participant.participant_id, 0.0)
        total_step_attempts = step_attempts_by_participant.get(
            participant.participant_id,
            0,
        )
        total_invalid_attempts = invalid_attempts_by_participant.get(
            participant.participant_id,
            0,
        )
        cost_per_success = (
            total_cost / participant.successes if participant.successes > 0 else None
        )
        participants.append(
            {
                "participantId": participant.participant_id,
                "displayName": DISPLAY_NAMES.get(
                    participant.participant_id,
                    participant.participant_id,
                ),
                "runs": participant.runs,
                "rankingEligibleRuns": participant.ranking_eligible_runs,
                "successes": participant.successes,
                "modelFailures": participant.model_failures,
                "systemFailures": participant.system_failures,
                "totalEstimatedCostUsd": total_cost,
                "estimatedCostUsdPerSuccess": cost_per_success,
                "totalStepAttempts": total_step_attempts,
                "totalInvalidAttempts": total_invalid_attempts,
                "stepErrorRate": (
                    total_invalid_attempts / total_step_attempts
                    if total_step_attempts > 0
                    else None
                ),
                "totalModelResponseTimeMs": total_latency,
                "pairwiseWins": participant.pairwise_wins,
                "pairwiseLosses": participant.pairwise_losses,
                "pairwiseDraws": participant.pairwise_draws,
                "pairwiseSkipped": participant.pairwise_skipped,
                "elo": participant.elo,
            },
        )

    payload = {
        "benchmarkId": args.benchmark_id,
        "snapshotId": args.snapshot_id,
        "sourcePath": str(args.input),
        "artifactDir": args.artifact_dir,
        "generatedFromRuns": len(all_run_results),
        "rankedFromRuns": summary.total_runs,
        "totalRaces": summary.total_races,
        "excludedParticipants": sorted(
            excluded_participants,
        ),
        "scoringPolicy": {
            "tieBreaker": summary.tie_breaker,
            "unsolvedPairPolicy": summary.unsolved_pair_policy,
        },
        "pairwiseComparisons": summary.pairwise_comparisons,
        "pairwiseSkippedComparisons": summary.pairwise_skipped_comparisons,
        "rulesetHashes": summary.ruleset_hashes,
        "tasksetHashes": summary.taskset_hashes,
        "participants": participants,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _run_estimated_cost_usd(run_result: dict[str, Any]) -> float:
    direct_cost = run_result.get("estimated_cost_usd")
    if isinstance(direct_cost, int | float):
        return float(direct_cost)

    total = 0.0
    for step_attempt in run_result.get("step_attempts", []):
        if not isinstance(step_attempt, dict):
            continue
        model_metrics = step_attempt.get("model_metrics")
        if not isinstance(model_metrics, dict):
            continue
        step_cost = model_metrics.get("estimated_cost_usd")
        if isinstance(step_cost, int | float):
            total += float(step_cost)
    return total


def _run_model_response_time_ms(run_result: dict[str, Any]) -> float:
    total = 0.0
    for step_attempt in run_result.get("step_attempts", []):
        if not isinstance(step_attempt, dict):
            continue
        model_metrics = step_attempt.get("model_metrics")
        if not isinstance(model_metrics, dict):
            continue
        response_time_ms = model_metrics.get("response_time_ms")
        if isinstance(response_time_ms, int | float):
            total += float(response_time_ms)
    return total


if __name__ == "__main__":
    main()
