"""R8: cold-start dummy sequence generation with solar-mini personas.

The LLM call is injected so tests run offline; live calls use the same
interface with the UPSTAGE client.
"""
from kt.dummy_gen import PERSONAS, generate_sequences, sequences_to_csv


def fake_llm(persona, questions):
    """Deterministic stand-in: skill-based threshold on question difficulty."""
    return [1 if persona["skill"] >= q["difficulty"] else 0 for q in questions]


def _questions():
    return [
        {"q_id": i + 1, "kc_id": (i % 3) + 1, "difficulty": (i % 5) / 5}
        for i in range(10)
    ]


def test_personas_are_diverse():
    assert len(PERSONAS) >= 6
    skills = {p["skill"] for p in PERSONAS}
    assert len(skills) >= 3  # multiple levels
    assert {p["name"] for p in PERSONAS}.__len__() == len(PERSONAS)


def test_generate_one_sequence_per_persona():
    seqs = generate_sequences(_questions(), llm=fake_llm)
    assert len(seqs) == len(PERSONAS)
    for user_id, seq in seqs.items():
        assert len(seq) == 10
        assert all(c in (0, 1) for _, c in seq)


def test_higher_skill_scores_higher():
    seqs = generate_sequences(_questions(), llm=fake_llm)
    by_name = {uid: sum(c for _, c in seq) for uid, seq in seqs.items()}
    best = max(PERSONAS, key=lambda p: p["skill"])["name"]
    worst = min(PERSONAS, key=lambda p: p["skill"])["name"]
    assert by_name[best] >= by_name[worst]


def test_csv_export(tmp_path):
    seqs = generate_sequences(_questions()[:2], llm=fake_llm)
    out = tmp_path / "sequences.csv"
    sequences_to_csv(seqs, out)
    lines = out.read_text().strip().splitlines()
    assert lines[0] == "user_id,kc_id,q_id,correct,ts"
    assert len(lines) == 1 + 2 * len(PERSONAS)
