from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import mcp_server


@dataclass
class BenchmarkResult:
    tool: str
    scenario: str
    raw_bytes: int
    context_bytes: int
    savings_percent: float
    duration_ms: float


def _token_estimate(byte_count: int) -> int:
    return max(0, int(round(byte_count / 4.0)))


def _result(tool: str, scenario: str, raw: str, output: str, duration_ms: float) -> BenchmarkResult:
    raw_bytes = len(raw.encode("utf-8"))
    context_bytes = len(output.encode("utf-8"))
    savings = 0.0
    if raw_bytes > 0:
        savings = (1.0 - (context_bytes / raw_bytes)) * 100.0
    return BenchmarkResult(
        tool=tool,
        scenario=scenario,
        raw_bytes=raw_bytes,
        context_bytes=context_bytes,
        savings_percent=round(savings, 2),
        duration_ms=round(duration_ms, 2),
    )


async def _run_single(query: str, top_k: int) -> tuple[BenchmarkResult, str]:
    start = time.perf_counter()
    output = await mcp_server.search_memory(query=query, top_k=top_k)
    duration_ms = (time.perf_counter() - start) * 1000.0
    result = _result(
        tool="search_memory",
        scenario=query,
        raw=query,
        output=output,
        duration_ms=duration_ms,
    )
    return result, output


async def _run_batch(queries: list[str], top_k: int) -> tuple[BenchmarkResult, str]:
    joined_raw = "\n".join(queries)
    start = time.perf_counter()
    output = await mcp_server.search_memory_batch(queries=queries, top_k=top_k)
    duration_ms = (time.perf_counter() - start) * 1000.0
    result = _result(
        tool="search_memory_batch",
        scenario=f"{len(queries)} queries",
        raw=joined_raw,
        output=output,
        duration_ms=duration_ms,
    )
    return result, output


async def run_benchmark(queries: list[str], top_k: int) -> dict:
    results: list[BenchmarkResult] = []

    for query in queries:
        result, _output = await _run_single(query, top_k=top_k)
        results.append(result)

    batch_result, _batch_output = await _run_batch(queries, top_k=top_k)
    results.append(batch_result)

    total_raw = sum(item.raw_bytes for item in results)
    total_context = sum(item.context_bytes for item in results)
    aggregate_savings = 0.0
    if total_raw > 0:
        aggregate_savings = (1.0 - (total_context / total_raw)) * 100.0

    return {
        "results": [asdict(item) for item in results],
        "aggregate": {
            "total_raw_bytes": total_raw,
            "total_context_bytes": total_context,
            "total_raw_tokens_est": _token_estimate(total_raw),
            "total_context_tokens_est": _token_estimate(total_context),
            "aggregate_savings_percent": round(aggregate_savings, 2),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="SecondCortex MCP benchmark runner")
    parser.add_argument(
        "--queries",
        nargs="+",
        default=["authentication flow", "incident timeline", "database retries"],
        help="Queries to benchmark",
    )
    parser.add_argument("--top-k", type=int, default=5, help="MCP top_k")
    parser.add_argument(
        "--output",
        default="secondcortex-backend/tests/mcp-benchmark-results.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    if not os.getenv("SECONDCORTEX_MCP_API_KEY"):
        raise SystemExit("Set SECONDCORTEX_MCP_API_KEY before running benchmark.")

    payload = asyncio.run(run_benchmark(args.queries, top_k=args.top_k))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote benchmark report to {output_path}")


if __name__ == "__main__":
    main()

