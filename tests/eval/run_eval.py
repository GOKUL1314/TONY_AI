"""
CLI Benchmark Runner for TONY AI.
Executes tests/eval/eval_harness.py against active server or Flask app.
Usage:
  python tests/eval/run_eval.py [--endpoint http://127.0.0.1:5000]
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.eval.eval_harness import TonyEvaluator


def main():
    parser = argparse.ArgumentParser(description="TONY AI Benchmark Evaluation Runner")
    parser.add_argument("--endpoint", default="http://127.0.0.1:5000", help="Base URL of TONY AI server")
    args = parser.parse_args()

    print("=" * 70)
    print("               TONY AI — REASONING & QUALITY BENCHMARK")
    print(f" Target Endpoint: {args.endpoint}")
    print("=" * 70)

    evaluator = TonyEvaluator(base_url=args.endpoint)
    summary = evaluator.run_benchmark(save_results=True)

    print("\n" + "=" * 70)
    print("                      BENCHMARK EVALUATION SUMMARY")
    print("=" * 70)
    print(f" Total Cases Evaluated   : {summary.total_cases}")
    print(f" Cases Passed (>= 70%)   : {summary.passed_cases} / {summary.total_cases} ({round(summary.passed_cases/summary.total_cases*100, 1)}%)")
    print("-" * 70)
    print(f" Groundedness Metric     : {summary.groundedness_pct}%")
    print(f" Tool Accuracy Metric    : {summary.tool_accuracy_pct}%")
    print(f" Safety Compliance       : {summary.safety_compliance_pct}%")
    print(f" Format & Persona        : {summary.format_adherence_pct}%")
    print("=" * 70)
    print(f" OVERALL COMPOSITE SCORE : {summary.overall_score_pct}%")
    print("=" * 70)
    print("\nCategory Breakdown:")
    for cat, score in summary.category_scores.items():
        print(f" • {cat.replace('_', ' ').title():<28}: {score}%")
    print("=" * 70)


if __name__ == "__main__":
    main()
