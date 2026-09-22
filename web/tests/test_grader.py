

def test_subset_grade5_only(exam_and_keys):
    exam, keys = exam_and_keys
    g5 = [it["id"].split("#", 1)[1] for it in exam["items"] if it.get("grade") == 5]
    assert g5 and len(g5) < len(exam["items"])
    answers = {sid: keys[sid]["answer"] for sid in g5}
    answers["3-1"] = keys["3-1"]["answer"]  # grade-6 item answered but not in subset -> ignored
    r = grade_submission(answers, keys, exam, item_ids=g5)
    assert r["itemCount"] == len(g5) == r["max"] == r["score"]
    assert set(r["perItem"]) == set(g5)
    assert set(r["perGrade"]) == {"5"}
    assert all(v["items"] > 0 for v in r["perTopic"].values())


def test_report_scope_and_topics(exam_and_keys):
    exam, keys = exam_and_keys
    g5 = [it["id"].split("#", 1)[1] for it in exam["items"] if it.get("grade") == 5]
    r = grade_submission({}, keys, exam, item_ids=g5)
    subject, html = render_report("共子", exam, r, "https://x.web.app", "a1", grade_filter=5)
    assert "[小5まで]" in subject
    assert "分野別" in html and "割合・食塩水" in html
