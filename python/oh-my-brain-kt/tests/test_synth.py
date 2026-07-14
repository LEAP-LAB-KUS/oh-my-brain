import random

from kt.kc_catalog import CATALOG
from synth.config import STUDENT_MODELS
from synth.curriculum import plan_sequence
from synth.gates import (difficulty_monotonicity, learner_separation,
                         learning_slope, run_gates, spearman)
from synth.parsing import (extract_json_array, parse_choice, parse_kc_labels,
                           validate_question)
from synth.personas import DOMAINS, Persona, kc_domain, sample_personas


def test_domains_cover_catalog_exactly():
    seen = []
    for rng in DOMAINS.values():
        seen.extend(rng)
    assert sorted(seen) == list(range(100))
    assert len(CATALOG) == 100
    assert kc_domain(0) == "python"
    assert kc_domain(99) == "ai-ml"


def test_sample_personas_reproducible_and_bounded():
    a = sample_personas(200, STUDENT_MODELS, seed=1)
    b = sample_personas(200, STUDENT_MODELS, seed=1)
    assert [p.ability for p in a] == [p.ability for p in b]
    assert {p.model for p in a} == set(STUDENT_MODELS)
    for p in a:
        assert -2.0 <= p.ability <= 2.0
        assert 20 <= p.seq_len <= 200
        assert 2 <= len(p.focus_domains) <= 4
        assert 0.2 <= p.temperature("python") <= 1.6
        assert "Answer every quiz question honestly" in p.description()


def test_weak_persona_gets_higher_temperature():
    strong = Persona("s1", "m", 1.5, {d: 0.0 for d in DOMAINS}, 0.1, 50, ["python"])
    weak = Persona("s2", "m", -1.5, {d: 0.0 for d in DOMAINS}, 0.1, 50, ["python"])
    assert weak.temperature("python") > strong.temperature("python")


def test_plan_sequence_length_and_kc_reuse():
    persona = sample_personas(1, STUDENT_MODELS, seed=7)[0]
    bank = {kc: [{"q_id": f"q{kc}_{i}", "kc_id": kc, "difficulty": 0.1 * (i % 9 + 1),
                  "q": "x", "choices": ["a", "b", "c", "d"], "answer_idx": 0}
                 for i in range(10)]
            for kc in range(1, 101)}
    plan = plan_sequence(persona, bank, seed=11)
    assert len(plan) == persona.seq_len
    kcs = {q["kc_id"] for q in plan}
    assert 1 <= len(kcs) <= 25  # spiral over a handful of KCs, not all 100


def test_parse_choice_variants():
    assert parse_choice("B") == 1
    assert parse_choice("  c) because ...") == 2
    assert parse_choice("The answer is D.") == 3
    assert parse_choice("Answer: a") == 0
    assert parse_choice("either A or B") is None
    assert parse_choice("") is None
    assert parse_choice("42") is None


def test_extract_json_array():
    assert extract_json_array('x [1, 2] y') == [1, 2]
    assert extract_json_array('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert extract_json_array("no array") is None
    assert extract_json_array('{"a": [1]}') == [1]  # inner array is fine


def test_validate_question():
    names = {"deadlocks", "race-conditions"}
    good = {
        "q": "Which condition must hold for a deadlock to occur?",
        "choices": ["mutual exclusion", "preemption", "single thread", "gc pauses"],
        "answer_idx": 0,
        "difficulty": 0.55,
        "kcs": ["deadlocks", "race-conditions"],
    }
    v = validate_question(good, kc_names=names)
    assert v is not None and v["kcs"] == ["deadlocks", "race-conditions"]
    assert validate_question({**good, "answer_idx": 9}, kc_names=names) is None
    assert validate_question({**good, "difficulty": 1.5}, kc_names=names) is None
    assert validate_question({**good, "kcs": ["unknown-kc"]}, kc_names=names) is None
    assert validate_question({**good, "choices": ["a", "a", "b", "c"]}, kc_names=names) is None
    assert validate_question({**good, "q": "short?"}, kc_names=names) is None
    # single-KC via legacy "kc" key
    assert validate_question({**good, "kcs": None, "kc": "deadlocks"}, kc_names=names) is not None


def test_parse_kc_labels():
    assert parse_kc_labels('["Race Conditions", "locks/mutexes"]') == [
        "race-conditions", "locks-mutexes"]
    assert parse_kc_labels("deadlocks, python GIL\nextra-one, fourth-label") == [
        "deadlocks", "python-gil", "extra-one"]
    assert parse_kc_labels("") == []
    assert parse_kc_labels("!!!") == []


def _fake_interactions(n_students=40, seed=3):
    """IRT-style fake data with real learning + ability effects, for gate tests."""
    rng = random.Random(seed)
    abilities = {}
    interactions = []
    for s in range(n_students):
        sid = f"s{s}"
        theta = rng.gauss(0, 1)
        abilities[sid] = theta
        practice: dict[int, int] = {}
        for t in range(60):
            kc = rng.randint(1, 8)
            q = rng.randint(0, 4)
            difficulty = 0.15 + 0.15 * q
            k = practice.get(kc, 0)
            practice[kc] = k + 1
            p = 1 / (1 + pow(2.718, -(theta - (difficulty * 4 - 2) + 0.15 * k)))
            interactions.append({
                "student_id": sid, "kc_id": kc, "q_id": f"kc{kc}q{q}",
                "difficulty": difficulty, "correct": 1 if rng.random() < p else 0,
            })
    return interactions, abilities


def test_gates_pass_on_well_formed_data():
    interactions, abilities = _fake_interactions()
    report = run_gates(interactions, abilities, min_spearman=0.4,
                       min_separation=0.2, min_slope=0.0)
    assert report["passed"]["difficulty"], report["difficulty_monotonicity"]
    assert report["passed"]["separation"], report["learner_separation"]
    assert report["passed"]["learning"], report["learning_curve"]


def test_gates_fail_on_random_data():
    rng = random.Random(0)
    interactions = [{
        "student_id": f"s{i % 30}", "kc_id": 1, "q_id": f"q{i % 20}",
        "difficulty": rng.random(), "correct": rng.randint(0, 1),
    } for i in range(3000)]
    abilities = {f"s{i}": rng.gauss(0, 1) for i in range(30)}
    report = run_gates(interactions, abilities, min_spearman=0.4,
                       min_separation=0.2, min_slope=0.0)
    assert not report["passed"]["difficulty"]
    assert not report["passed"]["separation"]


def test_spearman_perfect_and_inverse():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) > 0.99
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) < -0.99
