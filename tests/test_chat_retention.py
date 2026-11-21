from datetime import timedelta
from app import AuditLog, ChatHistory, db, now
from test_core import client, register


def test_retention_dry_run_batch_cutoff_and_audit(client):
    register(client, 'retention@example.com')
    current = now()
    db.session.add_all([
        ChatHistory(user_id=1, query='Sensitive first', response='Private', provider='fallback', created_at=current - timedelta(days=100)),
        ChatHistory(user_id=1, query='Sensitive second', response='Private', provider='fallback', created_at=current - timedelta(days=95)),
        ChatHistory(user_id=1, query='Recent', response='Private', provider='fallback', created_at=current - timedelta(days=5)),
    ])
    db.session.commit()
    runner = client.application.test_cli_runner()
    preview = runner.invoke(args=['purge-chat-history', '--older-than-days', '90', '--batch-size', '1'])
    assert preview.exit_code == 0 and '2 eligible' in preview.output and 'No changes made' in preview.output
    assert db.session.execute(db.select(db.func.count()).select_from(ChatHistory)).scalar_one() == 3
    result = runner.invoke(args=['purge-chat-history', '--older-than-days', '90', '--batch-size', '1', '--execute'])
    assert result.exit_code == 0 and 'Deleted 1' in result.output
    remaining = db.session.execute(db.select(ChatHistory).order_by(ChatHistory.id)).scalars().all()
    assert [item.query for item in remaining] == ['Sensitive second', 'Recent']
    event = db.session.execute(db.select(AuditLog).filter_by(action='HARD_DELETE', record_type='chat_history')).scalar_one()
    assert event.actor_id is None and event.record_id == 1 and event.changed_fields == []
    result = runner.invoke(args=['purge-chat-history', '--older-than-days', '90', '--execute'])
    assert result.exit_code == 0 and 'Deleted 1' in result.output
    assert runner.invoke(args=['purge-chat-history', '--older-than-days', '90', '--execute']).output.startswith('Deleted 0')
    assert db.session.execute(db.select(ChatHistory.query)).scalar_one() == 'Recent'


def test_retention_rejects_missing_and_invalid_limits(client):
    runner = client.application.test_cli_runner()
    assert runner.invoke(args=['purge-chat-history']).exit_code != 0
    assert runner.invoke(args=['purge-chat-history', '--older-than-days', '0', '--execute']).exit_code != 0
    assert runner.invoke(args=['purge-chat-history', '--older-than-days', '90', '--batch-size', '0', '--execute']).exit_code != 0
