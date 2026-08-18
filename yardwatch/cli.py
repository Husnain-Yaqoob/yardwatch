"""Command-line entry point."""

from __future__ import annotations

import argparse
from datetime import timedelta

from . import handover, metrics, simulate, study


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="yardwatch",
        description="Bay allocation and shift handover for a capacity-constrained yard.",
    )
    parser.add_argument("--capacity", type=int, default=2, help="number of bays (default: 2)")
    parser.add_argument("--hours", type=int, default=8, help="shift length (default: 8)")
    parser.add_argument("--seed", type=int, default=42, help="simulation seed")
    parser.add_argument(
        "--target-wait",
        type=int,
        default=15,
        help="SLO target wait before admission, in minutes (default: 15)",
    )
    parser.add_argument("--out", help="write the handover report to this path")
    parser.add_argument(
        "--study",
        type=int,
        metavar="NIGHTS",
        help="run a capacity sweep across NIGHTS simulated shifts instead of "
        "printing one handover report",
    )
    args = parser.parse_args(argv)

    if args.study:
        results = study.sweep(
            capacities=[2, 3, 4, 5],
            nights=args.study,
            target_wait=timedelta(minutes=args.target_wait),
            hours=args.hours,
        )
        print(
            f"Capacity sweep over {args.study} simulated nights "
            f"(mean {results[0].mean_arrivals:.1f} arrivals/night, "
            f"target wait {args.target_wait} min)\n"
        )
        print(study.as_markdown_table(results))
        return 0

    shift, yard = simulate.run(hours=args.hours, capacity=args.capacity, seed=args.seed)
    computed = metrics.compute(
        yard.all_vehicles(), target_wait=timedelta(minutes=args.target_wait)
    )
    report = handover.generate(shift, yard, computed)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(report)
        print(f"Wrote handover report to {args.out}")
    else:
        print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
