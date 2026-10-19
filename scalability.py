"""Scalability: how do the two algorithms behave as the number of ATMs (N) grows?

For each N we run both algorithms in two cases:
  heavy load: all N ATMs withdraw at once
  light load: only ONE ATM withdraws (the last one, which is the worst case for
              the ring because the token starts at ATM 1 and must travel to it)

Nothing in the algorithms changes: comparison.py just builds N nodes instead of 3.

Run a demo with:  python scalability.py
"""
from concurrent.futures import ThreadPoolExecutor

from comparison import run_ricart_agrawala, run_token_ring

SIZES = [3, 5, 7, 10]


def theory_ricart_agrawala(n):
    return 2 * (n - 1)                       # (N-1) REQUESTs + (N-1) REPLYs per entry


def requesters_for(case, n):
    if case == "heavy":
        return list(range(n))                # everybody
    return [n - 1]                           # light: just the last ATM


def run_scalability(sizes=SIZES):
    """Returns results[case][algorithm][n] = summary dict (see comparison.summarize)."""
    jobs = []
    for case in ("heavy", "light"):
        for n in sizes:
            for algo, run in (("ra", run_ricart_agrawala), ("ring", run_token_ring)):
                jobs.append((case, algo, n, run))

    # The runs are independent, so do them side by side to save time.
    # (Message counts don't depend on timing, so this doesn't change the results.)
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(run, requesters_for(case, n), n) for case, algo, n, run in jobs]
        outcomes = [f.result() for f in futures]

    results = {"heavy": {"ra": {}, "ring": {}}, "light": {"ra": {}, "ring": {}}}
    for (case, algo, n, _), summary in zip(jobs, outcomes):
        results[case][algo][n] = summary
    return results


if __name__ == "__main__":
    results = run_scalability()
    for case in ("heavy", "light"):
        print(case, "load: messages per entry")
        print("   N   RA (theory)   Ring")
        for n in SIZES:
            ra = results[case]["ra"][n]["per_entry"]
            ring = results[case]["ring"][n]["per_entry"]
            print(f"  {n:>2}   {ra:5.2f} ({theory_ricart_agrawala(n)})   {ring:5.2f}")
