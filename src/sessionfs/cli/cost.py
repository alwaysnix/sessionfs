"""Token cost estimation for AI model usage."""

from __future__ import annotations

from typing import Any

# Per-million-token pricing: (input, output, cache_read)
PRICING: dict[str, tuple[float, float, float]] = {
    "claude-opus-4": (15.0, 75.0, 1.5),
    "claude-sonnet-4": (3.0, 15.0, 0.3),
    "claude-haiku-4": (0.80, 4.0, 0.08),
    "claude-3-5-sonnet": (3.0, 15.0, 0.3),
    "claude-3-5-haiku": (0.80, 4.0, 0.08),
    "gpt-4.1": (2.0, 8.0, 0.5),
    "gpt-4.1-mini": (0.40, 1.60, 0.10),
    "gpt-4.1-nano": (0.10, 0.40, 0.025),
    "o4-mini": (1.10, 4.40, 0.275),
    "o3": (2.0, 8.0, 0.5),
    "o3-mini": (1.10, 4.40, 0.275),
}


def _match_model(model_id: str) -> tuple[float, float, float] | None:
    """Match a model ID to its pricing. Returns (input, output, cache) per million."""
    model_lower = model_id.lower()

    # Exact prefix match
    for prefix, pricing in PRICING.items():
        if model_lower.startswith(prefix):
            return pricing

    return None


def estimate_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
) -> dict[str, Any]:
    """Estimate cost for token usage.

    Args:
        model_id: Model identifier (e.g., "claude-opus-4-6").
        input_tokens: Total input tokens (includes cache reads).
        output_tokens: Output tokens generated.
        cache_read_tokens: Tokens served from cache (subset of input_tokens).

    Returns:
        Dict with cost breakdown and total_cost_usd.
    """
    pricing = _match_model(model_id)
    model_matched = pricing is not None

    if pricing is None:
        pricing = (0.0, 0.0, 0.0)

    input_per_m, output_per_m, cache_per_m = pricing

    non_cached_input = max(0, input_tokens - cache_read_tokens)
    input_cost = (non_cached_input / 1_000_000) * input_per_m
    cache_cost = (cache_read_tokens / 1_000_000) * cache_per_m
    output_cost = (output_tokens / 1_000_000) * output_per_m
    total_cost = input_cost + cache_cost + output_cost

    # What would have been charged without cache
    cache_savings = (cache_read_tokens / 1_000_000) * (input_per_m - cache_per_m)

    return {
        "model_id": model_id,
        "model_matched": model_matched,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "cache_cost_usd": round(cache_cost, 6),
        "total_cost_usd": round(total_cost, 6),
        "cache_savings_usd": round(cache_savings, 6),
    }
