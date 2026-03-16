"""CLI entrypoint for Academic-Data-Agent."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status
from rich.table import Table


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.agent_runner import AnalysisRunResult, run_analysis  # noqa: E402
from data_analysis_agent.prompts import DEFAULT_QUERY  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Academic-Data-Agent from the command line.")
    parser.add_argument("--data", required=True, help="Path to the local Excel or CSV dataset.")
    parser.add_argument("--output-dir", default="outputs", help="Parent directory for per-run artifacts.")
    parser.add_argument("--report", default=None, help="Optional compatibility report copy path.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="User query prefix passed to the agent.")
    parser.add_argument("--env-file", default=None, help="Optional .env file path.")
    parser.add_argument("--max-steps", type=int, default=6, help="Maximum controller steps for the custom ReAct runner.")
    parser.add_argument(
        "--max-reviews",
        type=int,
        default=None,
        help="Optional override for maximum revision rounds after reviewer rejection.",
    )
    parser.add_argument(
        "--quality-mode",
        choices=("draft", "standard", "publication"),
        default="standard",
        help="Report quality mode: draft skips review, standard allows 1 revision, publication allows 2 revisions.",
    )
    parser.add_argument(
        "--latency-mode",
        choices=("auto", "quality", "fast"),
        default="auto",
        help="Latency policy: auto enables adaptive fast-paths, quality preserves the full workflow, fast prioritizes speed.",
    )
    parser.add_argument(
        "--document-ingestion-mode",
        choices=("auto", "text_only", "vision_fallback"),
        default="auto",
        help="PDF ingestion policy: auto and text_only only use local text/table parsing in V1; vision_fallback is reserved for future work.",
    )
    parser.add_argument(
        "--max-pdf-pages",
        type=int,
        default=20,
        help="Maximum number of PDF pages inspected during document ingestion.",
    )
    parser.add_argument(
        "--max-candidate-tables",
        type=int,
        default=5,
        help="Maximum number of candidate PDF tables recorded during ingestion.",
    )
    parser.add_argument(
        "--selected-table-id",
        default=None,
        help="Optional PDF candidate table_id override, such as table_01.",
    )
    parser.add_argument(
        "--vision-review-mode",
        choices=("off", "auto", "on"),
        default="auto",
        help="Visual review policy: auto enables it only for publication runs when configured, on enables it for reviewed runs, off disables it.",
    )
    parser.add_argument(
        "--vision-max-images",
        type=int,
        default=3,
        help="Maximum number of raster figures reviewed per round.",
    )
    parser.add_argument(
        "--vision-max-image-side",
        type=int,
        default=1024,
        help="Maximum image side length in pixels before JPEG downscaling for visual review.",
    )
    return parser


def _tool_label(tool_name: str | None) -> str:
    if tool_name == "PythonInterpreterTool":
        return "Local Python analysis"
    if tool_name == "TavilySearchTool":
        return "Online knowledge retrieval"
    return tool_name or "Unnamed step"


def _format_search_status(search_status: str, search_notes: str) -> str:
    mapping = {
        "used": "Online retrieval used",
        "skipped": "Online retrieval skipped",
        "unavailable": "Online retrieval unavailable",
        "attempted": "Online retrieval attempted",
        "not_used": "Online retrieval not triggered",
    }
    label = mapping.get(search_status, "Online retrieval status unknown")
    return f"{label} | {search_notes}"


def _format_workflow_status(result: AnalysisRunResult) -> str:
    if result.workflow_complete:
        return "Production-grade artifact contract satisfied"
    missing = ", ".join(result.missing_artifacts) if result.missing_artifacts else "unknown"
    return f"Incomplete production artifacts | missing: {missing}"


def _format_review_status(result: AnalysisRunResult) -> str:
    mapping = {
        "skipped": "Reviewer skipped",
        "accepted": "Reviewer accepted",
        "rejected": "Reviewer rejected",
        "max_reviews_reached": "Reviewer max rounds reached",
    }
    label = mapping.get(result.review_status, result.review_status or "unknown")
    return f"{label} | rounds={result.review_rounds_used}"


def _format_vision_status(result: AnalysisRunResult) -> str:
    mapping = {
        "completed": "Vision reviewer completed",
        "skipped": "Vision reviewer skipped",
        "unavailable": "Vision reviewer unavailable",
        "failed": "Vision reviewer failed",
    }
    label = mapping.get(result.vision_review_status, result.vision_review_status or "unknown")
    return f"{label} | mode={result.vision_review_mode}"


def _format_duration(duration_ms: int) -> str:
    return f"{duration_ms / 1000:.2f}s"


def _build_summary_table(result: AnalysisRunResult) -> Table:
    table = Table(title="Run Summary", show_header=False, box=None, pad_edge=False)
    table.add_column("Field", style="bold cyan", width=18)
    table.add_column("Value", style="white")
    table.add_row("Dataset", result.data_context.absolute_path.as_posix())
    table.add_row("Data shape", f"{result.data_context.shape[0]} rows x {result.data_context.shape[1]} columns")
    table.add_row("Detected domain", result.detected_domain)
    table.add_row("Tools used", ", ".join(result.tools_used) if result.tools_used else "unknown")
    table.add_row("Methods", ", ".join(result.methods_used) if result.methods_used else "unknown")
    table.add_row("Search", _format_search_status(result.search_status, result.search_notes))
    table.add_row("Quality mode", result.quality_mode)
    table.add_row("Latency mode", result.latency_mode)
    table.add_row("Input kind", result.input_kind)
    table.add_row("Document parse", result.document_ingestion_status)
    table.add_row("Candidate tables", str(result.candidate_table_count))
    table.add_row("Selected table", result.selected_table_id or "auto")
    table.add_row("PDF multi-table", "enabled" if result.pdf_multi_table_mode else "disabled")
    table.add_row("Vision review", _format_vision_status(result))
    table.add_row("Run directory", result.run_dir.as_posix())
    table.add_row("Cleaned data", result.cleaned_data_path.as_posix())
    table.add_row("Trace log", result.trace_path.as_posix())
    table.add_row("Report", result.report_path.as_posix())
    table.add_row("Review status", _format_review_status(result))
    table.add_row("Last critique", result.review_critique or "none")
    table.add_row("Total time", _format_duration(result.total_duration_ms))
    table.add_row("LLM time", _format_duration(result.llm_duration_ms))
    table.add_row("Tool time", _format_duration(result.tool_duration_ms))
    table.add_row("Review time", _format_duration(result.review_duration_ms))
    table.add_row("Document time", _format_duration(result.document_ingestion_duration_ms))
    table.add_row("Vision time", _format_duration(result.vision_review_duration_ms))
    table.add_row("Tavily time", _format_duration(result.timing_breakdown.get("tavily_duration_ms", 0)))
    table.add_row("Workflow", _format_workflow_status(result))
    return table


def _build_step_table(result: AnalysisRunResult) -> Table:
    table = Table(title="Execution Trace", header_style="bold magenta")
    table.add_column("Step", style="cyan", width=6)
    table.add_column("Stage / Tool", style="green", width=24)
    table.add_column("Status", style="yellow", width=10)
    table.add_column("Summary", style="white")
    for trace in result.step_traces:
        table.add_row(
            str(trace.step_index),
            _tool_label(trace.tool_name) if trace.action == "call_tool" else "Report finalization",
            trace.tool_status,
            trace.summary or trace.decision or trace.parse_error or "No summary",
        )
    return table


def _render_result(console: Console, result: AnalysisRunResult) -> None:
    console.print()
    border_style = "green" if result.workflow_complete else "yellow"
    title = "Academic-Data-Agent"
    message = "Research workflow completed." if result.workflow_complete else "Run completed, but production artifacts are incomplete."
    console.print(Panel.fit(message, title=title, border_style=border_style))
    console.print(_build_summary_table(result))
    console.print(_build_step_table(result))

    if not result.telemetry.valid:
        console.print("[yellow]Warning: the final report did not include a valid structured <telemetry> block.[/yellow]")

    if result.workflow_warnings:
        for warning in result.workflow_warnings:
            console.print(f"[yellow]Artifact warning:[/yellow] {warning}")

    preview_lines = result.report_markdown.splitlines()[:20]
    preview_text = "\n".join(preview_lines).strip()
    if preview_text:
        console.print(Panel(Markdown(preview_text), title="Report Preview", border_style="blue"))


def _build_event_handler(console: Console, status: Status) -> Callable[[str, dict[str, Any]], None]:
    def handle_event(event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "config_loading":
            status.update("[cyan]Loading runtime configuration and model settings...[/cyan]", spinner="dots")
        elif event_type == "config_loaded":
            status.update("[cyan]Configuration loaded. Checking available capabilities...[/cyan]", spinner="dots")
            if payload.get("tavily_configured"):
                console.log("[green]Tavily credential detected. Final search availability will follow the latency policy.[/green]")
            else:
                console.log("[yellow]Tavily credential not configured. The agent will skip online search when needed.[/yellow]")
            console.log(f"[cyan]Latency mode:[/cyan] {payload.get('latency_mode', 'auto')}")
            console.log(
                f"[cyan]Vision review:[/cyan] "
                f"{'configured' if payload.get('vision_configured') else 'not configured'}"
            )
        elif event_type == "run_directory_created":
            status.update("[cyan]Creating a production run workspace...[/cyan]", spinner="dots")
            console.log(f"[cyan]Run directory ready:[/cyan] {payload.get('run_dir', '')}")
        elif event_type == "document_ingestion_started":
            status.update("[cyan]Preparing the input document for analysis...[/cyan]", spinner="dots")
            console.log(f"[cyan]Input kind:[/cyan] {payload.get('input_kind', 'unknown')}")
        elif event_type == "document_ingestion_completed":
            console.log(
                f"[cyan]Document ingestion completed[/cyan] | status={payload.get('status', 'unknown')} | "
                f"{payload.get('summary', '')}"
            )
        elif event_type == "document_ingestion_skipped":
            console.log("[cyan]Document ingestion skipped:[/cyan] input is already tabular.")
        elif event_type == "data_context_loading":
            status.update("[cyan]Reading dataset metadata and building compact data_context...[/cyan]", spinner="dots")
        elif event_type == "data_context_ready":
            shape = payload.get("shape", ("?", "?"))
            console.log(
                f"[cyan]Data context ready:[/cyan] {shape[0]} rows x {shape[1]} columns, "
                f"{len(payload.get('columns', []))} fields."
            )
        elif event_type == "tool_registry_ready":
            status.update("[cyan]Registering analysis tools...[/cyan]", spinner="dots")
            tools = ", ".join(payload.get("tools", []))
            console.log(f"[cyan]Tools ready:[/cyan] {tools}")
            console.log(
                f"[cyan]Fast path:[/cyan] {payload.get('fast_path_enabled', False)} | "
                f"effective max steps = {payload.get('effective_max_steps', '?')}"
            )
        elif event_type == "analysis_started":
            status.update("[magenta]Agent is reasoning about the analysis plan...[/magenta]", spinner="moon")
            console.log(
                f"[bold magenta]{payload.get('agent_name', 'Agent')}[/bold magenta] started. "
                f"Max controller steps: {payload.get('max_steps', '?')}."
            )
            if payload.get("analysis_round"):
                console.log(f"[magenta]Analysis round:[/magenta] {payload.get('analysis_round')}")
        elif event_type == "step_started":
            status.update(
                f"[magenta]Step {payload.get('step_index', '?')}/{payload.get('max_steps', '?')}: planning the next action...[/magenta]",
                spinner="moon",
            )
        elif event_type == "tool_call_started":
            tool_name = payload.get("tool_name")
            if tool_name == "TavilySearchTool":
                status.update("[blue]Running online background search...[/blue]", spinner="earth")
            else:
                status.update("[green]Running local Python analysis in the sandbox...[/green]", spinner="line")
            decision = payload.get("decision")
            if decision:
                console.log(f"[white]Decision:[/white] {decision}")
        elif event_type == "tool_call_completed":
            tool_name = payload.get("tool_name")
            label = "online retrieval" if tool_name == "TavilySearchTool" else "local analysis"
            console.log(f"[green]Completed {label}[/green] | status = {payload.get('tool_status', 'unknown')}")
            preview = payload.get("observation_preview")
            if preview:
                console.log(f"[dim]{preview}[/dim]")
        elif event_type == "step_parse_error":
            console.log(f"[yellow]Protocol parse warning:[/yellow] {payload.get('message', '')}")
        elif event_type == "report_persisting":
            status.update("[cyan]Saving Markdown report and agent trace...[/cyan]", spinner="dots")
        elif event_type == "report_saved":
            status.update("[green]Report and trace saved.[/green]", spinner="dots")
            console.log(f"[green]Report:[/green] {payload.get('report_path', '')}")
            console.log(f"[green]Trace:[/green] {payload.get('trace_path', '')}")
        elif event_type == "artifact_validation_completed":
            if payload.get("workflow_complete"):
                console.log("[green]Production artifact validation passed.[/green]")
            else:
                console.log("[yellow]Production artifact validation failed.[/yellow]")
                missing = ", ".join(payload.get("missing_artifacts", []))
                if missing:
                    console.log(f"[yellow]Missing artifacts:[/yellow] {missing}")
        elif event_type == "analysis_finished":
            status.update("[green]The agent produced a final report.[/green]", spinner="dots")
        elif event_type == "analysis_max_steps":
            console.log("[yellow]The agent reached the maximum number of controller steps.[/yellow]")
        elif event_type == "vision_review_started":
            status.update("[cyan]Vision reviewer is checking the current round figures...[/cyan]", spinner="dots")
            console.log(f"[cyan]Vision reviewer round {payload.get('review_round', '?')} started.[/cyan]")
        elif event_type == "vision_review_completed":
            console.log(
                f"[cyan]Vision reviewer completed[/cyan] | status={payload.get('status', 'unknown')} | "
                f"decision={payload.get('decision', 'unknown')}"
            )
        elif event_type == "vision_review_skipped":
            console.log(f"[yellow]Vision reviewer skipped[/yellow] {payload.get('reason', '')}")
        elif event_type == "review_started":
            status.update("[cyan]Reviewer agent is auditing the candidate report...[/cyan]", spinner="dots")
            console.log(f"[cyan]Reviewer round {payload.get('review_round', '?')} started.[/cyan]")
        elif event_type == "review_rejected":
            status.update("[yellow]Reviewer requested revisions.[/yellow]", spinner="dots")
            console.log(f"[yellow][REJECT][/yellow] {payload.get('critique', '')}")
        elif event_type == "review_accepted":
            status.update("[green]Reviewer accepted the report.[/green]", spinner="dots")
            console.log("[bold green][OK] 审稿通过：报告达到当前质量档位要求。[/bold green]")
        elif event_type == "review_max_reached":
            status.update("[yellow]Maximum review rounds reached.[/yellow]", spinner="dots")
            console.log("[yellow]Reviewer max rounds reached. Final report was not formally accepted.[/yellow]")

    return handle_event


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    console = Console()

    console.print(
        Panel.fit(
            f"[bold]Academic-Data-Agent[/bold]\n"
            f"Dataset: {Path(args.data).as_posix()}\n"
            f"Run parent directory: {Path(args.output_dir).as_posix()}",
            title="Production Analysis Workflow",
            border_style="cyan",
        )
    )

    try:
        with console.status("[cyan]Initializing analysis task...[/cyan]", spinner="dots") as status:
            event_handler = _build_event_handler(console, status)
            result = run_analysis(
                args.data,
                output_dir=args.output_dir,
                report_path=args.report,
                query=args.query,
                env_file=args.env_file,
                max_steps=args.max_steps,
                max_reviews=args.max_reviews,
                quality_mode=args.quality_mode,
                latency_mode=args.latency_mode,
                document_ingestion_mode=args.document_ingestion_mode,
                max_pdf_pages=args.max_pdf_pages,
            max_candidate_tables=args.max_candidate_tables,
            selected_table_id=args.selected_table_id,
            vision_review_mode=args.vision_review_mode,
                vision_max_images=args.vision_max_images,
                vision_max_image_side=args.vision_max_image_side,
                event_handler=event_handler,
            )
    except Exception as exc:
        console.print("[bold red]Analysis failed[/bold red]")
        console.print(str(exc))
        console.print_exception(show_locals=False)
        return 1

    _render_result(console, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
