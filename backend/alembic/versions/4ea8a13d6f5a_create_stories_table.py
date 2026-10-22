"""create stories table

Revision ID: 4ea8a13d6f5a
Revises: 9a1285cab52e
Create Date: 2026-10-22 12:12:06.762360
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4ea8a13d6f5a'
down_revision: Union[str, None] = '9a1285cab52e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    stories = op.create_table('stories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )

    # Histórias iniciais (fábulas de domínio público) para a lista nascer preenchida
    op.bulk_insert(stories, [
        {
            'title': 'A Raposa e as Uvas',
            'description': 'Uma raposa faminta tenta alcançar um cacho de uvas e descobre como a vaidade pode enganar.',
        },
        {
            'title': 'A Lebre e a Tartaruga',
            'description': 'Uma corrida entre a lebre veloz e a tartaruga persistente mostra o valor da constância.',
        },
        {
            'title': 'O Patinho Feio',
            'description': 'Um patinho rejeitado pelos outros bichos encontra o seu lugar ao se descobrir quem é.',
        },
    ])


def downgrade() -> None:
    op.drop_table('stories')
