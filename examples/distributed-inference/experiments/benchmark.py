#!/usr/bin/env python3
"""Simulated distributed inference benchmark.

Simulates pipeline-parallel inference across multiple stages with
configurable latency, compression, and stage count. Outputs metrics
Autolab can parse.

Usage:
    python benchmark.py --stages 2 --latency-ms 10 --compression none --tokens 20
"""

import argparse
import math
import random
import time


def simulate_inference(
    stages: int,
    latency_ms: float,
    compression: str,
    tokens: int,
    seed: int,
) -> dict:
    """Simulate distributed inference and return metrics."""
    random.seed(seed)

    # Base compute per token per stage (ms)
    base_compute_ms = 25.0

    # Compression reduces network time but adds compute overhead
    compress_overhead = {"none": 0, "fp16": 2, "int8": 5, "sparse": 8}.get(compression, 0)
    compress_savings = {"none": 1.0, "fp16": 0.5, "int8": 0.25, "sparse": 0.3}.get(compression, 1.0)

    # Per-token timing
    compute_per_token = (base_compute_ms + compress_overhead) * stages
    network_per_token = latency_ms * (stages - 1) * compress_savings
    total_per_token = compute_per_token + network_per_token + random.gauss(0, 2)

    # First token is slower (prefill)
    ttft_ms = total_per_token * 3 + random.gauss(0, 5)

    # Total generation
    total_ms = ttft_ms + total_per_token * (tokens - 1)
    tok_per_sec = (tokens / total_ms) * 1000 if total_ms > 0 else 0

    return {
        "tok_per_sec": round(tok_per_sec, 2),
        "total_ms": round(total_ms, 1),
        "ttft_ms": round(ttft_ms, 1),
        "compute_ms": round(compute_per_token * tokens, 1),
        "network_ms": round(network_per_token * tokens, 1),
        "tokens": tokens,
    }


def main():
    parser = argparse.ArgumentParser(description="Simulated distributed inference")
    parser.add_argument("--stages", type=int, default=2)
    parser.add_argument("--latency-ms", type=float, default=10)
    parser.add_argument("--compression", type=str, default="none",
                        choices=["none", "fp16", "int8", "sparse"])
    parser.add_argument("--tokens", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print(f"Inference: stages={args.stages}, latency={args.latency_ms}ms, "
          f"compression={args.compression}, tokens={args.tokens}")

    time.sleep(0.05)
    metrics = simulate_inference(
        args.stages, args.latency_ms, args.compression, args.tokens, args.seed,
    )

    print(f"Tok/s: {metrics['tok_per_sec']}")
    print(f"Total: {metrics['total_ms']} ms")
    print(f"TTFT: {metrics['ttft_ms']} ms")
    print(f"Compute: {metrics['compute_ms']} ms")
    print(f"Network: {metrics['network_ms']} ms")
    print(f"Tokens: {metrics['tokens']}")


if __name__ == "__main__":
    main()
