from app.models import AssessmentComponent, Score

def login(client, username):
    return client.post("/login", data={"username": username, "password": "password123"})


def test_school_wide_assessment_settings_sync_every_subject_and_term(client, world):
    login(client, "admin")
    response = client.post("/admin/assessment-settings", data={
        "name": ["Continuous Assessment", "Examination", "", ""],
        "max_score": ["30", "70", "", ""],
        "weight": ["30", "70", "", ""],
        "report_slot": ["1", "4", "", ""],
    }, follow_redirects=True)
    assert response.status_code == 200
    for csub in (world["m1"], world["e1"], world["m2"]):
        rows = AssessmentComponent.query.filter_by(class_subject_id=csub.id, term_id=world["term"].id).all()
        assert [(x.name, x.max_score, x.weight) for x in sorted(rows, key=lambda x: x.report_slot)] == [
            ("Continuous Assessment", 30, 30), ("Examination", 70, 70)
        ]


def test_staff_can_open_assigned_subject_and_save_student_scores(client, world):
    login(client, "teacher1")
    page = client.get(f"/staff/subjects/{world['m1'].id}")
    assert page.status_code == 200
    assert "Enter scores" in page.get_data(as_text=True)
    components = AssessmentComponent.query.filter_by(
        class_subject_id=world["m1"].id, term_id=world["term"].id
    ).order_by(AssessmentComponent.position).all()
    assert len(components) == 4
    enrollment = world["en1"]
    fields = {f"score_{enrollment.id}_{component.id}": "8" for component in components}
    response = client.post(f"/staff/subjects/{world['m1'].id}", data={
        "term_id": world["term"].id, **fields
    }, follow_redirects=True)
    assert response.status_code == 200
    assert Score.query.filter_by(student_id=enrollment.student_id).count() == 4


def test_staff_cannot_open_unassigned_subject(client, world):
    login(client, "teacher1")
    response = client.get(f"/staff/subjects/{world['e1'].id}")
    assert response.status_code == 403
