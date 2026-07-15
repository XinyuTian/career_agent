from career_agent.merge import merge_list, merge_record, merge_scalar


def test_merge_scalar_fills_empty():
    value, conflict = merge_scalar(None, "x")
    assert value == "x" and conflict is None


def test_merge_scalar_conflict_keeps_existing():
    value, conflict = merge_scalar("old", "new")
    assert value == "old"
    assert conflict is not None


def test_merge_list_unions():
    assert merge_list(["a"], ["a", "b"]) == ["a", "b"]


def test_merge_record_reports_conflicts():
    merged, conflicts = merge_record(
        {"title": "A", "team": None, "responsibilities": ["x"]},
        {"title": "B", "team": "Platform", "responsibilities": ["y"]},
        list_fields={"responsibilities"},
    )
    assert merged["title"] == "A"
    assert merged["team"] == "Platform"
    assert merged["responsibilities"] == ["x", "y"]
    assert len(conflicts) == 1
