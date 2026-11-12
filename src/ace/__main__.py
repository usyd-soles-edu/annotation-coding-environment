import argparse
import json
import os


def _startup_reason(error: BaseException) -> str:
    """Classify startup failures without retaining exception text or paths."""
    if isinstance(error, ModuleNotFoundError):
        return "missing_dependency"
    if isinstance(error, PermissionError):
        return "permission_denied"
    if isinstance(error, OSError):
        return "os_error"
    if isinstance(error, SystemExit):
        return "server_exit"
    return "unexpected_error"


def _write_startup_report(path: str | None, stage: str, error: BaseException) -> None:
    """Write only fixed diagnostic codes to a launcher-owned temporary file."""
    if not path:
        return
    try:
        flags = os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "w", encoding="utf-8") as report:
            json.dump({"stage": stage, "reason": _startup_reason(error)}, report)
    except OSError:
        # The launcher may have removed the file after successful readiness.
        pass


def main():
    parser = argparse.ArgumentParser(description="ACE — Annotation Coding Environment")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    parser.add_argument("--parent-pid", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--launcher-token", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--runtime-file", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--startup-report", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--idle-timeout-seconds",
        type=float,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-kill-stale",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--check-native-picker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    stage = "import"
    try:
        from ace.app import run

        if args.check_native_picker:
            from ace.routes.api_support import check_native_picker_runtime

            check_native_picker_runtime()
            return
        stage = "serve"
        run(
            port=args.port,
            parent_pid=args.parent_pid,
            launcher_token=args.launcher_token,
            runtime_file=args.runtime_file,
            idle_timeout_seconds=args.idle_timeout_seconds,
            kill_stale=not args.no_kill_stale,
        )
    except (Exception, SystemExit) as error:
        _write_startup_report(args.startup_report, stage, error)
        raise


if __name__ == "__main__":
    main()
