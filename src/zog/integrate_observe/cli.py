"""CLI for integrate-observe factual comparison, impact, and verification history."""
import argparse
import json
import sys

from .history import VerificationHistoryAnalyzer
from .impact import ImpactAnalyzer
from .observer import IntegrationObserver, ObservationError, SCHEMA_VERSION


def _trace(args):
    try:
        from zog.build_trace import BuildTrace, TraceError
    except ImportError as exc:
        raise ObservationError(
            "dependency-unavailable",
            "Install build-trace 0.12.x before using the CLI.",
        ) from exc
    try:
        return BuildTrace(
            args.project_root,
            host_id=args.host_id,
            record_store=args.record_store,
            record_project_id=args.record_project_id,
        )
    except TraceError as exc:
        raise ObservationError(getattr(exc, "code", "build-trace-error"), str(exc)) from exc


def _parser():
    parser = argparse.ArgumentParser(prog="integrate-observe")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--record-store", required=True)
    parser.add_argument("--record-project-id", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    world = sub.add_parser("world", help="Inspect one caller-selected observation world")
    world.add_argument("snapshot")

    compare = sub.add_parser("compare", help="Compare caller-selected baseline and candidate worlds")
    compare.add_argument("baseline_snapshot")
    compare.add_argument("candidate_snapshot")

    impact = sub.add_parser(
        "impact",
        help="Compute bounded literal reverse relationship reachability in one world",
    )
    impact.add_argument("snapshot")
    impact.add_argument(
        "selector_kind",
        choices=("package", "package-output", "soname", "path"),
    )
    impact.add_argument("selector_value")
    impact.add_argument("--relation")
    impact.add_argument("--max-depth", type=int, default=3)
    impact.add_argument("--max-packages", type=int, default=100)

    history = sub.add_parser(
        "verification-history",
        help="Assess caller-ordered verification history and adjacent-point comparability",
    )
    history.add_argument("check_id")
    history.add_argument("snapshots", nargs="+")
    history.add_argument("--page-limit", type=int, default=20)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        trace = _trace(args)
        if args.command == "world":
            result = IntegrationObserver(trace).world(args.snapshot)
        elif args.command == "compare":
            result = IntegrationObserver(trace).compare(
                args.baseline_snapshot, args.candidate_snapshot
            )
        elif args.command == "impact":
            result = ImpactAnalyzer(
                trace, max_packages=args.max_packages
            ).impact(
                args.snapshot,
                args.selector_kind,
                args.selector_value,
                relation=args.relation,
                max_depth=args.max_depth,
            )
        else:
            result = VerificationHistoryAnalyzer(
                trace, page_limit=args.page_limit
            ).history(args.snapshots, args.check_id)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except ObservationError as exc:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "kind": "error",
            "error": {"code": exc.code, "message": exc.message},
        }, sort_keys=True, separators=(",", ":")))
        return 2
    except Exception as exc:
        # BuildTrace TraceError is deliberately not imported into observer.py. Preserve
        # a bounded public failure shape rather than exposing arbitrary exception text.
        code = getattr(exc, "code", None)
        if isinstance(code, str):
            print(json.dumps({
                "schema_version": SCHEMA_VERSION,
                "kind": "error",
                "error": {"code": code, "message": "build-trace query failed"},
            }, sort_keys=True, separators=(",", ":")))
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
