import argparse
import json
from pathlib import Path
from .domain import ExperimentRequest, ExperimentConfig, parse_csv, sample_reservations, to_csv
from .simulation import run_experiment, deterministic_report


def main():
    parser = argparse.ArgumentParser(description="ParkingOps Lab reproducible experiments")
    parser.add_argument("--csv", type=Path)
    parser.add_argument('--replay',type=Path,help='Replay exported JSON input/config with installed solver')
    parser.add_argument("--slots", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--trials", type=int, default=500)
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument('--distribution',choices=['normal','uniform'],default='normal')
    parser.add_argument('--fixed-buffer',type=float,default=5)
    parser.add_argument('--risk-budget',type=float,default=.1)
    parser.add_argument('--time-limit',type=float,default=8)
    args = parser.parse_args()
    rows = parse_csv(args.csv.read_text(encoding="utf-8-sig")) if args.csv else sample_reservations(seed=args.seed)
    request=ExperimentRequest(reservations=rows, config=ExperimentConfig(slots=args.slots, seed=args.seed,
        trials=args.trials,deviation_distribution=args.distribution,fixed_buffer_minutes=args.fixed_buffer,
        risk_budget=args.risk_budget,time_limit=args.time_limit))
    if args.replay:
        saved=json.loads(args.replay.read_text(encoding='utf-8'))
        request=ExperimentRequest(reservations=saved['input_reservations'],config=saved['config'])
        rows=request.reservations
    result = run_experiment(request)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output/"report.md").write_text(deterministic_report(result), encoding="utf-8")
    (args.output/"input.csv").write_text(to_csv(rows), encoding="utf-8")
    print(deterministic_report(result))


if __name__ == "__main__":
    main()
