"""Seed question bank for cold-start dummy generation (R8).

24 programming-concept questions across 6 KCs. Difficulty in [0,1] is a prior
set by item design; the KT model learns actual difficulty from responses.
"""

KCS = {
    1: "python-basics",
    2: "concurrency",
    3: "web-http",
    4: "algorithms",
    5: "debugging-testing",
    6: "git-vcs",
}

QUESTIONS = [
    # kc 1: python basics
    {"q_id": 1, "kc_id": 1, "difficulty": 0.1, "text": "What does a Python list comprehension return?"},
    {"q_id": 2, "kc_id": 1, "difficulty": 0.3, "text": "Why does mutating a default argument (def f(x, acc=[])) persist across calls?"},
    {"q_id": 3, "kc_id": 1, "difficulty": 0.5, "text": "Explain the difference between __eq__ and is."},
    {"q_id": 4, "kc_id": 1, "difficulty": 0.7, "text": "How does the descriptor protocol make @property work?"},
    # kc 2: concurrency
    {"q_id": 5, "kc_id": 2, "difficulty": 0.2, "text": "What does a mutex protect?"},
    {"q_id": 6, "kc_id": 2, "difficulty": 0.4, "text": "Name the four conditions required for a deadlock."},
    {"q_id": 7, "kc_id": 2, "difficulty": 0.6, "text": "Why can Python threads not speed up CPU-bound code under the GIL?"},
    {"q_id": 8, "kc_id": 2, "difficulty": 0.8, "text": "Explain how asyncio event loop scheduling differs from OS thread preemption."},
    # kc 3: web/http
    {"q_id": 9, "kc_id": 3, "difficulty": 0.1, "text": "What does HTTP status 404 mean?"},
    {"q_id": 10, "kc_id": 3, "difficulty": 0.35, "text": "Why are PUT requests expected to be idempotent?"},
    {"q_id": 11, "kc_id": 3, "difficulty": 0.55, "text": "How does a JWT signature prevent token tampering?"},
    {"q_id": 12, "kc_id": 3, "difficulty": 0.75, "text": "Explain how CORS preflight decides whether a browser sends the real request."},
    # kc 4: algorithms
    {"q_id": 13, "kc_id": 4, "difficulty": 0.15, "text": "What is the time complexity of binary search?"},
    {"q_id": 14, "kc_id": 4, "difficulty": 0.4, "text": "Why is quicksort's worst case O(n^2) and when does it happen?"},
    {"q_id": 15, "kc_id": 4, "difficulty": 0.6, "text": "When does memoization turn exponential recursion into polynomial time?"},
    {"q_id": 16, "kc_id": 4, "difficulty": 0.85, "text": "Explain amortized O(1) for dynamic array append."},
    # kc 5: debugging/testing
    {"q_id": 17, "kc_id": 5, "difficulty": 0.15, "text": "What is the purpose of an assertion in a unit test?"},
    {"q_id": 18, "kc_id": 5, "difficulty": 0.35, "text": "Why should a regression test fail before the fix is applied?"},
    {"q_id": 19, "kc_id": 5, "difficulty": 0.55, "text": "What is a flaky test and name one common cause."},
    {"q_id": 20, "kc_id": 5, "difficulty": 0.75, "text": "How does bisecting (git bisect) find a fault-introducing commit in O(log n)?"},
    # kc 6: git/vcs
    {"q_id": 21, "kc_id": 6, "difficulty": 0.1, "text": "What does git commit record?"},
    {"q_id": 22, "kc_id": 6, "difficulty": 0.35, "text": "What is the difference between merge and rebase?"},
    {"q_id": 23, "kc_id": 6, "difficulty": 0.6, "text": "When does a fast-forward merge happen?"},
    {"q_id": 24, "kc_id": 6, "difficulty": 0.8, "text": "Explain how git detects renames without storing them."},
]
