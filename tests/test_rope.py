"""RotaryPositionalEmbedding concurrency-safe behavior."""

from __future__ import annotations

import threading

import torch

from model.module import RotaryPositionalEmbedding


def _q_k(batch: int, heads: int, seq: int, head_dim: int) -> tuple[torch.Tensor, torch.Tensor]:
    q = torch.randn(batch, heads, seq, head_dim)
    k = torch.randn(batch, heads, seq, head_dim)
    return q, k


def test_rope_handles_sequential_different_seq_lengths() -> None:
    rope = RotaryPositionalEmbedding(dim=64)
    for seq in (32, 256, 66, 305, 64):
        q, k = _q_k(1, 4, seq, 64)
        out_q, out_k = rope(q, k)
        assert out_q.shape == q.shape
        assert out_k.shape == k.shape


def test_rope_handles_mismatched_q_k_lengths() -> None:
    rope = RotaryPositionalEmbedding(dim=32)
    q = torch.randn(1, 2, 8, 32)
    k = torch.randn(1, 2, 16, 32)
    out_q, out_k = rope(q, k)
    assert out_q.shape == q.shape
    assert out_k.shape == k.shape


def test_rope_threaded_different_seq_lengths() -> None:
    rope = RotaryPositionalEmbedding(dim=64)
    errors: list[BaseException] = []

    def worker(seq: int) -> None:
        try:
            for _ in range(20):
                q, k = _q_k(1, 4, seq, 64)
                out_q, out_k = rope(q, k)
                assert out_q.shape[-2] == seq
                assert out_k.shape[-2] == seq
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(seq,)) for seq in (32, 64, 128, 256, 66, 305)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
