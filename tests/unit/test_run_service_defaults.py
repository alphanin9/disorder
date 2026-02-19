from types import SimpleNamespace

from control_plane.app.services.run_service import build_default_stop_criteria


def _make_challenge(flag_regex: str | None, ctf_default_regex: str | None):
    ctf = None if ctf_default_regex is None else SimpleNamespace(default_flag_regex=ctf_default_regex)
    return SimpleNamespace(flag_regex=flag_regex, ctf=ctf)


def test_challenge_override_regex_wins() -> None:
    challenge = _make_challenge(flag_regex=r"override\{.*\}", ctf_default_regex=r"ctf\{.*\}")
    criteria = build_default_stop_criteria(challenge)
    assert criteria["primary"]["config"]["regex"] == r"override\{.*\}"


def test_ctf_default_regex_used_when_challenge_missing() -> None:
    challenge = _make_challenge(flag_regex=None, ctf_default_regex=r"ctf\{.*\}")
    criteria = build_default_stop_criteria(challenge)
    assert criteria["primary"]["config"]["regex"] == r"ctf\{.*\}"


def test_global_default_regex_used_when_no_overrides() -> None:
    challenge = _make_challenge(flag_regex=None, ctf_default_regex=None)
    criteria = build_default_stop_criteria(challenge)
    assert criteria["primary"]["config"]["regex"] == r"flag\{.*?\}"
