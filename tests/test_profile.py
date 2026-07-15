# tests/test_profile.py
from career_agent.profile import load_profile, save_profile


def test_profile_roundtrip(tmp_path):
    path = tmp_path / "profile.json"
    save_profile({"name": "Ada"}, path=path)
    assert load_profile(path=path)["name"] == "Ada"
