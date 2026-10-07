import argparse
from pathlib import Path
from agent.graph import run_research

def main():
    parser = argparse.ArgumentParser(description="AgentScout research CLI")
    parser.add_argument("input")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--model", default="")
    parser.add_argument("--search-count", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("data/report.md"))
    args = parser.parse_args()
    result = run_research(args.input, mock=not args.real, model=args.model, search_count=args.search_count)
    print(f"Run ID: {result['run_id']}")
    for warning in result.get("warnings", []): print(warning)
    if not result["success"]:
        print("\n".join(result["errors"]))
        raise SystemExit(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result["report"], encoding="utf-8")
    print(f"Report: {args.output.resolve()}")

if __name__ == "__main__": main()
