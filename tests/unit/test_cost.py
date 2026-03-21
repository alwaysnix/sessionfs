"""Tests for cost estimation."""

from __future__ import annotations

from sessionfs.cli.cost import estimate_cost


def test_known_model():
    result = estimate_cost("claude-opus-4-6", input_tokens=1_000_000, output_tokens=500_000)
    assert result["model_matched"] is True
    assert result["input_cost_usd"] == 15.0
    assert result["output_cost_usd"] == 37.5
    assert result["total_cost_usd"] == 52.5


def test_unknown_model():
    result = estimate_cost("unknown-model", input_tokens=100, output_tokens=50)
    assert result["model_matched"] is False
    assert result["total_cost_usd"] == 0.0


def test_cache_savings():
    result = estimate_cost(
        "claude-opus-4-6",
        input_tokens=1_000_000,
        output_tokens=0,
        cache_read_tokens=500_000,
    )
    assert result["cache_savings_usd"] > 0
    # Cache read is cheaper than full input
    assert result["cache_cost_usd"] < result["input_cost_usd"]


def test_zero_tokens():
    result = estimate_cost("claude-opus-4-6", input_tokens=0, output_tokens=0)
    assert result["total_cost_usd"] == 0.0
    assert result["cache_savings_usd"] == 0.0
