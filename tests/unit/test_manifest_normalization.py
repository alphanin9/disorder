from control_plane.app.adapters.ctfd import normalize_description, parse_remote_endpoints


def test_description_normalization_deterministic() -> None:
    raw = "<p>Hello<br>world</p>\r\n<p>Visit https://ctf.test/chal</p>"
    normalized = normalize_description(raw)
    assert normalized == "Hello\nworld\nVisit https://ctf.test/chal"


def test_remote_endpoint_parsing() -> None:
    text = "Connect with nc chall.ctf.local 31337 and visit http://chall.ctf.local:8080/path"
    endpoints = parse_remote_endpoints(text)

    assert {"type": "nc", "host": "chall.ctf.local", "port": 31337} in endpoints
    assert any(item.get("type") == "http" and item.get("url", "").startswith("http://chall.ctf.local") for item in endpoints)
