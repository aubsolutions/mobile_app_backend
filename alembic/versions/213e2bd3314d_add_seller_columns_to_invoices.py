"""add seller columns to invoices

Revision ID: 213e2bd3314d
Revises: 4d50c1f0013c
Create Date: 2025-08-08 17:46:28.363046

"""
from alembic import op
import sqlalchemy as sa

# Alembic revision identifiers – ОСТАВЬ ТЕ, КОТОРЫЕ ALEMBIC УЖЕ СГЕНЕРИРОВАЛ:
revision = '213e2bd3314d'
down_revision = '4d50c1f0013c'
branch_labels = None
depends_on = None

def upgrade():
    # новые колонки в invoices
    op.add_column("invoices", sa.Column("seller_employee_id", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("seller_name", sa.String(), nullable=True))

    # FK на employees.id (при удалении сотрудника – seller_employee_id станет NULL)
    op.create_foreign_key(
        "fk_invoices_seller_employee",
        "invoices",
        "employees",
        ["seller_employee_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # индекс на seller_employee_id
    op.create_index("ix_invoices_seller_employee_id", "invoices", ["seller_employee_id"])

def downgrade():
    op.drop_index("ix_invoices_seller_employee_id", table_name="invoices")
    op.drop_constraint("fk_invoices_seller_employee", "invoices", type_="foreignkey")
    op.drop_column("invoices", "seller_name")
    op.drop_column("invoices", "seller_employee_id")