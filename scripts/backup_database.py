#!/usr/bin/env python3
"""Create and verify a PostgreSQL custom-format backup without overwriting files."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def backup(destination, database_url):
    """Write a new archive at destination; raise on failure and remove partial files."""
    destination = Path(destination).expanduser().absolute()
    if not database_url or not database_url.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
        raise ValueError('DATABASE_URL must be a PostgreSQL connection string')
    if not destination.parent.is_dir():
        raise ValueError('Backup directory does not exist')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Backup destination already exists')
    url = database_url.replace('postgresql+psycopg://', 'postgresql://', 1)
    env = os.environ.copy()
    from psycopg.conninfo import conninfo_to_dict
    from psycopg.pq import Conninfo
    # pg_dump treats PGDATABASE as a literal database name.
    mappings = {opt.keyword.decode(): opt.envvar.decode() for opt in Conninfo.get_defaults() if opt.envvar}
    for option, value in conninfo_to_dict(url).items():
        if option not in mappings:
            raise ValueError('Unsupported connection option')
        env[mappings[option]] = value
    fd, temporary = tempfile.mkstemp(prefix='.docify-backup-', suffix='.partial', dir=destination.parent)
    os.close(fd)
    try:
        subprocess.run(['pg_dump', '--format=custom', '--no-owner', '--no-privileges', '--file', temporary],
                       env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        subprocess.run(['pg_restore', '--list', temporary], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        # Hard-link in the same directory atomically refuses an existing destination.
        os.link(temporary, destination)
    finally:
        os.unlink(temporary)
    return destination


def main():
    parser = argparse.ArgumentParser(description='Create a new verified PostgreSQL archive.')
    parser.add_argument('destination', help='New archive path; existing files are never overwritten')
    args = parser.parse_args()
    try:
        path = backup(args.destination, os.environ.get('DATABASE_URL', ''))
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Backup failed. Check the PostgreSQL connection, client tools, permissions and destination.', file=sys.stderr)
        return 1
    print(f'Backup archive created: {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
