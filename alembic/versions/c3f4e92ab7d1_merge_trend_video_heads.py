"""merge trend video heads

Revision ID: c3f4e92ab7d1
Revises: 8e5ef6acf3fd, ab12c7f4d8a1
Create Date: 2026-04-13 00:10:00.000000

"""
from typing import Sequence, Union


revision: str = "c3f4e92ab7d1"
down_revision: Union[str, Sequence[str], None] = (
    "8e5ef6acf3fd",
    "ab12c7f4d8a1",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
