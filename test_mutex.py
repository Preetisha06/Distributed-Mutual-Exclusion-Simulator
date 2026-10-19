"""Tests: all 3 ATMs request to edit at the same time.

Checks:
  1. Only one ATM edits at a time (mutual exclusion).
  2. The smallest request timestamp edits first.

Run with:  python test_mutex.py
"""
import time
from node import Node, SharedAccount

NAMES = ["ATM 1", "ATM 2", "ATM 3"]


def run_scenario(title, clock_starts):
    """All three ATMs request at once. Returns (account, nodes)."""
    print(f"\n===== {title} =====")
    account = SharedAccount()

    # Create the nodes, each with its own starting clock value
    nodes = []
    for i in range(3):
        nodes.append(Node(i, NAMES[i], account, clock_starts[i]))

    # Everyone knows everyone else
    for node in nodes:
        for other in nodes:
            if other is not node:
                node.peers.append(other)

    # Mark everyone as wanting to edit BEFORE starting any thread,
    # so all three send their REQUESTs right away, "at the same time"
    for node in nodes:
        node.wants_edit = True
    for node in nodes:
        node.start()

    # Wait until everyone has finished editing (give up after 10 seconds)
    deadline = time.time() + 10
    while time.time() < deadline:
        all_done = True
        for node in nodes:
            if not node.done:
                all_done = False
        if all_done:
            break
        time.sleep(0.05)

    for node in nodes:
        node.stop()
    for node in nodes:
        node.join()

    for node in nodes:
        assert node.done, f"{node.name} never got to edit (deadlock?)"
    return account, nodes


def check(account, nodes):
    # 1. Mutual exclusion: never more than one editor at once
    assert account.max_active == 1, f"overlap! {account.max_active} editing at once"

    # 2. Order: sorted by (request timestamp, node id) -> smallest goes first
    expected = sorted(nodes, key=lambda n: (n.request_ts, n.node_id))
    expected_names = [n.name for n in expected]
    assert account.edit_order == expected_names, (
        f"wrong order: got {account.edit_order}, expected {expected_names}")

    print("request timestamps:", {n.name: n.request_ts for n in nodes})
    print("edit order:", account.edit_order)
    print("max editors at once:", account.max_active)
    print("PASS")


# Scenario 1: all clocks equal -> all requests get the SAME timestamp (1).
# The tie is broken by node id, so the order must be ATM 1, ATM 2, ATM 3.
account, nodes = run_scenario("Scenario 1: identical timestamps (tie)", [0, 0, 0])
check(account, nodes)
assert account.edit_order == ["ATM 1", "ATM 2", "ATM 3"]

# Scenario 2: different clocks -> different timestamps.
# ATM 3(0)->ts 1, ATM 2(3)->ts 4, ATM 1(5)->ts 6, so ATM 3 must go first.
account, nodes = run_scenario("Scenario 2: different timestamps", [5, 3, 0])
check(account, nodes)
assert account.edit_order == ["ATM 3", "ATM 2", "ATM 1"]

print("\nAll tests passed.")
