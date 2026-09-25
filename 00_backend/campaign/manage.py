"""Run operator commands with python -m campaign.manage --help."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

import asyncpg
from pydantic import ValidationError

from .config import OperatorDatabaseSettings
from .database import DatabaseStartupError, database_pool
from .migration import MigrationError, export_campaigns, load_export, read_session, write_export
from .operations import OperationError, OperatorService
from .repository import CampaignConflictError


def parser():
    root = argparse.ArgumentParser(description='Operator workspace provisioning and legacy campaign migration')
    commands = root.add_subparsers(dest='command', required=True)
    workspace = commands.add_parser('workspace-create')
    workspace.add_argument('--name', required=True)
    workspace.add_argument('--slug', required=True)
    workspace.add_argument('--creator-uid', required=True)
    for name in ('member-set', 'member-suspend'):
        member = commands.add_parser(name)
        member.add_argument('--workspace-id', type=UUID, required=True)
        member.add_argument('--uid', required=True)
        if name == 'member-set':
            member.add_argument('--role', choices=['viewer', 'editor', 'runner', 'approver'], required=True)
    export = commands.add_parser('campaigns-export', help='Read the old in-memory API before stopping its processes')
    export.add_argument('--source', nargs=2, action='append', metavar=('INSTANCE', 'ORIGIN'), required=True)
    export.add_argument('--session-file', type=Path)
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--quiesced', action='store_true', help='Acknowledge all source writes are paused and requests drained')
    for name in ('campaigns-import', 'campaigns-verify'):
        command = commands.add_parser(name)
        command.add_argument('--file', type=Path, required=True)
        command.add_argument('--import-id', type=UUID, required=True)
        if name == 'campaigns-import':
            command.add_argument('--name', required=True)
            command.add_argument('--slug', required=True)
            command.add_argument('--owner-uid', required=True)
            command.add_argument('--dry-run', action='store_true')
    return root


async def run(args):
    if args.command == 'campaigns-export':
        document = await export_campaigns(args.source, read_session(args.session_file), quiesced=args.quiesced)
        write_export(args.output, document)
        return dict(output=str(args.output), campaign_count=document.campaign_count, format_version=1)
    # Validate a file before opening a connection or looking up any identity.
    document = load_export(args.file) if args.command in {'campaigns-import', 'campaigns-verify'} else None
    settings = OperatorDatabaseSettings()
    async with database_pool(settings) as pool:
        service = OperatorService(pool)
        if args.command == 'workspace-create':
            return await service.workspace_create(args.name, args.slug, args.creator_uid)
        if args.command == 'member-set':
            return await service.member_set(args.workspace_id, args.uid, args.role)
        if args.command == 'member-suspend':
            return await service.member_suspend(args.workspace_id, args.uid)
        if args.command == 'campaigns-import':
            return await service.import_campaigns(document, args.import_id, args.name, args.slug,
                                                 args.owner_uid, dry_run=args.dry_run)
        return await service.verify_import(document, args.import_id)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except (MigrationError, OperationError, CampaignConflictError, DatabaseStartupError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValidationError:
        print('Invalid operator configuration or input; use explicit OPERATOR_DATABASE_* settings', file=sys.stderr)
        return 1
    except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, UnicodeError, TimeoutError):
        print('Operation failed; check operator permissions, file access, and database availability', file=sys.stderr)
        return 1
    print(json.dumps(result, default=str, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
