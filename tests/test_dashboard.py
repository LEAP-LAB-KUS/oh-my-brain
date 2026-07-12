"""H2 (human usability eval): local learning dashboard generator."""
from pathlib import Path

from harness.dashboard import build_dashboard


def _seed(tmp_path: Path):
    logs = tmp_path / "logs"
    kt = tmp_path / "kt" / "data"
    logs.mkdir()
    kt.mkdir(parents=True)
    (logs / "prompts.jsonl").write_text(
        '{"ts": 1.0, "session_id": "s1", "prompt": "just fix it", "cwd": "/r"}\n')
    (logs / "assessments.jsonl").write_text(
        '{"ts": 1.0, "session_id": "s1", "score": 1.0, "trigger": true, "dimensions": {}}\n')
    (kt / "sequences.csv").write_text(
        "user_id,kc_id,q_id,correct,ts\nu1,1,1,1,2.0\nu1,1,2,0,3.0\nu1,2,3,1,4.0\n")
    return tmp_path


def test_builds_selfcontained_html(tmp_path):
    root = _seed(tmp_path)
    out = build_dashboard(root)
    assert out.exists() and out.suffix == ".html"
    html = out.read_text(encoding="utf-8")
    assert "<html" in html.lower()
    # self-contained: no external requests
    assert "http://" not in html and "https://" not in html


def test_dashboard_shows_kc_accuracy_and_counts(tmp_path):
    root = _seed(tmp_path)
    html = build_dashboard(root).read_text(encoding="utf-8")
    assert "KC 1" in html and "KC 2" in html
    assert "50%" in html   # kc1: 1/2
    assert "100%" in html  # kc2: 1/1
    assert "just fix it" in html  # recent prompt visible


def test_dashboard_handles_missing_data(tmp_path):
    out = build_dashboard(tmp_path)  # no logs at all
    assert "No data yet" in out.read_text(encoding="utf-8")


def test_kc_names_shown_when_available(tmp_path):
    # user feedback round 3: "KC 1" alone is meaningless; show the concept name
    root = _seed(tmp_path)
    (root / "kt" / "data" / "kc.json").write_text(
        '{"kcs": {"concurrency": 1, "web-http": 2}, "questions": {}}')
    html = build_dashboard(root).read_text(encoding="utf-8")
    assert "concurrency" in html
    assert "web-http" in html


def test_mastery_predictions_shown_with_status_badges(tmp_path):
    # user feedback round 4: show model-predicted mastery and mastered/learning status
    root = _seed(tmp_path)
    (root / "kt" / "data" / "kc.json").write_text(
        '{"kcs": {"concurrency": 1, "web-http": 2}, "questions": {}}')
    fake = {"1": 0.85, "2": 0.35}
    html = build_dashboard(root, mastery_fn=lambda kc, history: fake[kc])
    text = html.read_text(encoding="utf-8")
    assert "Mastery" in text and "85%" in text and "35%" in text
    assert "mastered" in text.lower()
    assert "needs work" in text.lower()


def test_dashboard_works_without_kt_model(tmp_path):
    root = _seed(tmp_path)
    html = build_dashboard(root, mastery_fn=None).read_text(encoding="utf-8")
    assert "Accuracy" in html  # observed stats still render
    # no crash, no bogus mastery column when model unavailable
    assert "Mastery (model)" not in html


def test_interactive_learning_map_embedded(tmp_path):
    # user feedback round 3: interactive learning map (self-contained SVG + JS)
    root = _seed(tmp_path)
    (root / "kt" / "data" / "kc.json").write_text(
        '{"kcs": {"concurrency": 1, "web-http": 2}, "questions": {}}')
    html = build_dashboard(root).read_text(encoding="utf-8")
    assert "<svg" in html and "learning map" in html.lower()
    assert "addEventListener" in html  # clickable nodes
    assert "http://" not in html and "https://" not in html  # still self-contained
