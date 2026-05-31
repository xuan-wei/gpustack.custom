#!/usr/bin/env python3
"""MATH-500 benchmark: direct answer vs 1-round reflexion, 5 runs each.

Compares qwen2.5-14b-instruct-awq (vLLM, 4-bit AWQ) vs
qwen2.5-14b-instruct (llama.cpp, Q-quant) accuracy.

Grading via math_verify (sympy-based equivalence, robust to formatting).
"""

import json, time, asyncio, aiohttp, sys
from pathlib import Path
from math_verify import parse, verify

API_BASE = "http://localhost:28080/v1/chat/completions"
API_KEY = "efef3129baacd506"
MODELS = ["qwen2.5-14b-instruct-awq", "qwen2.5-14b-instruct"]
N_RUNS = 5
MAX_CONCURRENT = 8          # gentle: llama.cpp has --parallel 7
TIMEOUT = 180
TEMPERATURE = 0.7           # >0 so the 5 runs show real variance
TOP_P = 0.8
MAX_TOKENS = 2048
DATA_PATH = "/data/shared/modelscope/hub/datasets/AI-ModelScope/MATH-500/test.jsonl"
OUTPUT_DIR = Path("/home/xuan/Workspace/gpustack-dev/gpustack.custom/bench-math500")

DIRECT_PROMPT = (
    "Solve the following math problem step by step. "
    "Put your final answer in \\boxed{{}}.\n\nProblem: {problem}"
)
REFLEXION_PROMPT = (
    "You are checking your own solution to a math problem.\n\n"
    "Problem: {problem}\n\n"
    "Your previous solution:\n{prev}\n\n"
    "Carefully re-examine each step. If you find an error, fix it. "
    "Then give your final answer in \\boxed{{}}."
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
        for attempt in range(2):
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
                if attempt == 1:
                    return f"ERROR: {e}"
                await asyncio.sleep(2)


async def one_run(model, problems, sem):
    """Return (direct_responses, reflexion_responses) for all problems."""
    async with aiohttp.ClientSession() as session:
        # Direct pass
        direct = await asyncio.gather(*[
            call(session, model, DIRECT_PROMPT.format(problem=p["problem"]), sem)
            for p in problems
        ])
        # Reflexion pass (builds on direct)
        reflex = await asyncio.gather(*[
            call(session, model, REFLEXION_PROMPT.format(problem=p["problem"], prev=d), sem)
            for p, d in zip(problems, direct)
        ])
    return direct, reflex


def score(responses, problems):
    correct = sum(grade(r, p["answer"]) for r, p in zip(responses, problems))
    errors = sum(1 for r in responses if r.startswith("ERROR:"))
    return correct, len(problems), errors


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH) as f:
        problems = [json.loads(l) for l in f]
    print(f"Loaded {len(problems)} MATH-500 problems")
    print(f"Config: {N_RUNS} runs, temp={TEMPERATURE}, concurrency={MAX_CONCURRENT}\n")

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    results = {m: {"direct": [], "reflexion": []} for m in MODELS}

    for model in MODELS:
        print(f"{'='*64}\n{model}\n{'='*64}")
        for run_i in range(1, N_RUNS + 1):
            t0 = time.time()
            direct, reflex = await one_run(model, problems, sem)
            dc, dt, de = score(direct, problems)
            rc, rt, re_ = score(reflex, problems)
            results[model]["direct"].append(dc / dt * 100)
            results[model]["reflexion"].append(rc / rt * 100)
            dur = time.time() - t0
            print(f"  run {run_i}: direct {dc}/{dt}={dc/dt*100:.1f}%  "
                  f"reflexion {rc}/{rt}={rc/rt*100:.1f}%  "
                  f"(err d={de} r={re_}, {dur:.0f}s)")
            # dump raw
            with open(OUTPUT_DIR / f"{model}_run{run_i}.json", "w") as f:
                json.dump([
                    {"problem": p["problem"], "gold": p["answer"],
                     "direct": d, "reflexion": rf,
                     "direct_ok": grade(d, p["answer"]),
                     "reflexion_ok": grade(rf, p["answer"])}
                    for p, d, rf in zip(problems, direct, reflex)
                ], f, ensure_ascii=False, indent=2)

    # Summary
    def stats(xs):
        m = sum(xs) / len(xs)
        return m, min(xs), max(xs)

    print(f"\n{'='*64}\nSUMMARY (mean over {N_RUNS} runs)\n{'='*64}")
    print(f"{'Model':<28}{'Mode':<12}{'Mean':>8}{'Min':>8}{'Max':>8}")
    print("-" * 64)
    for model in MODELS:
        for mode in ["direct", "reflexion"]:
            m, lo, hi = stats(results[model][mode])
            print(f"{model:<28}{mode:<12}{m:>7.1f}%{lo:>7.1f}%{hi:>7.1f}%")

    with open(OUTPUT_DIR / "summary.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
