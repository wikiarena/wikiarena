from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from wikiarena.eval import load_run_results, summarize_run_results
from wikiarena.eval.summary import compare_run_results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate static frontend manifest for benchmark race replays.",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    run_results = load_run_results(args.input)
    summary = summarize_run_results(run_results)
    elo_by_participant = {
        participant.participant_id: participant.elo
        for participant in summary.participants
    }
    runs_by_race = defaultdict(list)
    for run_result in run_results:
        runs_by_race[run_result.race_id].append(run_result)

    races = []
    for race_id, race_run_results in sorted(runs_by_race.items()):
        race_metadata_path = args.artifact_dir / "races" / race_id / "race.json"
        if not race_metadata_path.exists():
            continue
        metadata = json.loads(race_metadata_path.read_text(encoding="utf-8"))
        run_by_id = {run_result.run_id: run_result for run_result in race_run_results}
        participants = []
        run_payloads = {
            run_result.run_id: run_result.model_dump(mode="python")
            for run_result in race_run_results
        }
        for participant in metadata.get("participants", []):
            run_result = run_by_id.get(participant.get("run_id"))
            if run_result is None:
                continue
            participants.append(
                {
                    "participantId": participant["participant_id"],
                    "displayName": participant["display_name"],
                    "runId": participant["run_id"],
                    "terminalOutcome": run_result.terminal_outcome.value,
                    "committedMoves": run_result.total_committed_moves,
                    "scoreMoves": _score_moves(run_result.model_dump(mode="python")),
                    "scoreLabel": _score_label(run_result.model_dump(mode="python")),
                    "invalidAttempts": run_result.total_invalid_attempts,
                    "estimatedCostUsd": _run_estimated_cost_usd(
                        run_payloads[run_result.run_id],
                    ),
                    "elo": elo_by_participant.get(run_result.participant_id),
                },
            )

        winner_participant_id = _winner_participant_id(race_run_results)
        optimal_moves = _optimal_moves(run_payloads.values())
        winner = _participant_by_id(participants, winner_participant_id)
        loser = _loser_participant(participants, winner_participant_id)
        margin = _victory_margin(winner, loser)

        races.append(
            {
                "raceId": race_id,
                "taskId": metadata.get("task_id"),
                "startTitle": metadata.get("start_title"),
                "targetTitle": metadata.get("target_title"),
                "optimalMoves": optimal_moves,
                "winnerParticipantId": winner_participant_id,
                "victoryMarginMoves": margin,
                "participants": participants,
            },
        )

    payload = {
        "sourcePath": str(args.input),
        "artifactDir": str(args.artifact_dir),
        "totalRaces": len(races),
        "races": races,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _winner_participant_id(race_run_results: list[Any]) -> str | None:
    eligible = [run_result for run_result in race_run_results if run_result.ranking_eligible]
    if len(eligible) != 2:
        return None
    outcome = compare_run_results(
        eligible[0],
        eligible[1],
        tie_breaker="fewest_moves_then_draw",
    )
    if outcome > 0:
        return eligible[0].participant_id
    if outcome < 0:
        return eligible[1].participant_id
    return None


def _participant_by_id(
    participants: list[dict[str, Any]],
    participant_id: str | None,
) -> dict[str, Any] | None:
    if participant_id is None:
        return None
    return next(
        (
            participant
            for participant in participants
            if participant["participantId"] == participant_id
        ),
        None,
    )


def _loser_participant(
    participants: list[dict[str, Any]],
    winner_participant_id: str | None,
) -> dict[str, Any] | None:
    if winner_participant_id is None:
        return None
    return next(
        (
            participant
            for participant in participants
            if participant["participantId"] != winner_participant_id
        ),
        None,
    )


def _victory_margin(
    winner: dict[str, Any] | None,
    loser: dict[str, Any] | None,
) -> int | None:
    if winner is None or loser is None:
        return None
    return int(loser["scoreMoves"] - winner["scoreMoves"])


def _score_moves(run_result: dict[str, Any]) -> int:
    if run_result.get("terminal_outcome") == "success":
        return int(run_result.get("total_committed_moves") or 0)
    return max(
        50,
        int(run_result.get("total_step_attempts") or 0),
        int(run_result.get("total_committed_moves") or 0),
    )


def _score_label(run_result: dict[str, Any]) -> str:
    if run_result.get("terminal_outcome") == "success":
        return str(run_result.get("total_committed_moves") or 0)
    return "F"


def _optimal_moves(run_results: Any) -> int | None:
    for run_result in run_results:
        for step_attempt in run_result.get("step_attempts", []):
            if not isinstance(step_attempt, dict):
                continue
            solver_metrics = step_attempt.get("solver_metrics")
            if not isinstance(solver_metrics, dict):
                continue
            distance_before = solver_metrics.get("distance_before")
            if isinstance(distance_before, int):
                return distance_before
    return None


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


if __name__ == "__main__":
    main()
