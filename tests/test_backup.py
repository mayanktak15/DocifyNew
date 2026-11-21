import importlib.util
import os
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('backup_database', Path(__file__).resolve().parents[1] / 'scripts' / 'backup_database.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_backup_verifies_before_publish_and_hides_credentials(tmp_path, monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == 'pg_dump':
            Path(args[-1]).write_bytes(b'archive')
        else:
            assert not (tmp_path / 'backup.dump').exists()
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(module.subprocess, 'run', run)
    destination = tmp_path / 'backup.dump'
    result = module.backup(destination, 'postgresql+psycopg://user:secret@db/docify')
    assert result.read_bytes() == b'archive'
    assert result.stat().st_mode & 0o777 == 0o600
    assert [call[0][0] for call in calls] == ['pg_dump', 'pg_restore']
    assert all('secret' not in str(args) for args, _ in calls)
    assert calls[0][1]['env']['PGDATABASE'] == 'docify'
    assert not list(tmp_path.glob('*.partial'))
    with pytest.raises(FileExistsError):
        module.backup(destination, 'postgresql://db/docify')
    assert result.read_bytes() == b'archive'


def test_failed_backup_removes_partial_archive(tmp_path, monkeypatch):
    def fail(args, **kwargs):
        raise subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(module.subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        module.backup(tmp_path / 'backup.dump', 'postgresql://db/docify')
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        module.backup(tmp_path / 'backup.dump', 'sqlite:///local.db')


def test_archive_verification_failure_does_not_publish(tmp_path, monkeypatch):
    def run(args, **kwargs):
        if args[0] == 'pg_dump':
            Path(args[-1]).write_bytes(b'bad archive')
            return subprocess.CompletedProcess(args, 0)
        raise subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(module.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        module.backup(tmp_path / 'backup.dump', 'postgresql://db/docify')
    assert list(tmp_path.iterdir()) == []
