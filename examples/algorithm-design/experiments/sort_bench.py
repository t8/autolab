#!/usr/bin/env python3
"""Benchmark sorting algorithms with configurable parameters.

Tests variations of sorting algorithms and outputs performance metrics.

Usage:
    python sort_bench.py --algorithm quicksort --size 10000 --distribution random
"""

import argparse
import random
import time


def quicksort(arr: list, pivot_strategy: str = "median") -> list:
    if len(arr) <= 1:
        return arr
    if pivot_strategy == "first":
        pivot = arr[0]
    elif pivot_strategy == "last":
        pivot = arr[-1]
    elif pivot_strategy == "median":
        mid = len(arr) // 2
        candidates = sorted([(arr[0], 0), (arr[mid], mid), (arr[-1], -1)])
        pivot = candidates[1][0]
    else:
        pivot = arr[random.randint(0, len(arr) - 1)]

    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left, pivot_strategy) + middle + quicksort(right, pivot_strategy)


def mergesort(arr: list) -> list:
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = mergesort(arr[:mid])
    right = mergesort(arr[mid:])
    return merge(left, right)


def merge(left: list, right: list) -> list:
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result


def heapsort(arr: list) -> list:
    import heapq
    heapq.heapify(arr)
    return [heapq.heappop(arr) for _ in range(len(arr))]


def generate_data(size: int, distribution: str, seed: int) -> list:
    random.seed(seed)
    if distribution == "random":
        return [random.randint(0, size * 10) for _ in range(size)]
    elif distribution == "sorted":
        return list(range(size))
    elif distribution == "reversed":
        return list(range(size, 0, -1))
    elif distribution == "nearly_sorted":
        arr = list(range(size))
        swaps = size // 20
        for _ in range(swaps):
            i, j = random.randint(0, size - 1), random.randint(0, size - 1)
            arr[i], arr[j] = arr[j], arr[i]
        return arr
    elif distribution == "duplicates":
        return [random.randint(0, size // 10) for _ in range(size)]
    return [random.randint(0, size * 10) for _ in range(size)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--algorithm", default="quicksort",
                        choices=["quicksort", "mergesort", "heapsort"])
    parser.add_argument("--pivot", default="median",
                        choices=["first", "last", "median", "random"])
    parser.add_argument("--size", type=int, default=10000)
    parser.add_argument("--distribution", default="random",
                        choices=["random", "sorted", "reversed", "nearly_sorted", "duplicates"])
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    data = generate_data(args.size, args.distribution, args.seed)

    t0 = time.perf_counter()
    if args.algorithm == "quicksort":
        result = quicksort(list(data), args.pivot)
    elif args.algorithm == "mergesort":
        result = mergesort(list(data))
    elif args.algorithm == "heapsort":
        result = heapsort(list(data))
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Verify correctness
    correct = result == sorted(data)
    ops_per_sec = args.size / (elapsed_ms / 1000) if elapsed_ms > 0 else 0

    print(f"Algorithm: {args.algorithm}, Size: {args.size}, Distribution: {args.distribution}")
    print(f"Time: {elapsed_ms:.2f} ms")
    print(f"Ops/sec: {ops_per_sec:.0f}")
    print(f"Correct: {correct}")
    print(f"Elements: {args.size}")


if __name__ == "__main__":
    main()
