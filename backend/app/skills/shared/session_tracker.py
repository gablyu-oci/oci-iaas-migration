#!/usr/bin/env python3
"""
session_tracker.py - CLI wrapper around agent_logger.py for persisting session state
across multiple CLI invocations using temp JSON files in /tmp/aws-oci-sessions/.

Usage:
  python3 shared/session_tracker.py start --type {iam|cfn|discovery} --source FILENAME
  python3 shared/session_tracker.py log --session SESSION_ID --iteration N --agent AGENT ...
  python3 shared/session_tracker.py review --session SESSION_ID --iteration N ...
  python3 shared/session_tracker.py fix --session SESSION_ID --iteration N ...
  python3 shared/session_tracker.py end --session SESSION_ID --decision DECISION --confidence FLOAT
  python3 shared/session_tracker.py paths --session SESSION_ID
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
# shared/session_tracker.py → parent is shared/ → parent.parent is project root
SHARED_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SHARED_DIR.parent.resolve()
sys.path.insert(0, str(SHARED_DIR))

# ── Constants ─────────────────────────────────────────────────────────────────
TMP_DIR = Path("/tmp/aws-oci-sessions")

LOG_DIR_MAP = {
    "iam":       PROJECT_ROOT / "iam-translation" / "translation-logs",
    "cfn":       PROJECT_ROOT / "cfn-terraform" / "translation-logs",
    "discovery": PROJECT_ROOT / "aws-dependency-discovery" / "output" / "logs",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def ensure_tmp_dir():
    TMP_DIR.mkdir(parents=True, exist_ok=True)


def session_path(session_id: str) -> Path:
    return TMP_DIR / f"{session_id}.json"


def load_session(session_id: str) -> dict:
    path = session_path(session_id)
    if not path.exists():
        print(f"ERROR: Session file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def save_session(data: dict):
    ensure_tmp_dir()
    path = session_path(data["session_id"])
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def parse_json_arg(value: str, field_name: str):
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON for {field_name}: {e}", file=sys.stderr)
        sys.exit(1)


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_start(args):
    """Create a new session temp file and print the SESSION_ID to stdout."""
    ensure_tmp_dir()

    project_type = args.type
    source_file = args.source
    log_dir = LOG_DIR_MAP.get(project_type)
    if log_dir is None:
        print(f"ERROR: Unknown project type '{project_type}'", file=sys.stderr)
        sys.exit(1)

    source_stem = Path(source_file).stem
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_id = f"{project_type}-{source_stem}-{timestamp}"

    data = {
        "session_id": session_id,
        "project_type": project_type,
        "source_file": source_file,
        "log_dir": str(log_dir),
        "start_time": datetime.now().isoformat(),
        "interactions": [],
    }
    save_session(data)
    print(session_id)


def cmd_log(args):
    """Append a translation/analysis interaction to the session temp file."""
    data = load_session(args.session)
    metadata = parse_json_arg(args.metadata, "--metadata") or {}

    interaction = {
        "call_type": "log",
        "iteration": args.iteration,
        "agent": args.agent,
        "model": getattr(args, "model", None),
        "input": args.input,
        "output": args.output,
        "duration": args.duration,
        "tokens_in": args.tokens_in,
        "tokens_out": args.tokens_out,
        "tokens_cache_read": getattr(args, "tokens_cache_read", None),
        "tokens_cache_write": getattr(args, "tokens_cache_write", None),
        "cost": args.cost,
        "decision": None,
        "confidence": None,
        "issues": [],
        "fixes": [],
        "metadata": metadata,
    }
    data["interactions"].append(interaction)
    save_session(data)
    print(f"Logged {args.agent} for session {args.session}, iteration {args.iteration}")


def cmd_review(args):
    """Append a review interaction to the session temp file."""
    data = load_session(args.session)
    issues = parse_json_arg(args.issues, "--issues") or []

    interaction = {
        "call_type": "review",
        "iteration": args.iteration,
        "agent": "reviewer",
        "model": getattr(args, "model", None),
        "input": f"Review translation from iteration {args.iteration}",
        "output": args.output,
        "duration": args.duration,
        "tokens_in": args.tokens_in,
        "tokens_out": args.tokens_out,
        "tokens_cache_read": getattr(args, "tokens_cache_read", None),
        "tokens_cache_write": getattr(args, "tokens_cache_write", None),
        "cost": args.cost,
        "decision": args.decision,
        "confidence": args.confidence,
        "issues": issues,
        "fixes": [],
        "metadata": {},
    }
    data["interactions"].append(interaction)
    save_session(data)
    print(
        f"Logged review for session {args.session}, iteration {args.iteration}: "
        f"{args.decision} (confidence={args.confidence})"
    )


def cmd_fix(args):
    """Append a fix interaction to the session temp file."""
    data = load_session(args.session)
    fixes = parse_json_arg(args.fixes, "--fixes") or []

    interaction = {
        "call_type": "fix",
        "iteration": args.iteration,
        "agent": "fix",
        "model": getattr(args, "model", None),
        "input": f"Fix issues from review iteration {args.iteration}",
        "output": args.output,
        "duration": args.duration,
        "tokens_in": args.tokens_in,
        "tokens_out": args.tokens_out,
        "tokens_cache_read": getattr(args, "tokens_cache_read", None),
        "tokens_cache_write": getattr(args, "tokens_cache_write", None),
        "cost": args.cost,
        "decision": None,
        "confidence": None,
        "issues": [],
        "fixes": fixes,
        "metadata": {},
    }
    data["interactions"].append(interaction)
    save_session(data)
    print(f"Logged fix for session {args.session}, iteration {args.iteration}")


def cmd_end(args):
    """
    Load temp file, replay all interactions into AgentLogger using the correct
    agent_logger.py API, generate reports, clean up temp file, print report paths.
    """
    data = load_session(args.session)

    log_dir = Path(data["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)

    try:
        from agent_logger import (
            AgentLogger, AgentType, ReviewDecision, ConfidenceCalculator
        )
    except ImportError as e:
        print(f"ERROR: Could not import agent_logger: {e}", file=sys.stderr)
        sys.exit(1)

    # String → enum maps
    decision_map = {
        "APPROVED":            ReviewDecision.APPROVED,
        "APPROVED_WITH_NOTES": ReviewDecision.APPROVED_WITH_NOTES,
        "NEEDS_FIXES":         ReviewDecision.NEEDS_FIXES,
        "FAILED":              ReviewDecision.FAILED,
    }
    agent_type_map = {
        "translator":  AgentType.TRANSLATOR,
        "enhancement": AgentType.ENHANCEMENT,
        "fix":         AgentType.FIX,
        "discovery":   AgentType.DISCOVERY,
        "validation":  AgentType.VALIDATION,
        "analysis":    AgentType.DISCOVERY,   # alias
        "reviewer":    AgentType.REVIEW,
    }

    # Initialise and start the logger (session_id is generated internally)
    logger = AgentLogger(
        project_type=data["project_type"],
        source_file=data["source_file"],
        log_dir=str(log_dir),
    )
    logger.start_session()

    # ── Replay all recorded interactions ──────────────────────────────────────
    for ix in data["interactions"]:
        call_type = ix.get("call_type", "log")

        # Common optional token / cost kwargs — from real API usage only
        tok_kwargs = {}
        if ix.get("tokens_in")          is not None: tok_kwargs["tokens_input"]        = ix["tokens_in"]
        if ix.get("tokens_out")         is not None: tok_kwargs["tokens_output"]       = ix["tokens_out"]
        if ix.get("tokens_cache_read")  is not None: tok_kwargs["tokens_cache_read"]   = ix["tokens_cache_read"]
        if ix.get("tokens_cache_write") is not None: tok_kwargs["tokens_cache_write"]  = ix["tokens_cache_write"]
        if ix.get("cost")               is not None: tok_kwargs["cost_usd"]            = ix["cost"]
        if ix.get("model")              is not None: tok_kwargs["model"]               = ix["model"]

        if call_type == "log":
            agent_type = agent_type_map.get(
                ix.get("agent", "enhancement"), AgentType.ENHANCEMENT
            )
            logger.log_agent_call(
                iteration=ix.get("iteration", 0),
                agent_type=agent_type,
                input_summary=ix.get("input", ""),
                output_summary=ix.get("output", ""),
                duration_seconds=ix.get("duration", 0.0),
                metadata=ix.get("metadata") or {},
                **tok_kwargs,
            )

        elif call_type == "review":
            raw_decision = ix.get("decision", "NEEDS_FIXES")
            review_decision = decision_map.get(raw_decision, ReviewDecision.NEEDS_FIXES)

            # Extract issue descriptions as strings (issues can be dicts or strings)
            raw_issues = ix.get("issues", [])
            issues_found = [
                i.get("description", str(i)) if isinstance(i, dict) else str(i)
                for i in raw_issues
            ]

            logger.log_review_call(
                iteration=ix.get("iteration", 0),
                decision=review_decision,
                confidence=ix.get("confidence", 0.0),
                issues_found=issues_found,
                review_output={"issues": raw_issues, "output": ix.get("output", "")},
                duration_seconds=ix.get("duration", 0.0),
                **tok_kwargs,
            )

        elif call_type == "fix":
            fixes = ix.get("fixes", [])
            logger.log_fix_call(
                iteration=ix.get("iteration", 0),
                fixes_applied=fixes,
                output_summary=ix.get("output", ""),
                duration_seconds=ix.get("duration", 0.0),
                **tok_kwargs,
            )

    # ── Finalise session ───────────────────────────────────────────────────────
    final_decision = decision_map.get(
        args.decision.upper(), ReviewDecision.APPROVED
    )
    logger.end_session(
        final_decision=final_decision,
        final_confidence=args.confidence,
    )

    # Clean up temp file (non-fatal if it fails)
    try:
        session_path(args.session).unlink()
    except OSError:
        pass

    # Print the report paths so the skill can display them
    print(json.dumps(logger.get_report_paths(), indent=2))


def cmd_paths(args):
    """
    Print the expected output paths for a session.
    Works even before end is called (useful for pre-announcing paths).
    """
    data = load_session(args.session)
    session_id = data["session_id"]
    log_dir = Path(data["log_dir"])

    paths = {
        "json_log":        str(log_dir / f"{session_id}.json"),
        "markdown_report": str(log_dir / f"{session_id}-report.md"),
    }
    print(json.dumps(paths, indent=2))


# ── Argument parsing ──────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="CLI session tracker for AWS→OCI migration orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # start
    p = subparsers.add_parser("start", help="Begin a new migration session")
    p.add_argument("--type", required=True, choices=["iam", "cfn", "discovery"])
    p.add_argument("--source", required=True, help="Source filename (e.g. policy.json)")

    def _add_token_args(p):
        """Add real-API token args to a subparser (no self-report --tokens)."""
        p.add_argument("--model",              default=None, help="Model ID e.g. google.gemini-2.5-pro")
        p.add_argument("--tokens-in",          type=int, default=None, dest="tokens_in",
                       help="Input tokens from response.usage.input_tokens")
        p.add_argument("--tokens-out",         type=int, default=None, dest="tokens_out",
                       help="Output tokens from response.usage.output_tokens")
        p.add_argument("--tokens-cache-read",  type=int, default=None, dest="tokens_cache_read",
                       help="Cache read tokens from response.usage.cache_read_input_tokens")
        p.add_argument("--tokens-cache-write", type=int, default=None, dest="tokens_cache_write",
                       help="Cache write tokens from response.usage.cache_creation_input_tokens")
        p.add_argument("--cost",               type=float, default=None,
                       help="USD cost (use calculate_cost() from agent_logger — do not estimate)")

    # log
    p = subparsers.add_parser("log", help="Log a translation/analysis interaction")
    p.add_argument("--session", required=True)
    p.add_argument("--iteration", required=True, type=int)
    p.add_argument("--agent", required=True,
        choices=["translator", "enhancement", "fix", "discovery",
                 "validation", "analysis", "reviewer"])
    p.add_argument("--input",    required=True, dest="input")
    p.add_argument("--output",   required=True, dest="output")
    p.add_argument("--duration", required=True, type=float)
    _add_token_args(p)
    p.add_argument("--metadata", default=None, help="JSON string of extra metadata")

    # review
    p = subparsers.add_parser("review", help="Log a review interaction")
    p.add_argument("--session",    required=True)
    p.add_argument("--iteration",  required=True, type=int)
    p.add_argument("--decision",   required=True,
        choices=["APPROVED", "APPROVED_WITH_NOTES", "NEEDS_FIXES", "FAILED"])
    p.add_argument("--confidence", required=True, type=float)
    p.add_argument("--issues",     required=True, help="JSON array of issue objects")
    p.add_argument("--output",     required=True, dest="output")
    p.add_argument("--duration",   required=True, type=float)
    _add_token_args(p)

    # fix
    p = subparsers.add_parser("fix", help="Log a fix interaction")
    p.add_argument("--session",    required=True)
    p.add_argument("--iteration",  required=True, type=int)
    p.add_argument("--fixes",      required=True, help="JSON array of fix descriptions")
    p.add_argument("--output",     required=True, dest="output")
    p.add_argument("--duration",   required=True, type=float)
    _add_token_args(p)

    # end
    p = subparsers.add_parser("end", help="Finalise session and generate reports")
    p.add_argument("--session",    required=True)
    p.add_argument("--decision",   required=True)
    p.add_argument("--confidence", required=True, type=float)

    # paths
    p = subparsers.add_parser("paths", help="Print expected output file paths")
    p.add_argument("--session", required=True)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    command_map = {
        "start":   cmd_start,
        "log":     cmd_log,
        "review":  cmd_review,
        "fix":     cmd_fix,
        "end":     cmd_end,
        "paths":   cmd_paths,
    }

    handler = command_map.get(args.command)
    if handler is None:
        print(f"ERROR: Unknown command '{args.command}'", file=sys.stderr)
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()
