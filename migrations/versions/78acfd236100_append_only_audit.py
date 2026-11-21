"""Prevent changes to existing audit rows on supported databases."""
from alembic import op

revision = '78acfd236100'
down_revision = '62ad8780da6c'
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == 'sqlite':
        op.execute("CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END")
        op.execute("CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END")
    elif dialect == 'postgresql':
        op.execute("""CREATE FUNCTION docify_reject_audit_change() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'audit log is append-only'; END;
        $$ LANGUAGE plpgsql""")
        op.execute('CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_log FOR EACH STATEMENT EXECUTE FUNCTION docify_reject_audit_change()')
    else:
        raise RuntimeError('Audit immutability is supported only on SQLite and PostgreSQL')


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == 'sqlite':
        op.execute('DROP TRIGGER audit_log_no_update')
        op.execute('DROP TRIGGER audit_log_no_delete')
    elif dialect == 'postgresql':
        op.execute('DROP TRIGGER audit_log_no_change ON audit_log')
        op.execute('DROP FUNCTION docify_reject_audit_change()')
    else:
        raise RuntimeError('Audit immutability is supported only on SQLite and PostgreSQL')
