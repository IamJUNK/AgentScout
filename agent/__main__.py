import argparse
from pathlib import Path
from agent.graph import run_research


def main():
    parser = argparse.ArgumentParser(description="AgentScout evidence-based research")
    parser.add_argument("input")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--model", default="")
    parser.add_argument("--search-count", type=int, default=5)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--material", type=Path, help="UTF-8 user-provided research material")
    parser.add_argument("--output", type=Path, default=Path("data/report.md"))
    args = parser.parse_args()
    result = run_research(args.input, supplied_text=args.material.read_text(encoding="utf-8") if args.material else "", mock=not args.real, model=args.model, search_count=args.search_count, force_refresh=args.refresh)
    print(f"Run ID: {result['run_id']}\nStatus: {result['status']}")
    for warning in result.get("warnings", []): print(warning)
    for error in result.get("errors", []): print(error)
    if result.get("report"):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result["report"], encoding="utf-8")
        print(f"Report: {args.output.resolve()}")
    raise SystemExit(0 if result["status"] in {"completed", "demo"} else (1 if result["status"] == "failed" else 2))


if __name__ == "__main__":
    main()
