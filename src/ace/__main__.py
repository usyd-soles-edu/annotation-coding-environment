import argparse

from ace.app import run


def main():
    parser = argparse.ArgumentParser(description="ACE — Annotation Coding Environment")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    parser.add_argument("--parent-pid", type=int, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    run(port=args.port, parent_pid=args.parent_pid)


if __name__ == "__main__":
    main()
