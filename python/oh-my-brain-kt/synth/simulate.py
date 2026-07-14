"""Simulate learners answering the question bank with small local models.

One process handles ONE student model (vLLM holds the GPU); run once per
model in config.STUDENT_MODELS:

  .venv-vllm/bin/python -m synth.simulate --model Qwen/Qwen2.5-0.5B-Instruct \
      [--students-per-model 1000] [--pilot]

Each student answers question-by-question. Learning is induced two ways:
the prompt carries per-KC practice history ("you practiced this concept k
times, reviewed material after mistakes"), and decoding temperature decays
with practice at the persona's learning rate (study makes you less guessy).

Outputs (append-safe per model):
  synth/data/interactions_<tag>.jsonl   one row per answer
  synth/logs/simulate_<tag>.json        throughput/parse stats + per-model gates
"""
from __future__ import annotations

import argparse
import json
import random
import time

from synth.config import (DATA_DIR, GATE_DIFFICULTY_SPEARMAN, GATE_LEARNER_SEPARATION,
                          GATE_LEARNING_SLOPE, LOGS_DIR, N_STUDENTS, SEED,
                          STUDENT_MODELS)
from synth.curriculum import plan_sequence
from synth.gates import run_gates
from synth.llm import chat_batch, load_llm
from synth.parsing import parse_choice
from synth.personas import Persona, kc_domain, sample_personas

LETTERS = "ABCD"
CHUNK = 4096  # prompts per vLLM batch


def load_questions(path) -> dict[int, list[dict]]:
    by_kc: dict[int, list[dict]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            by_kc.setdefault(q["kc_id"], []).append(q)
    return by_kc


def practice_temperature(persona: Persona, domain: str, k: int) -> float:
    """Base persona temperature, decayed by practice (bounded)."""
    base = persona.temperature(domain)
    decay = 1.0 - 0.9 * persona.learning_rate * min(k, 8) / 8 * 3.0
    return max(0.15, base * max(0.25, decay))


def question_prompt(persona: Persona, q: dict, k: int, last_wrong: bool) -> list[dict]:
    kc_name = q["kcs"][0]
    history = "This is your first time practicing this concept."
    if k > 0:
        studied = " After wrong answers you reviewed a short study page on it." if last_wrong else ""
        history = f"You have already practiced '{kc_name}' {k} time(s).{studied}"
    choices = "\n".join(f"{LETTERS[i]}) {c}" for i, c in enumerate(q["choices"]))
    return [
        {"role": "system", "content": persona.description() +
         " Reply with ONLY one letter: A, B, C, or D."},
        {"role": "user", "content": f"{history}\nQuiz on '{kc_name}':\n{q['q']}\n{choices}\nYour answer:"},
    ]


def simulate_students(llm, personas: list[Persona], questions_by_kc: dict[int, list[dict]],
                      *, seed: int) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    # plan every student, then flatten into one prompt list for max batching;
    # practice counts are computable in advance because plans are fixed.
    interactions: list[dict] = []
    convs: list[list[dict]] = []
    temps: list[float] = []
    meta: list[tuple] = []
    for persona in personas:
        plan = plan_sequence(persona, questions_by_kc, seed=rng.randrange(1 << 30))
        practice: dict[int, int] = {}
        wrong_seen: dict[int, bool] = {}
        for t, q in enumerate(plan):
            kc = q["kc_id"]
            k = practice.get(kc, 0)
            practice[kc] = k + 1
            domain = kc_domain(kc - 1)
            convs.append(question_prompt(persona, q, k, wrong_seen.get(kc, False)))
            temps.append(practice_temperature(persona, domain, k))
            meta.append((persona, t, q, k))
            # optimistic wrong-marker: real outcome unknown until batch returns;
            # mark "studied" from the 2nd practice onward (harness always
            # follows a graded answer with material, so studying is the norm)
            wrong_seen[kc] = True

    parse_failures = 0
    replies = []
    for i in range(0, len(convs), CHUNK):
        replies.extend(chat_batch(llm, convs[i:i + CHUNK],
                                  temperatures=temps[i:i + CHUNK],
                                  max_tokens=6, seed=seed + i))
    for (persona, t, q, k), reply in zip(meta, replies):
        choice = parse_choice(reply)
        if choice is None:
            parse_failures += 1
            choice = rng.randrange(4)  # unparseable = flustered guess
        interactions.append({
            "student_id": persona.student_id,
            "model": persona.model,
            "t": t,
            "q_id": q["q_id"],
            "kc_id": q["kc_id"],
            "kc_ids": q["kc_ids"],
            "difficulty": q["difficulty"],
            "practice_k": k,
            "choice": choice,
            "correct": 1 if choice == q["answer_idx"] else 0,
        })
    stats = {"prompts": len(convs), "parse_failures": parse_failures,
             "parse_failure_rate": round(parse_failures / max(len(convs), 1), 4)}
    return interactions, stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--students-per-model", type=int,
                    default=N_STUDENTS // len(STUDENT_MODELS))
    ap.add_argument("--pilot", action="store_true",
                    help="small run (50 students) for gate validation")
    ap.add_argument("--questions", default=str(DATA_DIR / "questions.jsonl"))
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    n_per_model = 50 if args.pilot else args.students_per_model
    tag = args.tag or (args.model.split("/")[-1] + ("-pilot" if args.pilot else ""))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # sample the FULL population once (deterministic), then keep this model's slice
    personas_all = sample_personas(N_STUDENTS, STUDENT_MODELS, seed=SEED)
    personas = [p for p in personas_all if p.model == args.model][:n_per_model]
    questions_by_kc = load_questions(args.questions)

    t0 = time.time()
    llm = load_llm(args.model)
    load_s = time.time() - t0
    t1 = time.time()
    interactions, stats = simulate_students(llm, personas, questions_by_kc,
                                            seed=SEED + hash(args.model) % 100000)
    gen_s = time.time() - t1

    out_path = DATA_DIR / f"interactions_{tag}.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for it in interactions:
            f.write(json.dumps(it) + "\n")

    abilities = {p.student_id: p.ability for p in personas}
    gates = run_gates(interactions, abilities,
                      min_spearman=GATE_DIFFICULTY_SPEARMAN,
                      min_separation=GATE_LEARNER_SEPARATION,
                      min_slope=GATE_LEARNING_SLOPE)
    summary = {
        "model": args.model, "tag": tag, "students": len(personas),
        "interactions": len(interactions),
        "load_seconds": round(load_s, 1), "gen_seconds": round(gen_s, 1),
        "answers_per_second": round(len(interactions) / max(gen_s, 1e-9), 1),
        **stats,
        "gates": gates,
    }
    (LOGS_DIR / f"simulate_{tag}.json").write_text(json.dumps(summary, indent=1),
                                                   encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "gates"}))
    print(json.dumps(gates))


if __name__ == "__main__":
    main()
