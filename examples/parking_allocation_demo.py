"""Illustrative parking allocation experiment, not a thesis replication.

Python standard library only. All requests and timing disturbances are synthetic.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import argparse
import json
import random


@dataclass(frozen=True)
class Request:
    key: str
    start: float
    end: float
    weight: int
    guard: float

    def __post_init__(self):
        if self.start >= self.end or self.guard < 0 or self.weight <= 0:
            raise ValueError("Require start < end, guard >= 0, and positive weight")


@dataclass(frozen=True)
class Assignment:
    request: Request
    bay: int


def overlap(a_start, a_end, b_start, b_end):
    """Half-open intervals: touching endpoints do not overlap."""
    return max(a_start, b_start) < min(a_end, b_end)


def solve(requests, bays=2, buffered=False):
    """Exact search for max accepted weight; intended for small examples only.

    A request's guard extends both ends of its planned interval in buffered mode.
    The optimization objective is identical between the two compared policies.
    """
    if bays < 1:
        raise ValueError("bays must be positive")
    if len({r.key for r in requests}) != len(requests):
        raise ValueError("request keys must be unique")
    ordered = sorted(requests, key=lambda r: (r.start, r.end, r.key))
    best_score = -1
    best = []
    allocations = [[] for _ in range(bays)]
    remaining = [0] * (len(ordered) + 1)
    for i in range(len(ordered) - 1, -1, -1):
        remaining[i] = remaining[i + 1] + ordered[i].weight

    def search(i, chosen, score):
        nonlocal best_score, best
        if score + remaining[i] <= best_score:
            return
        if i == len(ordered):
            best_score, best = score, list(chosen)
            return
        r = ordered[i]
        guard = r.guard if buffered else 0
        for bay in range(bays):
            if all(not overlap(r.start - guard, r.end + guard,
                               old.start - (old.guard if buffered else 0),
                               old.end + (old.guard if buffered else 0))
                   for old in allocations[bay]):
                allocations[bay].append(r)
                chosen.append(Assignment(r, bay))
                search(i + 1, chosen, score + r.weight)
                chosen.pop()
                allocations[bay].pop()
        search(i + 1, chosen, score)

    search(0, [], 0)
    return best


def conflicting_requests(assignments, realized):
    """Return both endpoints of each conflicting pair, deduplicated."""
    bad = set()
    for i, a in enumerate(assignments):
        for b in assignments[i + 1:]:
            if a.bay == b.bay and overlap(*realized[a.request.key], *realized[b.request.key]):
                bad.update((a.request.key, b.request.key))
    return bad


def experiment(requests, trials=1000, seed=20261019, bays=2):
    if trials < 1:
        raise ValueError("trials must be positive")
    policies = {"nominal": solve(requests, bays, False),
                "buffered": solve(requests, bays, True)}
    rng = random.Random(seed)
    counts = {name: 0 for name in policies}
    for _ in range(trials):
        # Common random numbers: both policies see the same realization per request.
        realized = {r.key: (r.start + rng.uniform(-7, 3),
                            r.end + rng.uniform(-3, 12)) for r in requests}
        for name, assignments in policies.items():
            counts[name] += len(conflicting_requests(assignments, realized))
    reports = {}
    for name, assignments in policies.items():
        n = len(assignments)
        reports[name] = {
            "accepted_requests": n,
            "total_requests": len(requests),
            "accepted_weight": sum(a.request.weight for a in assignments),
            "request_conflict_rate": counts[name] / (n * trials) if n else None,
            "assignments": [{"key": a.request.key, "bay": a.bay} for a in assignments],
        }
    return {"scope": "synthetic illustration; not a thesis replication",
            "seed": seed, "trials": trials, "bays": bays,
            "units": "minutes", "conflict_denominator": "accepted requests times trials",
            "requests": [asdict(r) for r in requests], "policies": reports}


def requests_for_demo():
    return [Request("A", 0, 30, 5, 6), Request("B", 0, 30, 2, 3),
            Request("C", 30, 60, 5, 6), Request("D", 38, 68, 2, 3),
            Request("E", 60, 90, 5, 6), Request("F", 76, 106, 2, 3),
            Request("G", 90, 120, 5, 6), Request("H", 114, 144, 2, 3)]


def chart(report):
    rows = []
    for i, (name, label) in enumerate((("nominal", "Nominal intervals"),
                                      ("buffered", "Guarded intervals"))):
        r = report["policies"][name]
        rate = r["request_conflict_rate"]
        y = 100 + i * 87
        width = 420 * (rate or 0)
        rows.append(f'<text x="28" y="{y}" fill="#c5d5e0" font-size="16">{label}</text>'
                    f'<rect x="220" y="{y-19}" width="420" height="27" rx="5" fill="#253849"/>'
                    f'<rect x="220" y="{y-19}" width="{width:.1f}" height="27" rx="5" fill="#80d8cc"/>'
                    f'<text x="657" y="{y+1}" fill="#f5f9fc" font-size="18">{rate:.1%}</text>'
                    f'<text x="220" y="{y+31}" fill="#9aafbd" font-size="12">'
                    f'{r["accepted_requests"]}/{r["total_requests"]} requests accepted; '
                    f'accepted weight {r["accepted_weight"]}</text>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="780" height="285" viewBox="0 0 780 285">'
            '<rect width="780" height="285" rx="14" fill="#102333"/>'
            '<g font-family="Arial,sans-serif"><text x="28" y="35" fill="#f5f9fc" font-size="19">'
            'Synthetic method demo / request conflict rate</text>'
            '<text x="28" y="57" fill="#9aafbd" font-size="12">'
            f'Seed {report["seed"]}; {report["trials"]} shared timing realizations; not thesis results</text>'
            + ''.join(rows) + '<text x="28" y="261" fill="#9aafbd" font-size="12">'
            'Compare risk together with admission and accepted weight. Lower conflict alone is not optimality.</text></g></svg>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261019)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--chart", type=Path, default=None)
    args = parser.parse_args()
    report = experiment(requests_for_demo(), args.trials, args.seed)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    if args.chart:
        args.chart.parent.mkdir(parents=True, exist_ok=True)
        args.chart.write_text(chart(report), encoding="utf-8")


if __name__ == "__main__":
    main()
