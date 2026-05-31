#!/usr/bin/env python3
"""MATH-500 benchmark v2: direct-only, 10 runs, 3 models in parallel.

Models: qwen2.5-14b-instruct (Q4_K_M/llama.cpp),
        qwen2.5-14b-instruct-awq (AWQ/vLLM),
        qwen2.5-14b-instruct-gptq-int4 (GPTQ-INT4/vLLM).

Grading via math_verify (sympy-based equivalence).
"""

import json, time, asyncio, aiohttp, sys
from pathlib import Path
from math_verify import parse, verify

API_BASE = "http://localhost:28080/v1/chat/completions"
API_KEY = "efef3129baacd506"
MODELS = [
    "qwen2.5-14b-instruct",
    "qwen2.5-14b-instruct-awq",
    "qwen2.5-14b-instruct-gptq-int4",
]
START_RUN = 3
N_RUNS = 7
MAX_CONCURRENT = 40
TIMEOUT = 300
TEMPERATURE = 0.7
TOP_P = 0.8
MAX_TOKENS = 2048
DATA_PATH = "/data/shared/modelscope/hub/datasets/AI-ModelScope/MATH-500/test.jsonl"
OUTPUT_DIR = Path("/home/xuan/Workspace/gpustack-dev/gpustack.custom/bench-math500/v2")

DIRECT_PROMPT = (
    "Solve the following math problem step by step. "
    "Put your final answer in \\boxed{{}}.\n\nProblem: {problem}"
)


def grade(response: str, gold: str) -> bool:
    if not response or response.startswith("ERROR:"):
        return False
    try:
        g = parse(gold if "\\boxed" in gold else f"\\boxed{{{gold}}}")
        p = parse(response)
        return bool(verify(g, p))
    except Exception:
        return False


async def call(session, model, content, sem):
    async with sem:
        for attempt in range(3):
            try:
                async with session.post(
                    API_BASE,
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": content}],
                        "max_tokens": MAX_TOKENS,
                        "temperature": TEMPERATURE,
                        "top_p": TOP_P,
                    },
                    headers={"Authorization": f"Bearer {API_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=TIMEOUT),
                ) as resp:
                    data = await resp.json()
                    return data["choices"][0]["message"].get("content", "") or ""
            except Exception as e:
                if attempt == 2:
                    return f"ERROR: {e}"
                await asyncio.sleep(3)


async def run_model(model, problems, run_i, sem):
    """Run one model for one pass, return (correct, total, errors, duration, results_list)."""
    t0 = time.time()
    async with aiohttp.ClientSession() as session:
        responses = await asyncio.gather(*[
            call(session, model, DIRECT_PROMPT.format(problem=p["problem"]), sem)
            for p in problems
        ])
    dur = time.time() - t0
    correct = sum(grade(r, p["answer"]) for r, p in zip(responses, problems))
    errors = sum(1 for r in responses if isinstance(r, str) and r.startswith("ERROR:"))
    results = [
        {"problem": p["problem"], "gold": p["answer"],
         "response": r, "correct": grade(r, p["answer"])}
        for p, r in zip(problems, responses)
    ]
    return correct, len(problems), errors, dur, results


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH) as f:
        problems = [json.loads(l) for l in f]
    print(f"Loaded {len(problems)} MATH-500 problems")
    print(f"Config: runs {START_RUN}-{N_RUNS}, temp={TEMPERATURE}, concurrency={MAX_CONCURRENT}/model")
    print(f"Models: {', '.join(MODELS)}\n")

    all_results = {m: [] for m in MODELS}

    for run_i in range(START_RUN, N_RUNS + 1):
        print(f"--- Run {run_i}/{N_RUNS} ---")
        sems = {m: asyncio.Semaphore(MAX_CONCURRENT) for m in MODELS}
        tasks = {
            m: asyncio.create_task(run_model(m, problems, run_i, sems[m]))
            for m in MODELS
        }
        for m in MODELS:
            correct, total, errors, dur, results = await tasks[m]
            acc = correct / total * 100
            all_results[m].append(acc)
            print(f"  {m:<36} {correct}/{total} = {acc:.1f}%  "
                  f"(err={errors}, {dur:.0f}s)")
            with open(OUTPUT_DIR / f"{m}_run{run_i}.json", "w") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

    # Load existing run 1-2 results
    for model in MODELS:
        for ri in range(1, START_RUN):
            p = OUTPUT_DIR / f"{model}_run{ri}.json"
            if p.exists():
                d = json.load(open(p))
                acc = sum(1 for r in d if r['correct']) / len(d) * 100
                all_results[model].append(acc)

    def stats(xs):
        m = sum(xs) / len(xs)
        return m, min(xs), max(xs)

    total_runs = N_RUNS
    print(f"\n{'='*72}")
    print(f"SUMMARY (runs 1-{total_runs})")
    print(f"{'='*72}")
    print(f"{'Model':<36}{'Runs':>6}{'Mean':>8}{'Min':>8}{'Max':>8}{'Std':>8}")
    print("-" * 72)
    for model in MODELS:
        xs = all_results[model]
        m, lo, hi = stats(xs)
        std = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5
        print(f"{model:<36}{len(xs):>6}{m:>7.1f}%{lo:>7.1f}%{hi:>7.1f}%{std:>7.2f}%")

    with open(OUTPUT_DIR / "summary.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved to {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
