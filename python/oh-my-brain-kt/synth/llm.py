"""Thin vLLM wrapper for batched chat with per-request sampling params."""
from __future__ import annotations


def load_llm(model: str, *, max_model_len: int = 2048, gpu_mem: float = 0.85):
    from vllm import LLM

    return LLM(model=model, max_model_len=max_model_len,
               gpu_memory_utilization=gpu_mem, dtype="auto",
               enable_prefix_caching=True)


def chat_batch(llm, conversations: list[list[dict]], *, temperatures: list[float],
               max_tokens: int, seed: int) -> list[str]:
    """Run a batch of chats; one output string per conversation."""
    from vllm import SamplingParams

    params = [SamplingParams(temperature=t, max_tokens=max_tokens, seed=seed + i)
              for i, t in enumerate(temperatures)]
    outputs = llm.chat(conversations, params, use_tqdm=False)
    return [o.outputs[0].text for o in outputs]
