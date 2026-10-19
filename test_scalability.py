"""Tests for the scalability runs (N = 3, 5, 7, 10 ATMs, heavy and light load).

Run with:  python test_scalability.py
"""
from scalability import SIZES, requesters_for, run_scalability, theory_ricart_agrawala

assert SIZES == [3, 5, 7, 10]

# ---- the helpers ----
print("1. Helpers")
assert [theory_ricart_agrawala(n) for n in SIZES] == [4, 8, 12, 18]
assert requesters_for("heavy", 5) == [0, 1, 2, 3, 4]
assert requesters_for("light", 5) == [4]

# ---- run everything once ----
print("2. Running 16 simulations (about 5 seconds)...")
results = run_scalability()

for case in ("heavy", "light"):
    for n in SIZES:
        entries = n if case == "heavy" else 1
        ra = results[case]["ra"][n]
        ring = results[case]["ring"][n]

        # correctness: one ATM at a time, and the balance is right
        for name, r in (("RA", ra), ("ring", ring)):
            assert r["entries"] == entries, (case, n, name, r["entries"])
            assert r["max_active"] == 1, (case, n, name, "overlap!")
            assert r["balance"] == r["expected_balance"], (case, n, name, r["balance"])

        # Ricart-Agrawala: exactly 2(N-1) messages per entry, whatever the load
        assert ra["messages"] == entries * 2 * (n - 1), (case, n, ra["messages"])
        assert ra["per_entry"] == theory_ricart_agrawala(n)

        # Token Ring: the token makes N-1 passes to serve everyone (heavy) or the last ATM (light)
        assert ring["messages"] == n - 1, (case, n, ring["messages"])
        assert ring["per_entry"] == (n - 1) / entries

    print(f"   {case} load, N = {SIZES}: ok")

# ---- the shapes the chart should show ----
print("3. Trends")
# RA grows with N and does not care about the load
ra_heavy = [results["heavy"]["ra"][n]["per_entry"] for n in SIZES]
ra_light = [results["light"]["ra"][n]["per_entry"] for n in SIZES]
assert ra_heavy == ra_light == sorted(ra_heavy) and len(set(ra_heavy)) == len(SIZES)
# Ring under heavy load stays below 1 message per entry
assert all(results["heavy"]["ring"][n]["per_entry"] < 1 for n in SIZES)
# Ring under light load grows with N but is still cheaper than RA
ring_light = [results["light"]["ring"][n]["per_entry"] for n in SIZES]
assert ring_light == sorted(ring_light) and len(set(ring_light)) == len(SIZES)
assert all(results["light"]["ring"][n]["per_entry"] < results["light"]["ra"][n]["per_entry"]
           for n in SIZES)
print("   RA heavy/light:", ra_heavy)
print("   Ring heavy:", [round(results["heavy"]["ring"][n]["per_entry"], 2) for n in SIZES])
print("   Ring light:", ring_light)

print("\nAll scalability tests passed.")
