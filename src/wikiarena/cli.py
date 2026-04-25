from __future__ import annotations

import asyncio
import json
import random
from enum import Enum
from pathlib import Path
from typing import Any

import typer

from wikiarena.adapters.participants import ProviderParticipant
from wikiarena.cli_output import (
    EvalProgressReporter,
    RunTraceRenderer,
    build_error_summary_lines,
    build_stderr_console,
)
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
from wikiarena.graph import install_graph_release, load_graph_info
from wikiarena.protocol import (
    EventEnvelope,
    HarnessConfig,
    NavigationBackend,
    ResponseContract,
    RunEventType,
    RunResult,
    ScoringRules,
    SolverBackend,
    StepAttemptRecord,
)
from wikiarena.solver.binary import MappedBinarySolverGraph
from wikiarena.solver.models import PositionSolverFacts
from wikiarena.solver_runtime import SolverRuntimeConfig, resolve_solver_graph_file_path
from wikiarena.wiki_runtime import NavigationRuntimeConfig, resolve_graph_file_path
from wikiarena.wikipedia import LiveWikiService

app = typer.Typer(
    help="WikiArena CLI",
    no_args_is_help=True,
)
graph_app = typer.Typer(
    help="Graph installation workflows",
    no_args_is_help=True,
)
eval_app = typer.Typer(
    help="Evaluation workflows",
    no_args_is_help=True,
)
app.add_typer(
    graph_app,
    name="graph",
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


class OpenAIReasoningSummary(str, Enum):
    AUTO = "auto"
    CONCISE = "concise"
    DETAILED = "detailed"


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


@graph_app.command("install")
def graph_install_command(
    tag: str | None = typer.Option(
        None,
        "--tag",
        help="Specific published graph release tag to install",
    ),
    repo: str = typer.Option(
        "wikiarena/wikiarena",
        "--repo",
        help="GitHub repository containing published graph releases",
    ),
    install_dir: Path | None = typer.Option(
        None,
        "--install-dir",
        help="Directory where installed dated graph binaries are stored",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Reinstall even if the matching graph is already installed",
    ),
) -> None:
    install_result = install_graph_release(
        repo=repo,
        tag=tag,
        install_dir=install_dir,
        force=force,
    )
    if install_result.already_installed:
        typer.echo("Graph already installed.")
    else:
        typer.echo("Graph installed.")
    typer.echo(f"Release tag: {install_result.release_tag}")
    typer.echo(f"Installed graph: {install_result.graph_path}")
    typer.echo(f"Installed metadata: {install_result.metadata_path}")
    if install_result.snapshot_id is not None:
        typer.echo(f"Snapshot id: {install_result.snapshot_id}")
    typer.echo(f"Nodes: {install_result.node_count}")
    typer.echo(f"Edges: {install_result.edge_count}")


@graph_app.command("info")
def graph_info_command(
    graph_path: Path | None = typer.Option(
        None,
        "--graph-path",
        help="Path to a local dated graph binary to inspect",
    ),
    verify: bool = typer.Option(
        False,
        "--verify",
        help="Verify the graph file against its metadata sidecar",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print graph info as JSON",
    ),
) -> None:
    graph_info = load_graph_info(
        graph_path=graph_path,
        verify=verify,
    )
    if json_output:
        typer.echo(
            json.dumps(
                graph_info.to_dict(),
                indent=2,
            ),
        )
        return

    typer.echo(f"Active graph: {graph_info.graph_path}")
    typer.echo(f"Selected via: {graph_info.selected_via}")
    if graph_info.release_tag is not None:
        typer.echo(f"Release tag: {graph_info.release_tag}")
    if graph_info.snapshot_id is not None:
        typer.echo(f"Snapshot id: {graph_info.snapshot_id}")
    if graph_info.wiki is not None:
        typer.echo(f"Wiki: {graph_info.wiki}")
    if graph_info.dump_date is not None:
        typer.echo(f"Dump date: {graph_info.dump_date}")
    typer.echo(f"Nodes: {graph_info.node_count}")
    typer.echo(f"Edges: {graph_info.edge_count}")
    typer.echo(f"File size bytes: {graph_info.file_size_bytes}")
    if graph_info.metadata_present:
        typer.echo(f"Metadata: {graph_info.metadata_path}")
    else:
        typer.echo(f"Metadata: not found at {graph_info.metadata_path}")
    if graph_info.metadata_generated_at_utc is not None:
        typer.echo(f"Metadata generated at: {graph_info.metadata_generated_at_utc}")
    if graph_info.metadata_git_sha is not None:
        typer.echo(f"Metadata git sha: {graph_info.metadata_git_sha}")
    typer.echo(f"Verified: {'yes' if graph_info.verified else 'no'}")
    if graph_info.graph_sha256 is not None:
        typer.echo(f"Graph sha256: {graph_info.graph_sha256}")


@app.command("run")
def run_command(
    model: str = typer.Option(
        ...,
        "--model",
        help="Model identifier",
    ),
    start: str | None = typer.Option(
        None,
        "--start",
        help="Start page title; omit together with --target to choose a random task",
    ),
    target: str | None = typer.Option(
        None,
        "--target",
        help="Target page title; omit together with --start to choose a random task",
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
    navigation_backend: NavigationBackend | None = typer.Option(
        None,
        "--navigation-backend",
        help="Navigation backend mode; defaults to graph when a graph is available, otherwise live",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Alias for --navigation-backend graph",
    ),
    navigation_graph_path: Path | None = typer.Option(
        None,
        "--navigation-graph-path",
        help="Path to a local graph snapshot for navigation; implies graph navigation backend unless live is explicit",
    ),
    navigation_snapshot_id: str | None = typer.Option(
        None,
        "--navigation-snapshot-id",
        help="Optional navigation snapshot identifier to record in artifacts",
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
    solver_backend: SolverBackend | None = typer.Option(
        None,
        "--solver-backend",
        help="Solver backend mode; defaults to local when a graph is installed, otherwise none",
    ),
    solver_graph_path: Path | None = typer.Option(
        None,
        "--solver-graph-path",
        help="Path to a local graph snapshot for the local graph solver",
    ),
    solver_snapshot_id: str | None = typer.Option(
        None,
        "--solver-snapshot-id",
        help="Optional solver snapshot identifier to record in artifacts",
    ),
    solver_endpoint: str | None = typer.Option(
        None,
        "--solver-endpoint",
        help="Remote solver endpoint when --solver-backend remote is selected",
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
    openai_use_responses_api: bool = typer.Option(
        False,
        "--openai-use-responses-api/--openai-use-chat-completions",
        help="Use the OpenAI Responses API for openai_compatible providers; provider openai already uses Responses by default",
    ),
    openai_reasoning_summary: OpenAIReasoningSummary | None = typer.Option(
        None,
        "--openai-reasoning-summary",
        help="Include an OpenAI reasoning summary when using the Responses API",
    ),
    openai_include_encrypted_reasoning: bool = typer.Option(
        False,
        "--openai-include-encrypted-reasoning/--no-openai-include-encrypted-reasoning",
        help="Request encrypted OpenAI reasoning items in Responses API output",
    ),
    openai_use_previous_response_id: bool = typer.Option(
        True,
        "--openai-use-previous-response-id/--openai-no-previous-response-id",
        help="Continue OpenAI Responses turns with previous_response_id instead of replaying the full message history",
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
    trace: bool = typer.Option(
        False,
        "--trace",
        help="Print an incremental request/response transcript to stderr",
    ),
) -> None:
    run_service = get_cli_services().create_run_service()
    trace_renderer = None
    event_sink = None
    if trace:
        trace_renderer = RunTraceRenderer(
            console=build_stderr_console(),
        )
        run_service = _build_traced_run_service(
            run_service,
            trace_renderer,
        )
        event_sink = _build_single_run_trace_event_sink(
            trace_renderer,
        )
    model_settings = _build_model_settings(
        provider=provider,
        trace=trace,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        thinking_effort=thinking_effort,
        thinking_budget_tokens=thinking_budget_tokens,
        openai_use_responses_api=openai_use_responses_api,
        openai_reasoning_summary=openai_reasoning_summary,
        openai_include_encrypted_reasoning=openai_include_encrypted_reasoning,
        openai_use_previous_response_id=openai_use_previous_response_id,
        base_url=base_url,
    )
    navigation_runtime = _build_navigation_runtime_config(
        navigation_backend=navigation_backend,
        offline=offline,
        navigation_graph_path=navigation_graph_path,
        navigation_snapshot_id=navigation_snapshot_id,
    )
    resolved_start, resolved_target, used_random_titles = _resolve_run_titles(
        start=start,
        target=target,
        language=language,
        navigation_runtime=navigation_runtime,
    )
    if used_random_titles:
        typer.echo(
            f"Random task: {resolved_start} -> {resolved_target}",
            err=True,
        )

    request = run_service_request(
        model=model,
        provider=provider,
        start=resolved_start,
        target=resolved_target,
        language=language,
        navigation_runtime=navigation_runtime,
        solver_runtime=_build_solver_runtime_config(
            solver_backend=solver_backend,
            solver_graph_path=solver_graph_path,
            solver_snapshot_id=solver_snapshot_id,
            solver_endpoint=solver_endpoint,
        ),
        navigation_snapshot_id=navigation_snapshot_id,
        solver_snapshot_id=solver_snapshot_id,
        response_contract=response_contract,
        tool_name=tool_name,
        model_settings=model_settings,
    )
    run_plan = asyncio.run(
        run_service.plan_run(
            request,
        ),
    )
    if trace_renderer is not None:
        trace_renderer.defer_page_context_solver_facts = (
            run_plan.solver_runtime.backend == SolverBackend.LOCAL
        )
    _prepare_output_path(
        output,
        append=append,
        overwrite=overwrite,
        expected_ruleset_hash=run_plan.ruleset_hash,
        expected_navigation_backend=run_plan.navigation_runtime.backend,
        expected_navigation_snapshot_id=run_plan.navigation_snapshot_id,
        expected_solver_backend=run_plan.solver_runtime.backend,
        expected_solver_snapshot_id=run_plan.solver_snapshot_id,
    )

    artifact = asyncio.run(
        run_service.execute_plan(
            run_plan,
            event_sink=event_sink,
        ),
    )

    if trace_renderer is not None:
        trace_renderer.after_run_result(
            artifact.run_result,
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
    quiet: bool = typer.Option(
        False,
        "--quiet",
        help="Suppress progress logs on stderr",
    ),
    navigation_backend: NavigationBackend | None = typer.Option(
        None,
        "--navigation-backend",
        help="Override navigation backend mode from config",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Override config to use the graph navigation backend",
    ),
    navigation_graph_path: Path | None = typer.Option(
        None,
        "--navigation-graph-path",
        help="Override config navigation graph path; implies graph navigation backend unless live is explicit",
    ),
    navigation_snapshot_id: str | None = typer.Option(
        None,
        "--navigation-snapshot-id",
        help="Override config navigation snapshot identifier",
    ),
    solver_backend: SolverBackend | None = typer.Option(
        None,
        "--solver-backend",
        help="Override solver backend mode from config",
    ),
    solver_graph_path: Path | None = typer.Option(
        None,
        "--solver-graph-path",
        help="Override config local graph solver path",
    ),
    solver_snapshot_id: str | None = typer.Option(
        None,
        "--solver-snapshot-id",
        help="Override config solver snapshot identifier",
    ),
    solver_endpoint: str | None = typer.Option(
        None,
        "--solver-endpoint",
        help="Override config remote solver endpoint",
    ),
) -> None:
    loaded_config = load_eval_run_config(
        config,
    )
    services = get_cli_services()
    benchmark_runner = services.create_benchmark_runner()
    resolved_run_options = _override_benchmark_run_options(
        loaded_config.run_options,
        navigation_backend=navigation_backend,
        offline=offline,
        navigation_graph_path=navigation_graph_path,
        navigation_snapshot_id=navigation_snapshot_id,
        solver_backend=solver_backend,
        solver_graph_path=solver_graph_path,
        solver_snapshot_id=solver_snapshot_id,
        solver_endpoint=solver_endpoint,
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
        expected_navigation_backend=resolved_run_options.navigation_runtime.backend,
        expected_navigation_snapshot_id=resolved_run_options.navigation_snapshot_id,
        expected_solver_backend=resolved_run_options.solver_runtime.backend,
        expected_solver_snapshot_id=resolved_run_options.solver_snapshot_id,
    )
    result_store = RunResultStore(
        output_path=output,
    )
    progress_reporter = None
    if not quiet and not json_output:
        progress_reporter = EvalProgressReporter(
            console=build_stderr_console(),
            total_runs=(
                len(loaded_config.benchmark_spec.tasks)
                * len(loaded_config.benchmark_spec.participants)
            ),
            total_races=len(
                loaded_config.benchmark_spec.tasks,
            ),
            participant_count=len(
                loaded_config.benchmark_spec.participants,
            ),
        )
        progress_reporter.print_start(
            benchmark_id=loaded_config.benchmark_spec.benchmark_id,
            participant_ids=[
                participant.participant_id
                for participant in loaded_config.benchmark_spec.participants
            ],
            navigation_backend=resolved_run_options.navigation_runtime.backend.value,
            solver_backend=resolved_run_options.solver_runtime.backend.value,
        )

    artifact = asyncio.run(
        benchmark_runner.run_benchmark(
            loaded_config.benchmark_spec,
            concurrency=loaded_config.concurrency,
            run_options=resolved_run_options,
            result_store=result_store,
            event_sink=(
                progress_reporter.handle_event
                if progress_reporter is not None
                else None
            ),
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
    navigation_runtime: NavigationRuntimeConfig,
    solver_runtime: SolverRuntimeConfig,
    navigation_snapshot_id: str | None,
    solver_snapshot_id: str | None,
    response_contract: ResponseContract,
    tool_name: str,
    model_settings: dict[str, Any],
):
    from wikiarena.eval import RunRequest

    return RunRequest(
        model_id=model,
        provider=provider,
        start_page_title=start,
        target_page_title=target,
        language=language,
        navigation_runtime=navigation_runtime,
        solver_runtime=solver_runtime,
        navigation_snapshot_id=(
            navigation_snapshot_id
            if navigation_snapshot_id is not None
            else navigation_runtime.snapshot_id
        ),
        solver_snapshot_id=(
            solver_snapshot_id
            if solver_snapshot_id is not None
            else solver_runtime.snapshot_id
        ),
        model_settings=model_settings,
        harness_config=HarnessConfig(
            harness_id=f"{response_contract.value}_v1",
            response_contract=response_contract,
            tool_name=tool_name,
        ),
        scoring_rules=ScoringRules(),
    )


def _build_traced_run_service(
    run_service: RunService,
    trace_renderer: RunTraceRenderer,
) -> RunService:
    if not isinstance(
        run_service,
        RunService,
    ):
        return run_service

    base_participant_factory = run_service.participant_factory

    def traced_participant_factory(participant_spec):
        participant_driver = base_participant_factory(
            participant_spec,
        )
        if isinstance(
            participant_driver,
            ProviderParticipant,
        ):
            participant_driver.trace_sink = trace_renderer
        return participant_driver

    return RunService(
        participant_factory=traced_participant_factory,
        wiki_navigator_factory=run_service.wiki_navigator_factory,
        solver_shortest_path_oracle=run_service.solver_shortest_path_oracle,
        run_executor=run_service.run_executor,
    )


def _build_single_run_trace_event_sink(
    trace_renderer: RunTraceRenderer,
):
    def handle_event(event: EventEnvelope) -> None:
        if event.event_type == RunEventType.STEP_ATTEMPT_RECORDED:
            step_attempt = StepAttemptRecord.model_validate(
                event.payload,
            )
            trace_renderer.after_step_attempt(
                step_attempt,
            )
            return

        if event.event_type == RunEventType.POSITION_SOLVER_FACTS_RECORDED:
            solver_facts_payload = event.payload.get(
                "solver_facts",
            )
            if isinstance(
                solver_facts_payload,
                dict,
            ):
                trace_renderer.record_position_solver_facts(
                    PositionSolverFacts.model_validate(
                        solver_facts_payload,
                    ),
                    event_sequence=event.sequence,
                    step_index=_optional_int_payload(
                        event.payload.get(
                            "step_index",
                        ),
                    ),
                    move_index=_optional_int_payload(
                        event.payload.get(
                            "move_index",
                        ),
                    ),
                )

    return handle_event


def _optional_int_payload(
    value: object,
) -> int | None:
    if isinstance(
        value,
        int,
    ):
        return value
    return None


def _resolve_run_titles(
    *,
    start: str | None,
    target: str | None,
    language: str,
    navigation_runtime: NavigationRuntimeConfig,
) -> tuple[str, str, bool]:
    if start is not None and target is not None:
        return start, target, False

    if (start is None) != (target is None):
        raise typer.BadParameter(
            "provide both --start and --target, or omit both to choose a random task",
        )

    try:
        if navigation_runtime.backend == NavigationBackend.GRAPH:
            random_start, random_target = _select_random_graph_titles(
                navigation_runtime.graph_path,
            )
        else:
            random_start, random_target = asyncio.run(
                _select_random_live_titles(
                    language,
                ),
            )
    except Exception as error:
        raise typer.BadParameter(
            f"could not choose random start/target titles: {error}",
        ) from error

    return random_start, random_target, True


async def _select_random_live_titles(
    language: str,
) -> tuple[str, str]:
    wiki_service = LiveWikiService(
        language=language,
    )
    candidate_titles: list[str] = []
    for _ in range(3):
        candidate_titles.extend(
            await wiki_service.get_random_pages(
                count=8,
            ),
        )
        distinct_titles = _dedupe_titles_preserving_order(
            candidate_titles,
        )
        if len(distinct_titles) >= 2:
            return distinct_titles[0], distinct_titles[1]

    raise ValueError(
        "wikipedia did not return two distinct random article titles",
    )


def _select_random_graph_titles(
    graph_path: Path | None,
) -> tuple[str, str]:
    resolved_graph_path = resolve_graph_file_path(
        graph_path,
    )
    with MappedBinarySolverGraph(
        file_path=resolved_graph_path,
    ) as graph:
        if graph.node_count < 2:
            raise ValueError(
                "graph snapshot contains fewer than two pages",
            )
        start_node_id, target_node_id = random.sample(
            range(graph.node_count),
            k=2,
        )
        return (
            graph.title_for_node_id(start_node_id),
            graph.title_for_node_id(target_node_id),
        )


def _dedupe_titles_preserving_order(
    titles: list[str],
) -> list[str]:
    seen_titles: set[str] = set()
    deduped_titles: list[str] = []
    for title in titles:
        if title in seen_titles:
            continue
        seen_titles.add(
            title,
        )
        deduped_titles.append(
            title,
        )
    return deduped_titles


def _build_model_settings(
    *,
    provider: str,
    trace: bool,
    temperature: float | None,
    max_tokens: int | None,
    reasoning_effort: str | None,
    thinking_effort: ThinkingEffort | None,
    thinking_budget_tokens: int | None,
    openai_use_responses_api: bool,
    openai_reasoning_summary: OpenAIReasoningSummary | None,
    openai_include_encrypted_reasoning: bool,
    openai_use_previous_response_id: bool,
    base_url: str | None,
) -> dict[str, Any]:
    model_settings: dict[str, Any] = {}
    normalized_provider = provider.strip().lower()
    openai_provider = normalized_provider in {
        "openai",
        "openai_compatible",
    }
    openai_responses_flags = (
        openai_use_responses_api
        or openai_reasoning_summary is not None
        or openai_include_encrypted_reasoning
    )
    if temperature is not None:
        model_settings["temperature"] = temperature
    if max_tokens is not None:
        model_settings["max_tokens"] = max_tokens
    resolved_reasoning_effort = reasoning_effort
    if resolved_reasoning_effort is None and normalized_provider in {
        "codex",
        "openai",
        "openai_compatible",
        "openrouter",
    }:
        resolved_reasoning_effort = "high"
    if resolved_reasoning_effort is not None:
        model_settings["reasoning_effort"] = resolved_reasoning_effort
    if thinking_effort is not None and thinking_budget_tokens is not None:
        raise typer.BadParameter(
            "--thinking-effort and --thinking-budget-tokens are mutually exclusive",
        )
    resolved_thinking_effort = thinking_effort
    if (
        trace
        and normalized_provider == "anthropic"
        and resolved_thinking_effort is None
        and thinking_budget_tokens is None
    ):
        resolved_thinking_effort = ThinkingEffort.HIGH
    if resolved_thinking_effort is not None:
        model_settings["thinking"] = {
            "type": "adaptive",
        }
        model_settings["output_config"] = {
            "effort": resolved_thinking_effort.value,
        }
    if thinking_budget_tokens is not None:
        model_settings["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget_tokens,
        }
    if normalized_provider == "openai":
        model_settings["openai_api_mode"] = "responses"
        model_settings["openai_use_previous_response_id"] = (
            openai_use_previous_response_id
        )
    elif openai_responses_flags:
        if not openai_provider:
            raise typer.BadParameter(
                "OpenAI Responses API options require --provider openai or --provider openai_compatible",
            )
        model_settings["openai_api_mode"] = "responses"
        model_settings["openai_use_previous_response_id"] = (
            openai_use_previous_response_id
        )
    resolved_openai_reasoning_summary = openai_reasoning_summary
    if (
        trace
        and resolved_openai_reasoning_summary is None
        and (
            normalized_provider == "openai"
            or (
                openai_provider
                and (
                    openai_use_responses_api
                    or openai_include_encrypted_reasoning
                )
            )
        )
    ):
        resolved_openai_reasoning_summary = OpenAIReasoningSummary.DETAILED
    if resolved_openai_reasoning_summary is not None:
        model_settings["openai_reasoning_summary"] = (
            resolved_openai_reasoning_summary.value
        )
    if openai_include_encrypted_reasoning:
        model_settings["openai_include_encrypted_reasoning"] = True
    if base_url is not None:
        model_settings["provider_settings"] = {
            "base_url": base_url,
        }
    return model_settings


def _build_navigation_runtime_config(
    *,
    navigation_backend: NavigationBackend | None,
    offline: bool,
    navigation_graph_path: Path | None,
    navigation_snapshot_id: str | None,
) -> NavigationRuntimeConfig:
    resolved_backend = _resolve_default_navigation_backend(
        navigation_backend=NavigationBackend.GRAPH if offline else navigation_backend,
        navigation_graph_path=navigation_graph_path,
    )
    if offline:
        resolved_backend = NavigationBackend.GRAPH
    if (
        navigation_graph_path is not None
        and resolved_backend != NavigationBackend.GRAPH
    ):
        raise typer.BadParameter(
            "--navigation-graph-path requires --navigation-backend graph or --offline",
        )

    return NavigationRuntimeConfig(
        backend=resolved_backend,
        graph_path=navigation_graph_path,
        snapshot_id=navigation_snapshot_id,
    )


def _resolve_default_navigation_backend(
    *,
    navigation_backend: NavigationBackend | None,
    navigation_graph_path: Path | None,
) -> NavigationBackend:
    if navigation_backend is not None:
        return navigation_backend
    if navigation_graph_path is not None:
        return NavigationBackend.GRAPH

    try:
        resolve_graph_file_path(
            None,
        )
    except FileNotFoundError:
        return NavigationBackend.LIVE
    return NavigationBackend.GRAPH


def _build_solver_runtime_config(
    *,
    solver_backend: SolverBackend | None,
    solver_graph_path: Path | None,
    solver_snapshot_id: str | None,
    solver_endpoint: str | None,
) -> SolverRuntimeConfig:
    resolved_solver_backend = _resolve_default_solver_backend(
        solver_backend=solver_backend,
        solver_graph_path=solver_graph_path,
        solver_endpoint=solver_endpoint,
    )
    if resolved_solver_backend == SolverBackend.REMOTE:
        raise typer.BadParameter(
            "--solver-backend remote is not yet supported in the CLI",
        )
    if solver_graph_path is not None and resolved_solver_backend != SolverBackend.LOCAL:
        raise typer.BadParameter(
            "--solver-graph-path requires --solver-backend local",
        )
    if solver_endpoint is not None and resolved_solver_backend != SolverBackend.REMOTE:
        raise typer.BadParameter(
            "--solver-endpoint requires --solver-backend remote",
        )

    return SolverRuntimeConfig(
        backend=resolved_solver_backend,
        graph_path=solver_graph_path,
        snapshot_id=solver_snapshot_id,
        endpoint=solver_endpoint,
    )


def _resolve_default_solver_backend(
    *,
    solver_backend: SolverBackend | None,
    solver_graph_path: Path | None,
    solver_endpoint: str | None,
) -> SolverBackend:
    if solver_backend is not None:
        return solver_backend
    if solver_endpoint is not None:
        return SolverBackend.REMOTE
    if solver_graph_path is not None:
        return SolverBackend.LOCAL

    try:
        resolve_solver_graph_file_path(
            None,
        )
    except FileNotFoundError:
        return SolverBackend.NONE
    return SolverBackend.LOCAL


def _override_benchmark_run_options(
    run_options,
    *,
    navigation_backend: NavigationBackend | None,
    offline: bool,
    navigation_graph_path: Path | None,
    navigation_snapshot_id: str | None,
    solver_backend: SolverBackend | None,
    solver_graph_path: Path | None,
    solver_snapshot_id: str | None,
    solver_endpoint: str | None,
):
    resolved_navigation_graph_path = navigation_graph_path
    if resolved_navigation_graph_path is None:
        resolved_navigation_graph_path = run_options.navigation_runtime.graph_path

    config_navigation_backend_is_explicit = _runtime_field_was_explicitly_set(
        run_options,
        runtime_field_name="navigation_runtime",
        config_field_name="backend",
    )
    if offline:
        resolved_navigation_backend = NavigationBackend.GRAPH
    elif navigation_backend is not None:
        resolved_navigation_backend = navigation_backend
    elif config_navigation_backend_is_explicit:
        resolved_navigation_backend = run_options.navigation_runtime.backend
    else:
        resolved_navigation_backend = _resolve_default_navigation_backend(
            navigation_backend=None,
            navigation_graph_path=resolved_navigation_graph_path,
        )
    if (
        resolved_navigation_graph_path is not None
        and resolved_navigation_backend != NavigationBackend.GRAPH
    ):
        raise typer.BadParameter(
            "--navigation-graph-path requires --navigation-backend graph or --offline",
        )

    resolved_navigation_snapshot_id = navigation_snapshot_id
    if resolved_navigation_snapshot_id is None:
        resolved_navigation_snapshot_id = run_options.navigation_snapshot_id
    if resolved_navigation_snapshot_id is None:
        resolved_navigation_snapshot_id = run_options.navigation_runtime.snapshot_id

    updated_navigation_runtime = run_options.navigation_runtime.model_copy(
        update={
            "backend": resolved_navigation_backend,
            "graph_path": resolved_navigation_graph_path,
            "snapshot_id": resolved_navigation_snapshot_id,
        },
    )

    resolved_solver_graph_path = solver_graph_path
    if resolved_solver_graph_path is None:
        resolved_solver_graph_path = run_options.solver_runtime.graph_path

    resolved_solver_endpoint = solver_endpoint
    if resolved_solver_endpoint is None:
        resolved_solver_endpoint = run_options.solver_runtime.endpoint

    config_solver_backend_is_explicit = _runtime_field_was_explicitly_set(
        run_options,
        runtime_field_name="solver_runtime",
        config_field_name="backend",
    )
    if solver_backend is not None:
        resolved_solver_backend = solver_backend
    elif config_solver_backend_is_explicit:
        resolved_solver_backend = run_options.solver_runtime.backend
    else:
        resolved_solver_backend = _resolve_default_solver_backend(
            solver_backend=None,
            solver_graph_path=resolved_solver_graph_path,
            solver_endpoint=resolved_solver_endpoint,
        )
    if resolved_solver_backend == SolverBackend.REMOTE:
        raise typer.BadParameter(
            "--solver-backend remote is not yet supported in the CLI",
        )
    if (
        resolved_solver_graph_path is not None
        and resolved_solver_backend != SolverBackend.LOCAL
    ):
        raise typer.BadParameter(
            "--solver-graph-path requires --solver-backend local",
        )

    resolved_solver_snapshot_id = solver_snapshot_id
    if resolved_solver_snapshot_id is None:
        resolved_solver_snapshot_id = run_options.solver_snapshot_id
    if resolved_solver_snapshot_id is None:
        resolved_solver_snapshot_id = run_options.solver_runtime.snapshot_id

    if (
        resolved_solver_endpoint is not None
        and resolved_solver_backend != SolverBackend.REMOTE
    ):
        raise typer.BadParameter(
            "--solver-endpoint requires --solver-backend remote",
        )

    updated_solver_runtime = run_options.solver_runtime.model_copy(
        update={
            "backend": resolved_solver_backend,
            "graph_path": resolved_solver_graph_path,
            "snapshot_id": resolved_solver_snapshot_id,
            "endpoint": resolved_solver_endpoint,
        },
    )

    return run_options.model_copy(
        update={
            "navigation_runtime": updated_navigation_runtime,
            "solver_runtime": updated_solver_runtime,
            "navigation_snapshot_id": resolved_navigation_snapshot_id,
            "solver_snapshot_id": resolved_solver_snapshot_id,
        },
    )


def _runtime_field_was_explicitly_set(
    run_options,
    *,
    runtime_field_name: str,
    config_field_name: str,
) -> bool:
    if runtime_field_name not in run_options.model_fields_set:
        return False

    runtime_config = getattr(
        run_options,
        runtime_field_name,
    )
    return config_field_name in runtime_config.model_fields_set


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
    for label, value in build_error_summary_lines(
        run_result.error,
    ):
        typer.echo(
            f"{label}: {value}",
        )
    if output_path is not None:
        typer.echo(f"Saved to: {output_path}")


def _prepare_output_path(
    output_path: Path | None,
    *,
    append: bool,
    overwrite: bool,
    expected_ruleset_hash: str | None = None,
    expected_navigation_backend: NavigationBackend | None = None,
    expected_navigation_snapshot_id: str | None = None,
    expected_solver_backend: SolverBackend | None = None,
    expected_solver_snapshot_id: str | None = None,
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
            expected_navigation_backend=expected_navigation_backend,
            expected_navigation_snapshot_id=expected_navigation_snapshot_id,
            expected_solver_backend=expected_solver_backend,
            expected_solver_snapshot_id=expected_solver_snapshot_id,
        )
        return

    raise typer.BadParameter(
        f"output path already exists: {output_path}. Use --append or --overwrite.",
    )


def _validate_append_identity(
    output_path: Path,
    *,
    expected_ruleset_hash: str | None,
    expected_navigation_backend: NavigationBackend | None,
    expected_navigation_snapshot_id: str | None,
    expected_solver_backend: SolverBackend | None,
    expected_solver_snapshot_id: str | None,
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

    if expected_navigation_backend is not None:
        existing_navigation_backends = identity.navigation_backends
        if existing_navigation_backends and existing_navigation_backends != [
            expected_navigation_backend.value,
        ]:
            raise typer.BadParameter(
                "cannot append to output file with a different navigation_backend",
            )

    if expected_navigation_snapshot_id is not None:
        existing_navigation_snapshot_ids = identity.navigation_snapshot_ids
        if existing_navigation_snapshot_ids and existing_navigation_snapshot_ids != [
            expected_navigation_snapshot_id,
        ]:
            raise typer.BadParameter(
                "cannot append to output file with a different navigation_snapshot_id",
            )

    if expected_solver_backend is not None:
        existing_solver_backends = identity.solver_backends
        if existing_solver_backends and existing_solver_backends != [
            expected_solver_backend.value,
        ]:
            raise typer.BadParameter(
                "cannot append to output file with a different solver_backend",
            )

    if expected_solver_snapshot_id is not None:
        existing_solver_snapshot_ids = identity.solver_snapshot_ids
        if existing_solver_snapshot_ids and existing_solver_snapshot_ids != [
            expected_solver_snapshot_id,
        ]:
            raise typer.BadParameter(
                "cannot append to output file with a different solver_snapshot_id",
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
