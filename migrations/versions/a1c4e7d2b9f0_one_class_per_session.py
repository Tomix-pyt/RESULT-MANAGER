"""one class per student per session (database-enforced)

Revision ID: a1c4e7d2b9f0
Revises: 327681938ff9
"""
from alembic import op
import sqlalchemy as sa

revision = "a1c4e7d2b9f0"
down_revision = "327681938ff9"
branch_labels = None
depends_on = None

FIND_DUPLICATES = """
SELECT st.admission_number, st.last_name, st.first_name, ses.name AS session_name,
       COUNT(*) AS n, MIN(c.name) AS first_class, MAX(c.name) AS last_class
FROM student_enrollments e
JOIN class_sessions cs ON cs.id = e.class_session_id
JOIN classes c ON c.id = cs.class_id
JOIN academic_sessions ses ON ses.id = cs.academic_session_id
JOIN students st ON st.id = e.student_id
GROUP BY st.id, st.admission_number, st.last_name, st.first_name, ses.id, ses.name
HAVING COUNT(*) > 1
ORDER BY ses.name, st.last_name
"""


def upgrade():
    bind = op.get_bind()

    # 1. Refuse (clearly) if the data already breaks the rule. Postgres DDL is transactional,
    #    so nothing is changed if we stop here.
    dups = bind.execute(sa.text(FIND_DUPLICATES)).fetchall()
    if dups:
        lines = "\n".join(
            f"  - {d.admission_number} {d.last_name} {d.first_name}: {d.n} classes in {d.session_name} "
            f"({d.first_class} / {d.last_class})" for d in dups)
        raise RuntimeError(
            "Cannot apply: some students are enrolled in more than one class in the same session:\n"
            f"{lines}\n\nFix: in the app open Classes > (the class) and remove the wrong enrollment "
            "for each student (or use Enrollment > Transfer), then run `flask --app run.py db upgrade` again. "
            "List them any time with: flask --app run.py check-enrollments")

    # 2. Add the column, fill it from the class session, then lock it down.
    op.add_column("student_enrollments", sa.Column("academic_session_id", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE student_enrollments
        SET academic_session_id = (SELECT cs.academic_session_id FROM class_sessions cs
                                   WHERE cs.id = student_enrollments.class_session_id)
    """)
    op.alter_column("student_enrollments", "academic_session_id", nullable=False)
    op.create_foreign_key("fk_student_enrollments_academic_session", "student_enrollments",
                          "academic_sessions", ["academic_session_id"], ["id"])
    op.drop_constraint("uq_student_class_session", "student_enrollments", type_="unique")
    op.create_unique_constraint("uq_student_enrollment_session", "student_enrollments",
                                ["student_id", "academic_session_id"])


def downgrade():
    op.drop_constraint("uq_student_enrollment_session", "student_enrollments", type_="unique")
    op.create_unique_constraint("uq_student_class_session", "student_enrollments",
                                ["student_id", "class_session_id"])
    op.drop_constraint("fk_student_enrollments_academic_session", "student_enrollments", type_="foreignkey")
    op.drop_column("student_enrollments", "academic_session_id")
