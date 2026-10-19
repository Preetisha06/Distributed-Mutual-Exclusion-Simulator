"""Tests for the ATM account, the local OS demo and the crash demo.

Run with:  python test_features.py
(test_mutex.py still tests Ricart-Agrawala ordering on its own.)
"""
from bank import START_BALANCE
from comparison import run_ricart_agrawala, run_token_ring
from crash import run_crash_ricart_agrawala, run_crash_token_ring
from local_os import run_local

# ---- 1. Both algorithms protect the bank account ----
print("1. Bank account under both algorithms")
for run in (run_ricart_agrawala, run_token_ring):
    r = run([0, 1, 2])
    assert r["max_active"] == 1, "two ATMs in the critical section at once!"
    assert r["balance"] == START_BALANCE - 300, f"wrong balance {r['balance']}"
    print("  ", run.__name__, "balance =", r["balance"], "order =", r["order"])

# ---- 2. Local OS: race without a lock, correct with a semaphore ----
print("2. Local OS version")
no_lock = run_local(use_lock=False)
assert no_lock["final"] != no_lock["expected"], "expected a race condition"
print("   no lock  :", no_lock["final"], "(expected", no_lock["expected"], ")")
with_lock = run_local(use_lock=True)
assert with_lock["final"] == with_lock["expected"], "semaphore should fix it"
print("   semaphore:", with_lock["final"], "(expected", with_lock["expected"], ")")

# ---- 3. Crash: try each ATM as the crashed one ----
print("3. Crash demo")
for crashed in range(3):
    others = [f"ATM {i + 1}" for i in range(3) if i != crashed]

    # Ricart-Agrawala: both survivors wait forever, nobody withdraws
    ra = run_crash_ricart_agrawala(crashed)
    assert ra["edited"] == [], "RA should be stuck"
    assert ra["starved"] == others
    assert ra["balance"] == START_BALANCE
    for n in ra["nodes"]:
        if not n["crashed"]:
            # always missing at least the dead node's reply (the later requester
            # also gets no reply from the earlier one, which defers it)
            assert n["replies"] < n["needed"] == 2

    # Token Ring: the token is lost at the crashed node
    ring = run_crash_token_ring(crashed)
    assert ring["token_lost"], "token should be lost"
    # ATMs before the crashed one in the ring get to withdraw first
    expected_edited = [f"ATM {i + 1}" for i in range(crashed)]
    assert ring["edited"] == expected_edited, (ring["edited"], expected_edited)
    print(f"   ATM {crashed + 1} crashed: RA stuck {ra['starved']}, "
          f"ring edited {ring['edited']} then lost token")

print("\nAll feature tests passed.")
