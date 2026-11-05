"""results engine: printed columns, class highest/lowest, term reports, ratings, form teacher

Revision ID: 34c4f89017b8
Revises: a1c4e7d2b9f0
"""
from alembic import op
import sqlalchemy as sa

revision = "34c4f89017b8"
down_revision = "a1c4e7d2b9f0"
branch_labels = None
depends_on = None


def _timestamps():
    return [sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False)]


def upgrade():
    op.create_table(
        "student_term_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("total_obtained", sa.Numeric(8, 2), nullable=True),
        sa.Column("total_obtainable", sa.Numeric(8, 2), nullable=True),
        sa.Column("average", sa.Numeric(6, 2), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("class_size", sa.Integer(), nullable=True),
        sa.Column("form_teacher_remark", sa.Text(), nullable=True),
        sa.Column("principal_remark", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["enrollment_id"], ["student_enrollments.id"]),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("enrollment_id", "term_id", name="uq_term_report"),
    )
    op.create_table(
        "student_traits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("trait_key", sa.String(length=30), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_trait_rating"),
        sa.CheckConstraint("source IN ('AUTO','MANUAL')", name="ck_trait_source"),
        sa.ForeignKeyConstraint(["enrollment_id"], ["student_enrollments.id"]),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("enrollment_id", "term_id", "trait_key", name="uq_student_trait"),
    )
    op.add_column("class_sessions", sa.Column("form_teacher_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_class_sessions_form_teacher", "class_sessions", "users", ["form_teacher_id"], ["id"])
    op.add_column("results", sa.Column("class_highest", sa.Numeric(6, 2), nullable=True))
    op.add_column("results", sa.Column("class_lowest", sa.Numeric(6, 2), nullable=True))
    op.add_column("terms", sa.Column("next_term_begins", sa.Date(), nullable=True))
    op.add_column("assessment_components", sa.Column("report_slot", sa.Integer(), nullable=True))

    # Existing assessments: give the first four of each subject+term a printed column, in their
    # display order (1'st CA, 2'nd CA, 3'rd CA, Exams). Any beyond four stay NULL (not printed).
    op.execute("""
        UPDATE assessment_components ac SET report_slot = ranked.slot
        FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY class_subject_id, term_id
                                            ORDER BY COALESCE(position, 9999), id) AS slot
              FROM assessment_components) ranked
        WHERE ac.id = ranked.id AND ranked.slot <= 4
    """)
    op.create_check_constraint("ck_assessment_report_slot", "assessment_components",
                               "report_slot IS NULL OR report_slot BETWEEN 1 AND 4")
    op.create_unique_constraint("uq_assessment_report_slot", "assessment_components",
                                ["class_subject_id", "term_id", "report_slot"])


def downgrade():
    op.drop_constraint("uq_assessment_report_slot", "assessment_components", type_="unique")
    op.drop_constraint("ck_assessment_report_slot", "assessment_components", type_="check")
    op.drop_column("assessment_components", "report_slot")
    op.drop_column("terms", "next_term_begins")
    op.drop_column("results", "class_lowest")
    op.drop_column("results", "class_highest")
    op.drop_constraint("fk_class_sessions_form_teacher", "class_sessions", type_="foreignkey")
    op.drop_column("class_sessions", "form_teacher_id")
    op.drop_table("student_traits")
    op.drop_table("student_term_reports")
