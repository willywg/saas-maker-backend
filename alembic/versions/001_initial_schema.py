"""Initial schema with multi-tenant models

Revision ID: 001_initial
Revises:
Create Date: 2026-01-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema."""

    # Organizations table
    op.create_table(
        'organizations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )
    op.create_index('ix_organizations_slug', 'organizations', ['slug'])

    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # Organization members table (many-to-many with roles)
    op.create_table(
        'organization_members',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'user_id', name='uq_org_user')
    )
    op.create_index('ix_organization_members_organization_id', 'organization_members', ['organization_id'])
    op.create_index('ix_organization_members_user_id', 'organization_members', ['user_id'])

    # Invite tokens table
    op.create_table(
        'invite_tokens',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('token', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invite_tokens_email'), 'invite_tokens', ['email'], unique=False)
    op.create_index(op.f('ix_invite_tokens_organization_id'), 'invite_tokens', ['organization_id'], unique=False)
    op.create_index(op.f('ix_invite_tokens_token'), 'invite_tokens', ['token'], unique=True)


def downgrade() -> None:
    """Remove all tables."""
    op.drop_index(op.f('ix_invite_tokens_token'), table_name='invite_tokens')
    op.drop_index(op.f('ix_invite_tokens_organization_id'), table_name='invite_tokens')
    op.drop_index(op.f('ix_invite_tokens_email'), table_name='invite_tokens')
    op.drop_table('invite_tokens')

    op.drop_index('ix_organization_members_user_id', table_name='organization_members')
    op.drop_index('ix_organization_members_organization_id', table_name='organization_members')
    op.drop_table('organization_members')

    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')

    op.drop_index('ix_organizations_slug', table_name='organizations')
    op.drop_table('organizations')
