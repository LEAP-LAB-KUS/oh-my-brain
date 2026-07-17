"""Persona sampling for simulated learners.

Each persona has a latent overall ability, per-domain offsets, and a
learning rate. The natural-language description conditions the small LLM;
the latents also set the sampling temperature (weaker learner -> noisier
answering) so ability differences survive small-model role-play limits.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from kt.kc_catalog import CATALOG

# contiguous slices of the 100-KC catalog (kept in sync with kc_catalog.py)
DOMAINS: dict[str, range] = {
    "python": range(0, 10),
    "javascript-typescript": range(10, 18),
    "web-http": range(18, 28),
    "frontend": range(28, 34),
    "databases": range(34, 42),
    "concurrency": range(42, 50),
    "algorithms": range(50, 60),
    "systems": range(60, 68),
    "git-workflow": range(68, 74),
    "testing-debugging": range(74, 82),
    "security": range(82, 88),
    "devops-cloud": range(88, 96),
    "ai-ml": range(96, 100),
}


def kc_domain(kc_index0: int) -> str:
    """Domain name for a 0-based catalog index."""
    for name, rng in DOMAINS.items():
        if kc_index0 in rng:
            return name
    raise ValueError(f"kc index {kc_index0} outside catalog")


LEVELS = [
    (-10.0, "complete beginner who has only written a few scripts"),
    (-0.8, "junior developer with about one year of experience"),
    (0.2, "mid-level developer comfortable with day-to-day work"),
    (1.0, "senior developer with broad, deep experience"),
]

SKILL_WORDS = [
    (-10.0, "very weak"),
    (-1.0, "weak"),
    (-0.3, "average"),
    (0.5, "strong"),
    (1.2, "expert"),
]


def _bucket(theta: float, table: list[tuple[float, str]]) -> str:
    label = table[0][1]
    for threshold, text in table:
        if theta >= threshold:
            label = text
    return label


@dataclass
class Persona:
    student_id: str
    model: str
    ability: float
    domain_offsets: dict[str, float]
    learning_rate: float
    seq_len: int
    focus_domains: list[str] = field(default_factory=list)

    def theta(self, domain: str) -> float:
        return self.ability + self.domain_offsets[domain]

    def temperature(self, domain: str) -> float:
        """Weaker persona -> noisier decoding (guessy behavior)."""
        t = 1.1 - 0.35 * self.theta(domain)
        return max(0.2, min(1.6, t))

    def description(self) -> str:
        level = _bucket(self.ability, LEVELS)
        strong = [d for d in self.focus_domains if self.theta(d) >= 0.5]
        weak = [d for d in self.focus_domains if self.theta(d) <= -0.5]
        parts = [f"You are a {level}."]
        if strong:
            parts.append(f"You are strong at {', '.join(strong)}.")
        if weak:
            parts.append(
                f"You are {_bucket(min(self.theta(d) for d in weak), SKILL_WORDS)} at "
                f"{', '.join(weak)} and often confuse related ideas there."
            )
        parts.append(
            "Answer every quiz question honestly AT YOUR OWN skill level: when your "
            "persona would not know the answer, pick the choice that merely seems "
            "plausible without careful reasoning."
        )
        return " ".join(parts)


def sample_personas(n: int, models: list[str], *, seed: int) -> list[Persona]:
    rng = random.Random(seed)
    personas = []
    domains = list(DOMAINS)
    for i in range(n):
        ability = max(-2.0, min(2.0, rng.gauss(0, 0.9)))
        offsets = {d: rng.gauss(0, 0.7) for d in domains}
        n_focus = rng.randint(2, 4)
        focus = rng.sample(domains, n_focus)
        # log-normal-ish sequence length, clipped (ASSIST09 mean ~75)
        seq_len = int(min(max(rng.lognormvariate(4.15, 0.55), 20), 200))
        personas.append(
            Persona(
                student_id=f"s{i:05d}",
                model=models[i % len(models)],
                ability=ability,
                domain_offsets=offsets,
                learning_rate=rng.uniform(0.06, 0.3),
                seq_len=seq_len,
                focus_domains=focus,
            )
        )
    return personas
