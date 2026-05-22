import argparse

from ace.app import run


def main():
    parser = argparse.ArgumentParser(description="ACE — Annotation Coding Environment")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    parser.add_argument("--parent-pid", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--launcher-token", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--runtime-file", default=None, help=argparse.SUPPRESS)
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
    args = parser.parse_args()
    run(
        port=args.port,
        parent_pid=args.parent_pid,
        launcher_token=args.launcher_token,
        runtime_file=args.runtime_file,
        idle_timeout_seconds=args.idle_timeout_seconds,
        kill_stale=not args.no_kill_stale,
    )


if __name__ == "__main__":
    main()
