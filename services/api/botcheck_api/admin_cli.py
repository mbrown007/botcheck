"""Administrative CLI entrypoints for BotCheck API."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from arq import create_pool
from arq.connections import RedisSettings as ArqRedisSettings

from . import database
from .config import settings
from .packs.service_sip_trunks import sync_sip_trunks
from .runs.service_judge import rejudge_run


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BotCheck administrative workflows.")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional DB URL override (defaults to configured API database).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "sync-sip-trunks",
        help="Sync outbound SIP trunk inventory from LiveKit into the local registry.",
    )
    rejudge = sub.add_parser(
        "rejudge-run",
        help="Re-enqueue a completed run for judging via the existing ARQ judge worker.",
    )
    rejudge.add_argument("--tenant-id", required=True, help="Tenant ID that owns the run.")
    rejudge.add_argument("--run-id", required=True, help="Run ID to rejudge.")
    rejudge.add_argument("--actor-id", required=True, help="Operator identity for audit_log.")
    rejudge.add_argument("--reason", default=None, help="Optional reason recorded in audit/event.")
    return parser


async def _run(args: argparse.Namespace) -> int:
    await database.init_db(args.database_url)
    factory = database.AsyncSessionLocal
    if factory is None:
        print("error: DB session factory is not initialized", file=sys.stderr)
        return 1

    async with factory() as session:
        try:
            if args.command == "sync-sip-trunks":
                synced = await sync_sip_trunks(session)
                result: dict[str, object] = {
                    "command": args.command,
                    "synced_count": len(synced),
                    "trunk_ids": [row.trunk_id for row in synced],
                }
            elif args.command == "rejudge-run":
                await database.apply_tenant_rls_context(session, args.tenant_id)
                arq_pool = await create_pool(ArqRedisSettings.from_dsn(settings.redis_url))
                try:
                    rejudge_result = await rejudge_run(
                        session,
                        run_id=args.run_id,
                        actor_id=args.actor_id,
                        arq_pool=arq_pool,
                        reason=args.reason,
                    )
                finally:
                    await arq_pool.close()
                result = {
                    "command": args.command,
                    "run_id": rejudge_result.run_id,
                    "previous_state": rejudge_result.previous_state,
                    "state": rejudge_result.state,
                    "tool_context_replayed": rejudge_result.tool_context_replayed,
                }
            else:  # pragma: no cover
                print(f"error: unsupported command {args.command!r}", file=sys.stderr)
                await session.rollback()
                return 2
            await session.commit()
        except Exception as exc:
            await session.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1

    print(json.dumps(result, sort_keys=True))
    return 0


async def _main_async(args: argparse.Namespace) -> int:
    try:
        return await _run(args)
    finally:
        await database.close_db()


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
