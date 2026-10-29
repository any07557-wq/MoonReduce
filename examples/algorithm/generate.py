#!/usr/bin/env python3
"""Original, deterministic synthetic regression input; not third-party data."""
from pathlib import Path
import random
import sys


def main():
    rng = random.Random(1729)
    noise = [rng.choice([-200, -41, -5, 0]) for _ in range(93)]
    values = noise[:46] + [17, -3, 19] + noise[46:]
    with Path(sys.argv[1]).open("xb") as output:
        output.write(b"".join(f"{value}\n".encode("ascii") for value in values))


if __name__ == "__main__":
    main()
