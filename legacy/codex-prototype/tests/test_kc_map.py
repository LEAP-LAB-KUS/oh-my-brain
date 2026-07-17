"""R6: KC/Question numbering — stable ids, similarity mapping, sequence records."""
from harness.kc_map import KCStore


def test_same_question_gets_same_qid(tmp_path):
    store = KCStore(tmp_path / "kc.json")
    q1 = store.assign("What does a mutex protect?", kc_hint="concurrency")
    q2 = store.assign("What does a mutex protect?", kc_hint="concurrency")
    assert q1.q_id == q2.q_id
    assert q1.kc_id == q2.kc_id


def test_new_question_same_hint_maps_to_same_kc(tmp_path):
    store = KCStore(tmp_path / "kc.json")
    a = store.assign("What does a mutex protect?", kc_hint="concurrency")
    b = store.assign("Why can a deadlock occur?", kc_hint="concurrency")
    assert a.kc_id == b.kc_id
    assert a.q_id != b.q_id


def test_different_hint_new_kc(tmp_path):
    store = KCStore(tmp_path / "kc.json")
    a = store.assign("What does a mutex protect?", kc_hint="concurrency")
    b = store.assign("What is a closure?", kc_hint="functions")
    assert a.kc_id != b.kc_id


def test_store_persists_across_instances(tmp_path):
    path = tmp_path / "kc.json"
    a = KCStore(path).assign("What does a mutex protect?", kc_hint="concurrency")
    b = KCStore(path).assign("What does a mutex protect?", kc_hint="concurrency")
    assert (a.kc_id, a.q_id) == (b.kc_id, b.q_id)


def test_record_outcome_appends_sequence_row(tmp_path):
    store = KCStore(tmp_path / "kc.json")
    q = store.assign("What does a mutex protect?", kc_hint="concurrency")
    seq = tmp_path / "sequences.csv"
    store.record_outcome(seq, user_id="u1", q=q, correct=1)
    store.record_outcome(seq, user_id="u1", q=q, correct=0)
    rows = seq.read_text().strip().splitlines()
    assert rows[0] == "user_id,kc_id,q_id,correct,ts"
    assert rows[1].startswith(f"u1,{q.kc_id},{q.q_id},1,")
    assert rows[2].startswith(f"u1,{q.kc_id},{q.q_id},0,")
