"""Run Ricart-Agrawala and Token Ring on the same requests and measure them.

Neither algorithm file is changed: we subclass the RA node just to count
its messages and record timings.
"""
import time

from bank import BankAccount, START_BALANCE
from node import Node
from token_ring import MessageCounter, build_ring, start_ring

NAMES = ["ATM 1", "ATM 2", "ATM 3"]


class CountingNode(Node):
    """Ricart-Agrawala node that counts messages and times its waiting."""

    def __init__(self, node_id, name, account, counter):
        super().__init__(node_id, name, account)
        self.counter = counter
        self.request_time = None
        self.edit_start_time = None

    def log(self, text):
        pass                                  # keep the comparison quiet

    def send(self, peer, msg_type, stamp):
        self.counter.add()                    # every REQUEST / REPLY counts
        super().send(peer, msg_type, stamp)

    def edit_account(self):
        self.edit_start_time = time.time()
        super().edit_account()


def wait_until_done(nodes, timeout=20):
    # Poll until every node has finished editing (or give up)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if all(node.done for node in nodes):
            return True
        time.sleep(0.05)
    return False


def summarize(requesters, account, counter, nodes, messages):
    # Average time from "asked" to "started editing"
    waits = []
    for i in requesters:
        waits.append(nodes[i].edit_start_time - nodes[i].request_time)
    entries = len(requesters)
    return {
        "entries": entries,
        "messages": messages,
        "per_entry": messages / entries,
        "avg_wait": sum(waits) / len(waits),
        "order": list(account.edit_order),
        "max_active": account.max_active,
        "balance": account.balance,
        "expected_balance": START_BALANCE - entries * account.amount,
    }


def atm_names(n):
    return [f"ATM {i + 1}" for i in range(n)]


def run_ricart_agrawala(requesters, n=3):
    """requesters = ids (0..n-1) of the ATMs that all ask at the same time."""
    account = BankAccount()
    counter = MessageCounter()
    nodes = [CountingNode(i, name, account, counter) for i, name in enumerate(atm_names(n))]
    for node in nodes:
        node.daemon = True
        for other in nodes:
            if other is not node:
                node.peers.append(other)

    # Flag the requests first so they all go out immediately
    now = time.time()
    for i in requesters:
        nodes[i].wants_edit = True
        nodes[i].request_time = now
    for node in nodes:
        node.start()

    wait_until_done([nodes[i] for i in requesters])
    for node in nodes:
        node.stop()
    for node in nodes:
        node.join()
    return summarize(requesters, account, counter, nodes, counter.count)


def run_token_ring(requesters, n=3):
    account = BankAccount()
    counter = MessageCounter()
    nodes = build_ring(account, counter, atm_names(n))
    now = time.time()
    for i in requesters:
        nodes[i].wants_edit = True
        nodes[i].request_time = now
    for node in nodes:
        node.log = lambda text: None          # keep the comparison quiet
        node.daemon = True
    start_ring(nodes)

    wait_until_done([nodes[i] for i in requesters])
    for node in nodes:
        node.stop()
    for node in nodes:
        node.join()
    # Only count token passes up to the last edit (the ring would keep going forever)
    return summarize(requesters, account, counter, nodes,
                     counter.count_at_last_edit_end)


if __name__ == "__main__":
    for requesters in ([0, 1, 2], [2], [0, 2]):
        print("requests from", [NAMES[i] for i in requesters])
        print("  RA  :", run_ricart_agrawala(requesters))
        print("  Ring:", run_token_ring(requesters))
