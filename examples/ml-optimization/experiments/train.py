#!/usr/bin/env python3
"""Toy training script that simulates ML training with configurable hyperparameters.

Outputs metrics in a format Autolab can parse. This simulates the training loop
behavior so you can test Autolab's campaign system without a real model.

Usage:
    python train.py --lr 0.01 --batch-size 32 --epochs 10 --optimizer adam
"""

import argparse
import math
import random
import time


def simulate_training(lr: float, batch_size: int, epochs: int, optimizer: str, seed: int) -> dict:
    """Simulate training and return metrics.

    The 'optimal' config is lr=0.001, batch_size=64, optimizer=adam.
    Deviations from this increase loss and decrease accuracy.
    """
    random.seed(seed)

    # Simulate: optimal lr is ~0.001, optimal batch_size is ~64
    lr_penalty = abs(math.log10(lr) - math.log10(0.001)) * 0.3
    bs_penalty = abs(math.log2(batch_size) - math.log2(64)) * 0.05
    opt_penalty = 0.0 if optimizer == "adam" else 0.15

    base_loss = 0.1 + lr_penalty + bs_penalty + opt_penalty
    noise = random.gauss(0, 0.02)
    final_loss = max(0.01, base_loss + noise)

    accuracy = max(0.0, min(1.0, 1.0 - final_loss + random.gauss(0, 0.01)))

    # Throughput scales with batch size, penalized by large lr (instability)
    throughput = batch_size * 10 * (1.0 - lr_penalty * 0.5) + random.gauss(0, 5)
    throughput = max(10, throughput)

    train_time = epochs * (100 / throughput) + random.gauss(0, 0.1)

    return {
        "loss": round(final_loss, 4),
        "accuracy": round(accuracy, 4),
        "throughput": round(throughput, 1),
        "train_time_s": round(train_time, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Simulated ML training")
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--optimizer", type=str, default="adam", choices=["adam", "sgd", "rmsprop"])
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print(f"Training with lr={args.lr}, batch_size={args.batch_size}, "
          f"epochs={args.epochs}, optimizer={args.optimizer}")

    # Simulate some training time
    time.sleep(0.1)

    metrics = simulate_training(args.lr, args.batch_size, args.epochs, args.optimizer, args.seed)

    print(f"Loss: {metrics['loss']}")
    print(f"Accuracy: {metrics['accuracy']}")
    print(f"Throughput: {metrics['throughput']} samples/sec")
    print(f"Train time: {metrics['train_time_s']}s")


if __name__ == "__main__":
    main()
