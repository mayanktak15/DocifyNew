"""Assign consultations to clinicians."""
from alembic import op
import sqlalchemy as sa

revision = '06b2d85cc0be'
down_revision = 'fce3a6f13385'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == 'sqlite':
        # Avoid a SQLite table rebuild, which loses reflected unnamed checks.
        op.execute('ALTER TABLE consultation ADD COLUMN clinician_id INTEGER REFERENCES user(id)')
    else:
        op.add_column('consultation', sa.Column('clinician_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_consultation_clinician', 'consultation', 'user', ['clinician_id'], ['id'])
    op.create_index('ix_consultation_clinician_id', 'consultation', ['clinician_id'])


def downgrade():
    op.drop_index('ix_consultation_clinician_id', table_name='consultation')
    if op.get_bind().dialect.name != 'sqlite':
        op.drop_constraint('fk_consultation_clinician', 'consultation', type_='foreignkey')
    op.drop_column('consultation', 'clinician_id')
