"""Named knowledge-component catalog (100 KCs), seeded into the KC store.

Replaces the early 6-KC demo bank. Names are stable identifiers the whole
harness shares: the KC store maps them to ids, the dashboard displays them,
and quiz generation picks the closest catalog name as its kc-hint so new
questions land on existing components instead of inventing near-duplicates.
"""

CATALOG: list[str] = [
    # python (10)
    "python-syntax-basics", "python-data-structures", "python-comprehensions",
    "python-mutability-and-references", "python-decorators", "python-generators-iterators",
    "python-typing", "python-exceptions", "python-modules-packaging", "python-oop",
    # javascript/typescript (8)
    "js-event-loop", "js-promises-async", "js-closures-scope", "js-this-binding",
    "js-modules", "ts-type-system", "ts-generics", "js-dom-events",
    # web (10)
    "http-methods-semantics", "http-caching", "http-status-codes", "rest-api-design",
    "cors", "cookies-sessions", "jwt-auth", "oauth-flows", "websockets", "graphql-basics",
    # frontend (6)
    "react-state-props", "react-hooks", "react-rendering-performance",
    "css-layout-flex-grid", "responsive-design", "web-accessibility",
    # databases (8)
    "sql-joins", "sql-indexing", "transactions-acid", "normalization",
    "orm-patterns", "nosql-modeling", "db-migrations", "query-optimization",
    # concurrency (8)
    "threads-vs-processes", "locks-mutexes", "deadlocks", "race-conditions",
    "async-await-model", "python-gil", "message-queues", "actor-model",
    # algorithms & data structures (10)
    "big-o-analysis", "arrays-vs-linked-lists", "hash-tables", "trees-traversal",
    "graphs-bfs-dfs", "sorting-algorithms", "binary-search", "dynamic-programming",
    "recursion", "amortized-analysis",
    # systems (8)
    "memory-management", "garbage-collection", "file-io-buffering", "unix-processes-signals",
    "environment-variables", "networking-tcp-udp", "dns-resolution", "load-balancing",
    # git & workflow (6)
    "git-commits-history", "git-branching-merging", "git-rebase", "git-conflicts",
    "git-bisect-debugging", "code-review-practices",
    # testing & debugging (8)
    "unit-testing", "tdd-workflow", "mocking-stubs", "integration-testing",
    "regression-testing", "flaky-tests", "debugging-strategies", "profiling-performance",
    # security (6)
    "input-validation-injection", "xss-csrf", "secrets-management", "hashing-vs-encryption",
    "tls-https", "least-privilege",
    # devops & cloud (8)
    "docker-containers", "ci-cd-pipelines", "logging-observability", "monitoring-alerting",
    "infrastructure-as-code", "serverless-model", "caching-strategies", "rate-limiting",
    # ai/ml engineering (4)
    "llm-prompting-basics", "embeddings-retrieval", "model-evaluation", "ml-data-leakage",
]

assert len(CATALOG) == 100, f"catalog must hold 100 KCs, has {len(CATALOG)}"
assert len(set(CATALOG)) == 100, "catalog names must be unique"


def seed_store(kc_json_path) -> int:
    """Seed the KC store with the full catalog (idempotent). Returns count."""
    import json
    from pathlib import Path

    p = Path(kc_json_path)
    data = {"kcs": {}, "questions": {}}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    next_id = max(data["kcs"].values(), default=0) + 1
    for name in CATALOG:
        if name not in data["kcs"]:
            data["kcs"][name] = next_id
            next_id += 1
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(data["kcs"])


if __name__ == "__main__":
    print("seeded", seed_store("kt/data/kc.json"), "KCs")
