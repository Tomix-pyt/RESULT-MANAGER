import pytest
from decimal import Decimal as D
from app.extensions import db
from app.errors import ValidationError, PermissionDenied
from app.models import Result, Score, StudentTermReport, StudentTrait
from app.services import operator_service as ops, score_service as sc, result_service as rs, traits_service as tr


@pytest.fixture()
def school(world):
    """JSS 1: Maths + English, 3 students; each subject has CA1/CA2/CA3 (10 each) + Exam (70) = 100."""
    w = dict(world); op = w["op"]
    s3 = ops.add_student(op, admission_number="CSS/003", first_name="Chi", last_name="Obi")
    en3 = ops.enroll_student(op, student_id=s3.id, class_session_id=w["cs1"].id)
    scale = ops.create_grading_scale(op, name="Std", academic_session_id=w["ses"].id)
    for lo, hi, g, rem in [(75, 100, "A", "Distinction"), (65, 74, "B", "Very Good"), (55, 64, "C", "Good"),
                           (40, 54, "D", "Pass"), (0, 39, "F", "Fail")]:
        ops.add_grade_boundary(op, grading_scale_id=scale.id, min_score=lo, max_score=hi, grade=g, remark=rem)
    comps = {}
    for csub in (w["m1"], w["e1"]):
        for name, mx in [("CA 1", 10), ("CA 2", 10), ("CA 3", 10), ("Exam", 70)]:
            comps[(csub.id, name)] = ops.create_assessment_component(
                op, class_subject_id=csub.id, term_id=w["term"].id, name=name, max_score=mx, weight=mx)
    w.update(s3=s3, en3=en3, comps=comps)
    return w


def enter(w, enr, csub, ca1, ca2, ca3, exam):
    vals = {w["comps"][(csub.id, n)].id: str(v) for n, v in
            [("CA 1", ca1), ("CA 2", ca2), ("CA 3", ca3), ("Exam", exam)] if v is not None}
    return sc.save_student_scores(w["op"], enrollment_id=enr.id, term_id=w["term"].id, values=vals)


def result_of(w, student, csub):
    return Result.query.filter_by(student_id=student.id, class_subject_id=csub.id, term_id=w["term"].id).first()


def test_assessments_get_printed_columns_automatically_and_max_four(school):
    slots = sorted(c.report_slot for (cid, _), c in school["comps"].items() if cid == school["m1"].id)
    assert slots == [1, 2, 3, 4]
    with pytest.raises(ValidationError, match="at most 4"):
        ops.create_assessment_component(school["op"], class_subject_id=school["m1"].id, term_id=school["term"].id,
                                        name="Extra", max_score=5, weight=5)


def test_totals_grades_highest_lowest_and_positions(school):
    w = school
    enter(w, w["en1"], w["m1"], 9, 8, 10, 60)        # 87 -> A
    enter(w, w["en1"], w["e1"], 5, 5, 5, 40)         # 55 -> C
    s2_enr = [e for e in w["s2"].enrollments][0]
    enter(w, s2_enr, w["m1"], 7, 6, 8, 45)           # 66 -> B
    enter(w, s2_enr, w["e1"], 6, 6, 6, 50)           # 68 -> B
    enter(w, w["en3"], w["m1"], 7, 6, 8, 45)         # 66 -> B  (tie with s2 in Maths)
    r = result_of(w, w["s1"], w["m1"])
    assert (r.total_score, r.grade, r.remark) == (87, "A", "Distinction")
    assert (r.class_highest, r.class_lowest, r.position) == (87, 66, 1)
    assert result_of(w, w["s2"], w["m1"]).position == 2 and result_of(w, w["s3"], w["m1"]).position == 2   # tie
    assert result_of(w, w["s1"], w["e1"]).grade == "C"
    s1, s2 = (StudentTermReport.query.filter_by(enrollment_id=e.id).first() for e in (w["en1"], s2_enr))
    assert s1.total_obtained == 142 and s1.total_obtainable == 200 and s1.average == D("71.00")
    assert s2.total_obtained == 134 and s2.average == D("67.00")
    assert (s1.position, s2.position, s1.class_size) == (1, 2, 3)


def test_term_totals_use_every_class_subject_and_rank_students_with_missing_marks(school):
    w = school
    # Ada has both subjects, Ali only Maths, and Chi has no entered marks.
    enter(w, w["en1"], w["m1"], 10, 10, 10, 60)       # 90
    enter(w, w["en1"], w["e1"], 10, 10, 10, 50)       # 80
    s2_enr = w["s2"].enrollments[0]
    enter(w, s2_enr, w["m1"], 8, 8, 8, 40)            # 64

    reports = {
        enr.id: StudentTermReport.query.filter_by(enrollment_id=enr.id, term_id=w["term"].id).first()
        for enr in (w["en1"], s2_enr, w["en3"])
    }
    ada, ali = reports[w["en1"].id], reports[s2_enr.id]
    assert (ada.total_obtained, ada.total_obtainable, ada.average, ada.position) == (170, 200, D("85.00"), 1)
    assert (ali.total_obtained, ali.total_obtainable, ali.average, ali.position) == (64, 200, D("32.00"), 2)
    # A student with no entered marks has no result summary/position yet.
    assert reports[w["en3"].id] is None


def test_subject_totals_and_grades_are_normalized_to_100_for_legacy_weights(school):
    w = school
    components = [w["comps"][(w["m1"].id, name)] for name in ("CA 1", "CA 2", "CA 3", "Exam")]
    # Simulate an older saved assessment structure whose weights total 50, not 100.
    for comp in components:
        comp.weight //= 2
    db.session.flush()
    enter(w, w["en1"], w["m1"], 10, 10, 10, 70)
    result = result_of(w, w["s1"], w["m1"])
    assert result.total_score == 100
    assert result.grade == "A"


def test_annual_totals_use_every_class_subject_even_when_subject_is_missing(school):
    w = school
    enter(w, w["en1"], w["m1"], 10, 10, 10, 60)       # Maths annual average = 90
    data = rs.annual_class(w["cs1"].id)
    ada = data[w["en1"].id]
    ali = data[w["s2"].enrollments[0].id]
    assert (ada["obtained"], ada["obtainable"], ada["average"], ada["position"]) == (90, 200, D("45.00"), 1)
    assert ali["obtained"] == 0 and ali["obtainable"] == 200
    assert ali["average"] is None and ali["position"] is None


def test_blank_removes_a_score_and_half_marks_round_up(school):
    w = school
    enter(w, w["en1"], w["m1"], D("8.5"), 8, 8, 60)  # 8.5+8+8+60 = 84.5 -> 85 (half up)
    assert result_of(w, w["s1"], w["m1"]).total_score == 85
    enter(w, w["en1"], w["m1"], "", "", "", "")      # blanks delete the scores
    assert Score.query.filter_by(student_id=w["s1"].id).count() == 0
    assert result_of(w, w["s1"], w["m1"]) is None


def test_invalid_scores_save_nothing(school):
    w = school
    with pytest.raises(ValidationError, match="between 0 and 10"):
        enter(w, w["en1"], w["m1"], 11, 5, 5, 50)
    with pytest.raises(ValidationError, match="not a number"):
        enter(w, w["en1"], w["m1"], "abc", 5, 5, 50)
    with pytest.raises(ValidationError, match="between 0 and"):
        enter(w, w["en1"], w["m1"], -1, 5, 5, 50)
    assert Score.query.count() == 0                      # all-or-nothing


def test_a_zero_is_a_real_score_but_blank_is_not(school):
    enter(school, school["en1"], school["m1"], 0, None, None, None)
    assert Score.query.filter_by(student_id=school["s1"].id).count() == 1
    assert result_of(school, school["s1"], school["m1"]).total_score == 0


def test_lock_blocks_everyone_and_unlock_reopens(school):
    w = school
    enter(w, w["en1"], w["m1"], 9, 8, 10, 60)
    n = rs.set_lock(w["op"], class_session_id=w["cs1"].id, term_id=w["term"].id, lock=True)
    assert n > 0 and result_of(w, w["s1"], w["m1"]).status == "LOCKED"
    with pytest.raises(PermissionDenied, match="locked"):
        enter(w, w["en1"], w["m1"], 1, 1, 1, 1)
    with pytest.raises(PermissionDenied, match="locked"):             # even a student with no result row yet
        enter(w, w["en3"], w["m1"], 5, 5, 5, 50)
    rs.set_lock(w["op"], class_session_id=w["cs1"].id, term_id=w["term"].id, lock=False)
    assert result_of(w, w["s1"], w["m1"]).status == "REOPENED"
    enter(w, w["en1"], w["m1"], 1, 1, 1, 1)                            # editable again
    assert result_of(w, w["s1"], w["m1"]).total_score == 4
    assert result_of(w, w["s3"], w["m1"]) is None                      # empty placeholders were cleaned up


def test_locked_results_are_frozen_by_recompute(school):
    w = school
    enter(w, w["en1"], w["m1"], 9, 8, 10, 60)
    rs.set_lock(w["op"], class_session_id=w["cs1"].id, term_id=w["term"].id, lock=True)
    before = result_of(w, w["s1"], w["m1"]).total_score
    rs.compile_class_term(w["cs1"].id, w["term"].id); db.session.commit()
    assert result_of(w, w["s1"], w["m1"]).total_score == before


def test_suggested_ratings_are_stable_performance_based_and_never_overwrite_manual(school):
    w = school
    enter(w, w["en1"], w["m1"], 10, 10, 10, 65)      # 95 average -> ratings around 5
    enter(w, w["en1"], w["e1"], 10, 10, 10, 65)
    rows = {t.trait_key: t for t in StudentTrait.query.filter_by(enrollment_id=w["en1"].id)}
    assert len(rows) == 16 and all(4 <= t.rating <= 5 for t in rows.values()) and {t.source for t in rows.values()} == {"AUTO"}
    snapshot = {k: t.rating for k, t in rows.items()}
    rs.compile_class_term(w["cs1"].id, w["term"].id); db.session.commit()      # "reprint": nothing changes
    assert {t.trait_key: t.rating for t in StudentTrait.query.filter_by(enrollment_id=w["en1"].id)} == snapshot
    sc.save_student_scores(w["op"], enrollment_id=w["en1"].id, term_id=w["term"].id, values={},
                           ratings={"neatness": "2", "honesty": str(snapshot["honesty"])})
    got = {t.trait_key: t for t in StudentTrait.query.filter_by(enrollment_id=w["en1"].id)}
    assert got["neatness"].source == "MANUAL" and got["neatness"].rating == 2
    assert got["honesty"].source == "AUTO"                                     # unchanged value stays AUTO
    enter(w, w["en1"], w["m1"], 1, 1, 1, 1)                                    # performance drops: AUTO follows, MANUAL stays
    got = {t.trait_key: t for t in StudentTrait.query.filter_by(enrollment_id=w["en1"].id)}
    assert got["neatness"].rating == 2 and got["handwriting"].rating <= 4


def test_annual_is_average_of_terms_with_class_positions(school):
    w = school
    enter(w, w["en1"], w["m1"], 10, 10, 10, 60)      # term 1: 90
    t2 = ops.create_term(w["op"], academic_session_id=w["ses"].id, name="Second Term")
    for name, mx in [("CA 1", 10), ("CA 2", 10), ("CA 3", 10), ("Exam", 70)]:
        c = ops.create_assessment_component(w["op"], class_subject_id=w["m1"].id, term_id=t2.id, name=name, max_score=mx, weight=mx)
        w["comps"][(w["m1"].id, name, 2)] = c
    vals = {w["comps"][(w["m1"].id, n, 2)].id: v for n, v in [("CA 1", 5), ("CA 2", 5), ("CA 3", 5), ("Exam", 45)]}
    sc.save_student_scores(w["op"], enrollment_id=w["en1"].id, term_id=t2.id, values=vals)   # term 2: 60
    enter(w, w["en3"], w["m1"], 5, 5, 5, 45)         # s3 only has term 1: 60
    data = rs.annual_class(w["cs1"].id)
    a1 = data[w["en1"].id]["subjects"][w["m1"].id]
    assert a1["average"] == 75 and a1["position"] == 1 and a1["highest"] == 75 and a1["lowest"] == 60
    assert data[w["en3"].id]["subjects"][w["m1"].id]["average"] == 60
    assert data[w["en1"].id]["position"] == 1 and data[w["en1"].id]["class_size"] == 3
