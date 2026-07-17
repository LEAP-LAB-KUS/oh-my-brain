"""Round-3 feedback: pre-styled template for generated learning materials."""
from harness.material_page import build_material_page


def test_builds_templated_selfcontained_page(tmp_path):
    out = build_material_page(
        tmp_path, title="Event Loops Explained", kc="concurrency",
        body_html="<p>An event loop schedules tasks cooperatively.</p>",
        image="loop.png", questions=["Why can one slow callback block everything?"])
    assert out.exists()
    h = out.read_text(encoding="utf-8")
    assert "Event Loops Explained" in h and "concurrency" in h
    assert "loop.png" in h and "Check yourself" in h
    assert "http://" not in h and "https://" not in h  # self-contained styling
    assert out.name == "event-loops-explained.html"


def test_no_answers_in_selfcheck_and_optional_media(tmp_path):
    out = build_material_page(tmp_path, title="X", kc="k", body_html="<p>b</p>")
    h = out.read_text(encoding="utf-8")
    assert "Check yourself" not in h  # no questions given
    assert "<video" not in h and "<img" not in h
