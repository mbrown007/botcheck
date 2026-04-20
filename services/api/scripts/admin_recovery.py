#!/usr/bin/env python3
"""Operator CLI for explicit auth recovery workflows (Phase 6 item 87)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from botcheck_api.admin_recovery import reset_user_2fa, reset_user_recovery_codes
from botcheck_api.config import settings
from botcheck_api import database


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operator auth recovery workflows for BotCheck local auth users.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional DB URL override (defaults to configured API database).",
    )
    parser.add_argument(
        "--tenant-id",
        default=settings.tenant_id,
        help=f"Tenant ID (default: {settings.tenant_id}).",
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Target user email.",
    )
    parser.add_argument(
        "--actor-id",
        required=True,
        help="Operator identity written to audit_log actor_id.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "reset-2fa",
        help="Disable TOTP, invalidate recovery codes, and revoke active sessions.",
    )
    sub.add_parser(
        "reset-recovery-codes",
        help="Invalidate all active recovery codes without disabling TOTP.",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    await database.init_db(args.database_url)
    factory = database.AsyncSessionLocal
    if factory is None:
        print("error: DB session factory is not initialized", file=sys.stderr)
        return 1

    async with factory() as session:
        try:
            await database.apply_tenant_rls_context(session, args.tenant_id)
            if args.command == "reset-2fa":
                result = await reset_user_2fa(
                    session,
                    tenant_id=args.tenant_id,
                    email=args.email,
                    actor_id=args.actor_id,
                )
            elif args.command == "reset-recovery-codes":
                result = await reset_user_recovery_codes(
                    session,
                    tenant_id=args.tenant_id,
                    email=args.email,
                    actor_id=args.actor_id,
                )
            else:  # pragma: no cover
                print(f"error: unsupported command {args.command!r}", file=sys.stderr)
                await session.rollback()
                return 2
            await session.commit()
        except ValueError as exc:
            await session.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:
            await session.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1

    print(json.dumps(asdict(result), sort_keys=True))
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    finally:
        try:
            asyncio.run(database.close_db())
        except RuntimeError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
