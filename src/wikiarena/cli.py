from __future__ import annotations

import asyncio
import json
from enum import Enum
from pathlib import Path
from typing import Any

import typer

from wikiarena.eval import (
    BenchmarkRunner,
    RunResultStore,
    RunService,
    inspect_result_file_identity,
    load_eval_run_config,
    load_run_results,
    plan_benchmark_identity,
    summarize_run_results,
)
from wikiarena.protocol import (
    HarnessConfig,
    ResponseContract,
    RunResult,
    ScoringRules,
    SolverMode,
    WikiBackend,
)
from wikiarena.wiki_runtime import WikiRuntimeConfig

app = typer.Typer(
    help="WikiArena CLI",
    no_args_is_help=True,
)
eval_app = typer.Typer(
    help="Evaluation workflows",
    no_args_is_help=True,
)
app.add_typer(
    eval_app,
    name="eval",
)


class SummaryFormat(str, Enum):
    TABLE = "table"
    JSON = "json"
    MARKDOWN = "markdown"


class TieBreaker(str, Enum):
    FEWEST_MOVES_THEN_DRAW = "fewest_moves_then_draw"
    FEWEST_MOVES_THEN_FASTEST_MS = "fewest_moves_then_fastest_ms"


class ThinkingEffort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


class CliServices:
    def create_run_service(
        self,
    ) -> RunService:
        return RunService()

    def create_benchmark_runner(
        self,
    ) -> BenchmarkRunner:
        return BenchmarkRunner(
            run_service=self.create_run_service(),
        )


_CLI_SERVICES = CliServices()


def get_cli_services() -> CliServices:
    return _CLI_SERVICES


@app.command("run")
def run_command(
    model: str = typer.Option(
        ...,
        "--model",
        help="Model identifier",
    ),
    start: str = typer.Option(
        ...,
        "--start",
        help="Start page title",
    ),
    target: str = typer.Option(
        ...,
        "--target",
        help="Target page title",
    ),
    provider: str = typer.Option(
        "openai",
        "--provider",
        help="Provider name",
    ),
    language: str = typer.Option(
        "en",
        "--language",
        help="Wikipedia language edition",
    ),
    wiki_backend: WikiBackend = typer.Option(
        WikiBackend.LIVE,
        "--wiki-backend",
        help="Wikipedia backend mode",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Use the local graph backend instead of live Wikipedia",
    ),
    graph_path: Path | None = typer.Option(
        None,
        "--graph-path",
        help="Path to a local dated graph binary for graph backend",
    ),
    wiki_snapshot_id: str | None = typer.Option(
        None,
        "--wiki-snapshot-id",
        help="Optional snapshot identifier to record in artifacts",
    ),
    response_contract: ResponseContract = typer.Option(
        ResponseContract.TOOL_CALL_ONLY,
        "--response-contract",
        help="Benchmark response contract",
    ),
    tool_name: str = typer.Option(
        "navigate",
        "--tool-name",
        help="Navigation tool name for tool_call_only mode",
    ),
    solver: SolverMode = typer.Option(
        SolverMode.NONE,
        "--solver",
        help="Solver provenance mode",
    ),
    temperature: float | None = typer.Option(
        None,
        "--temperature",
        help="Sampling temperature",
    ),
    max_tokens: int | None = typer.Option(
        None,
        "--max-tokens",
        help="Maximum output tokens",
    ),
    reasoning_effort: str | None = typer.Option(
        None,
        "--reasoning-effort",
        help="Provider-specific reasoning effort hint",
    ),
    thinking_effort: ThinkingEffort | None = typer.Option(
        None,
        "--thinking-effort",
        help="Anthropic adaptive thinking effort level for supported models",
    ),
    thinking_budget_tokens: int | None = typer.Option(
        None,
        "--thinking-budget-tokens",
        help="Enable provider thinking mode with the given token budget when supported",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="Override provider base URL",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional JSONL output path",
    ),
    append: bool = typer.Option(
        False,
        "--append",
        help="Append to an existing output file",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Overwrite an existing output file",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print full JSON run result",
    ),
) -> None:
    run_service = get_cli_services().create_run_service()
    model_settings = _build_model_settings(
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        thinking_effort=thinking_effort,
        thinking_budget_tokens=thinking_budget_tokens,
        base_url=base_url,
    )
    request = run_service_request(
        model=model,
        provider=provider,
        start=start,
        target=target,
        language=language,
        wiki_runtime=_build_wiki_runtime_config(
            wiki_backend=wiki_backend,
            offline=offline,
            graph_path=graph_path,
            wiki_snapshot_id=wiki_snapshot_id,
        ),
        response_contract=response_contract,
        tool_name=tool_name,
        solver=solver,
        model_settings=model_settings,
    )
    run_plan = asyncio.run(
        run_service.plan_run(
            request,
        ),
    )
    _prepare_output_path(
        output,
        append=append,
        overwrite=overwrite,
        expected_ruleset_hash=run_plan.ruleset_hash,
        expected_wiki_backend=run_plan.wiki_runtime.backend,
        expected_wiki_snapshot_id=run_plan.wiki_snapshot_id,
    )

    artifact = asyncio.run(
        run_service.execute_plan(
            run_plan,
        ),
    )

    if output is not None:
        RunResultStore(
            output_path=output,
        ).append_artifact(
            artifact,
        )

    _print_run_result(
        artifact.run_result,
        json_output=json_output,
        output_path=output,
    )


@eval_app.command("run")
def eval_run_command(
    config: Path = typer.Option(
        ...,
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="Benchmark config path (.toml or .json)",
    ),
    output: Path = typer.Option(
        Path("wikiarena_eval_results.jsonl"),
        "--output",
        help="Run results JSONL output path",
    ),
    append: bool = typer.Option(
        False,
        "--append",
        help="Append to an existing output file",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Overwrite an existing output file",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print JSON summary",
    ),
    print_hashes: bool = typer.Option(
        False,
        "--print-hashes",
        help="Print ruleset/taskset hashes in table output",
    ),
    wiki_backend: WikiBackend | None = typer.Option(
        None,
        "--wiki-backend",
        help="Override wiki backend mode from config",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Override config to use the local graph backend",
    ),
    graph_path: Path | None = typer.Option(
        None,
        "--graph-path",
        help="Override config graph path",
    ),
    wiki_snapshot_id: str | None = typer.Option(
        None,
        "--wiki-snapshot-id",
        help="Override config snapshot identifier",
    ),
) -> None:
    loaded_config = load_eval_run_config(
        config,
    )
    services = get_cli_services()
    benchmark_runner = services.create_benchmark_runner()
    resolved_run_options = _override_benchmark_run_options(
        loaded_config.run_options,
        wiki_backend=wiki_backend,
        offline=offline,
        graph_path=graph_path,
        wiki_snapshot_id=wiki_snapshot_id,
    )
    protocol_version = _resolve_protocol_version_from_runner(
        benchmark_runner,
    )
    identity_plan = plan_benchmark_identity(
        loaded_config.benchmark_spec,
        protocol_version=protocol_version,
    )
    _prepare_output_path(
        output,
        append=append,
        overwrite=overwrite,
        expected_ruleset_hash=identity_plan.ruleset_hash,
        expected_wiki_backend=resolved_run_options.wiki_runtime.backend,
        expected_wiki_snapshot_id=resolved_run_options.wiki_snapshot_id,
    )
    result_store = RunResultStore(
        output_path=output,
    )

    artifact = asyncio.run(
        benchmark_runner.run_benchmark(
            loaded_config.benchmark_spec,
            concurrency=loaded_config.concurrency,
            run_options=resolved_run_options,
            result_store=result_store,
        ),
    )

    summary_payload = {
        "benchmark_id": artifact.benchmark_id,
        "total_runs": artifact.total_runs,
        "total_races": len(artifact.race_results),
        "ruleset_hash": identity_plan.ruleset_hash,
        "taskset_hash": identity_plan.taskset_hash,
        "output_path": str(output),
    }

    if json_output:
        typer.echo(
            json.dumps(
                summary_payload,
                indent=2,
                ensure_ascii=False,
            ),
        )
        return

    typer.echo(f"Benchmark completed: {artifact.benchmark_id}")
    typer.echo(f"Runs: {artifact.total_runs}")
    typer.echo(f"Races: {len(artifact.race_results)}")
    typer.echo(f"Results: {output}")
    if print_hashes:
        typer.echo(f"Ruleset hash: {identity_plan.ruleset_hash}")
        typer.echo(f"Taskset hash: {identity_plan.taskset_hash}")


@eval_app.command("summarize")
def eval_summarize_command(
    input_path: Path = typer.Option(
        ...,
        "--input",
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="Run results JSONL input path",
    ),
    format: SummaryFormat = typer.Option(
        SummaryFormat.TABLE,
        "--format",
        help="Summary output format",
    ),
    tie_breaker: TieBreaker = typer.Option(
        TieBreaker.FEWEST_MOVES_THEN_DRAW,
        "--tie-breaker",
        help="Pairwise comparison tie-breaker",
    ),
) -> None:
    run_results = load_run_results(
        input_path,
    )
    evaluation_summary = summarize_run_results(
        run_results,
        tie_breaker=tie_breaker.value,
    )

    if format == SummaryFormat.JSON:
        typer.echo(
            json.dumps(
                evaluation_summary.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            ),
        )
        return

    if format == SummaryFormat.MARKDOWN:
        typer.echo(
            _format_summary_markdown(
                evaluation_summary,
            ),
        )
        return

    typer.echo(
        _format_summary_table(
            evaluation_summary,
        ),
    )


def run_service_request(
    *,
    model: str,
    provider: str,
    start: str,
    target: str,
    language: str,
    wiki_runtime: WikiRuntimeConfig,
    response_contract: ResponseContract,
    tool_name: str,
    solver: SolverMode,
    model_settings: dict[str, Any],
):
    from wikiarena.eval import RunRequest

    return RunRequest(
        model_id=model,
        provider=provider,
        start_page_title=start,
        target_page_title=target,
        language=language,
        wiki_runtime=wiki_runtime,
        wiki_snapshot_id=wiki_runtime.snapshot_id,
        model_settings=model_settings,
        harness_config=HarnessConfig(
            harness_id=f"{response_contract.value}_v1",
            response_contract=response_contract,
            tool_name=tool_name,
        ),
        scoring_rules=ScoringRules(),
        solver_mode=solver,
    )


def _build_model_settings(
    *,
    temperature: float | None,
    max_tokens: int | None,
    reasoning_effort: str | None,
    thinking_effort: ThinkingEffort | None,
    thinking_budget_tokens: int | None,
    base_url: str | None,
) -> dict[str, Any]:
    model_settings: dict[str, Any] = {}
    if temperature is not None:
        model_settings["temperature"] = temperature
    if max_tokens is not None:
        model_settings["max_tokens"] = max_tokens
    if reasoning_effort is not None:
        model_settings["reasoning_effort"] = reasoning_effort
    if thinking_effort is not None and thinking_budget_tokens is not None:
        raise typer.BadParameter(
            "--thinking-effort and --thinking-budget-tokens are mutually exclusive",
        )
    if thinking_effort is not None:
        model_settings["thinking"] = {
            "type": "adaptive",
        }
        model_settings["output_config"] = {
            "effort": thinking_effort.value,
        }
    if thinking_budget_tokens is not None:
        model_settings["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget_tokens,
        }
    if base_url is not None:
        model_settings["provider_settings"] = {
            "base_url": base_url,
        }
    return model_settings


def _build_wiki_runtime_config(
    *,
    wiki_backend: WikiBackend,
    offline: bool,
    graph_path: Path | None,
    wiki_snapshot_id: str | None,
) -> WikiRuntimeConfig:
    resolved_backend = wiki_backend
    if offline:
        resolved_backend = WikiBackend.GRAPH

    return WikiRuntimeConfig(
        backend=resolved_backend,
        graph_path=graph_path,
        snapshot_id=wiki_snapshot_id,
    )


def _override_benchmark_run_options(
    run_options,
    *,
    wiki_backend: WikiBackend | None,
    offline: bool,
    graph_path: Path | None,
    wiki_snapshot_id: str | None,
):
    if (
        wiki_backend is None
        and not offline
        and graph_path is None
        and wiki_snapshot_id is None
    ):
        return run_options

    resolved_backend = wiki_backend or run_options.wiki_runtime.backend
    if offline:
        resolved_backend = WikiBackend.GRAPH

    resolved_graph_path = graph_path
    if resolved_graph_path is None:
        resolved_graph_path = run_options.wiki_runtime.graph_path

    resolved_snapshot_id = wiki_snapshot_id
    if resolved_snapshot_id is None:
        resolved_snapshot_id = run_options.wiki_runtime.snapshot_id

    updated_wiki_runtime = run_options.wiki_runtime.model_copy(
        update={
            "backend": resolved_backend,
            "graph_path": resolved_graph_path,
            "snapshot_id": resolved_snapshot_id,
        },
    )
    return run_options.model_copy(
        update={
            "wiki_runtime": updated_wiki_runtime,
            "wiki_snapshot_id": resolved_snapshot_id,
        },
    )


def _print_run_result(
    run_result: RunResult,
    *,
    json_output: bool,
    output_path: Path | None,
) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                run_result.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            ),
        )
        return

    typer.echo(f"Run completed: {run_result.run_id}")
    typer.echo(f"Outcome: {run_result.terminal_outcome.value}")
    typer.echo(f"Reason: {run_result.termination_reason.value}")
    typer.echo(f"Committed moves: {run_result.total_committed_moves}")
    typer.echo(f"Step attempts: {run_result.total_step_attempts}")
    if output_path is not None:
        typer.echo(f"Saved to: {output_path}")


def _prepare_output_path(
    output_path: Path | None,
    *,
    append: bool,
    overwrite: bool,
    expected_ruleset_hash: str | None = None,
    expected_wiki_backend: WikiBackend | None = None,
    expected_wiki_snapshot_id: str | None = None,
) -> None:
    if output_path is None:
        return

    if append and overwrite:
        raise typer.BadParameter(
            "--append and --overwrite are mutually exclusive",
        )

    if not output_path.exists():
        return

    if output_path.is_dir():
        raise typer.BadParameter(
            f"output path is a directory: {output_path}",
        )

    if overwrite:
        output_path.unlink()
        return

    if append:
        _validate_append_identity(
            output_path,
            expected_ruleset_hash=expected_ruleset_hash,
            expected_wiki_backend=expected_wiki_backend,
            expected_wiki_snapshot_id=expected_wiki_snapshot_id,
        )
        return

    raise typer.BadParameter(
        f"output path already exists: {output_path}. Use --append or --overwrite.",
    )


def _validate_append_identity(
    output_path: Path,
    *,
    expected_ruleset_hash: str | None,
    expected_wiki_backend: WikiBackend | None,
    expected_wiki_snapshot_id: str | None,
) -> None:
    if expected_ruleset_hash is None:
        return

    identity = inspect_result_file_identity(
        output_path,
    )
    if identity.total_runs == 0:
        return

    if not identity.ruleset_hashes:
        raise typer.BadParameter(
            f"existing output file has no ruleset_hash values: {output_path}",
        )

    if len(identity.ruleset_hashes) > 1:
        raise typer.BadParameter(
            f"existing output file contains multiple ruleset hashes: {output_path}",
        )

    existing_ruleset_hash = identity.ruleset_hashes[0]
    if existing_ruleset_hash != expected_ruleset_hash:
        raise typer.BadParameter(
            "cannot append to output file with a different ruleset_hash",
        )

    if expected_wiki_backend is not None:
        existing_wiki_backends = identity.wiki_backends
        if existing_wiki_backends and existing_wiki_backends != [
            expected_wiki_backend.value,
        ]:
            raise typer.BadParameter(
                "cannot append to output file with a different wiki_backend",
            )

    if expected_wiki_snapshot_id is not None:
        existing_snapshot_ids = identity.wiki_snapshot_ids
        if existing_snapshot_ids and existing_snapshot_ids != [
            expected_wiki_snapshot_id,
        ]:
            raise typer.BadParameter(
                "cannot append to output file with a different wiki_snapshot_id",
            )


def _format_summary_table(
    evaluation_summary,
) -> str:
    lines = [
        f"Runs: {evaluation_summary.total_runs}",
        f"Races: {evaluation_summary.total_races}",
        f"Rulesets: {', '.join(evaluation_summary.ruleset_hashes) or 'n/a'}",
        f"Tasksets: {', '.join(evaluation_summary.taskset_hashes) or 'n/a'}",
        "",
        "participant_id | elo | successes | eligible | wins | losses | draws | avg_moves_success",
        "--- | --- | --- | --- | --- | --- | --- | ---",
    ]
    for participant_summary in evaluation_summary.participants:
        avg_moves = (
            f"{participant_summary.average_committed_moves_on_success:.2f}"
            if participant_summary.average_committed_moves_on_success is not None
            else "-"
        )
        lines.append(
            " | ".join(
                [
                    participant_summary.participant_id,
                    str(participant_summary.elo or "-"),
                    str(participant_summary.successes),
                    str(participant_summary.ranking_eligible_runs),
                    f"{participant_summary.pairwise_wins:.1f}",
                    f"{participant_summary.pairwise_losses:.1f}",
                    f"{participant_summary.pairwise_draws:.1f}",
                    avg_moves,
                ],
            ),
        )
    return "\n".join(lines)


def _format_summary_markdown(
    evaluation_summary,
) -> str:
    return _format_summary_table(
        evaluation_summary,
    )


def _resolve_protocol_version_from_runner(
    benchmark_runner: BenchmarkRunner,
) -> str:
    run_service = getattr(
        benchmark_runner,
        "run_service",
        None,
    )
    if run_service is None:
        return "1.0.0-draft"

    run_executor = getattr(
        run_service,
        "run_executor",
        None,
    )
    if run_executor is None:
        return "1.0.0-draft"

    protocol_version = getattr(
        run_executor,
        "protocol_version",
        None,
    )
    if (
        isinstance(
            protocol_version,
            str,
        )
        and protocol_version
    ):
        return protocol_version
    return "1.0.0-draft"


def main() -> None:
    app()


if __name__ == "__main__":
    main()
