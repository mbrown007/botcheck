#!/usr/bin/env python3
"""Generate a production-safe Argon2id password hash for use in users.yaml.

Usage:
    uv run scripts/hash_password.py
    uv run scripts/hash_password.py --password "my-secret"

The script reads the password from stdin if --password is not provided.
Output is a single-line Argon2id hash safe to paste into users.yaml.

Parameters match DEPLOYMENT_PLAN.md item 79 minimums:
    time_cost=2, memory_cost=65536 KiB (64 MiB), parallelism=2
"""
from __future__ import annotations

import argparse
import getpass
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an Argon2id hash for BotCheck user bootstrap.",
    )
    parser.add_argument(
        "--password",
        metavar="PASSWORD",
        help="Password to hash (read from stdin prompt if omitted).",
    )
    parser.add_argument(
        "--time-cost",
        type=int,
        default=2,
        metavar="N",
        help="Argon2id time cost (iterations). Minimum: 2. Default: 2.",
    )
    parser.add_argument(
        "--memory-cost",
        type=int,
        default=65536,
        metavar="KiB",
        help="Argon2id memory cost in KiB. Minimum: 65536 (64 MiB). Default: 65536.",
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=2,
        metavar="N",
        help="Argon2id parallelism (threads). Minimum: 2. Default: 2.",
    )
    args = parser.parse_args()

    if args.time_cost < 2:
        print("error: --time-cost must be >= 2", file=sys.stderr)
        sys.exit(1)
    if args.memory_cost < 65536:
        print("error: --memory-cost must be >= 65536 KiB (64 MiB)", file=sys.stderr)
        sys.exit(1)
    if args.parallelism < 2:
        print("error: --parallelism must be >= 2", file=sys.stderr)
        sys.exit(1)

    password = args.password
    if password is None:
        try:
            password = getpass.getpass("Password: ")
            confirm = getpass.getpass("Confirm password: ")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.", file=sys.stderr)
            sys.exit(1)
        if password != confirm:
            print("error: passwords do not match", file=sys.stderr)
            sys.exit(1)
    if not password:
        print("error: password must not be empty", file=sys.stderr)
        sys.exit(1)

    try:
        from passlib.context import CryptContext
    except ImportError:
        print(
            "error: passlib not installed — run: uv sync",
            file=sys.stderr,
        )
        sys.exit(1)

    ctx = CryptContext(
        schemes=["argon2"],
        argon2__time_cost=args.time_cost,
        argon2__memory_cost=args.memory_cost,
        argon2__parallelism=args.parallelism,
    )

    print("Hashing…", end=" ", flush=True, file=sys.stderr)
    hashed = ctx.hash(password)
    print("done.", file=sys.stderr)
    print()
    print(hashed)
    print()
    print(
        f"Parameters: time_cost={args.time_cost}, "
        f"memory_cost={args.memory_cost} KiB, "
        f"parallelism={args.parallelism}",
        file=sys.stderr,
    )
    print(
        "Paste the hash above into users.yaml as the password_hash field.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
