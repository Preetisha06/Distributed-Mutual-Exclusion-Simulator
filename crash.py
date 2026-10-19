"""Crash demo: what happens when one ATM (node) dies?

We simulate the crash by never starting that node's thread, so it never
answers any message. The other ATMs all try to withdraw money.

  - Ricart-Agrawala needs a REPLY from EVERY other node -> it waits forever.
  - Token Ring passes the token along the ring -> the token is handed to
    the dead node and is lost.

Run a demo with:  python crash.py
"""
import time

from bank import BankAccount
from comparison import CountingNode, NAMES
from token_ring import MessageCounter, build_ring


def make_logger(node, lines):
    # Replace the node's log() so lines go into a list instead of printing
    def log(text):
        lines.append(f"[{node.name} t={node.clock.time}] {text}")
    node.log = log


def stop_all(nodes):
    for node in nodes:
        node.stop()
    for node in nodes:
        if node.is_alive():                 # the crashed node was never started
            node.join(timeout=1)


def run_crash_ricart_agrawala(crashed, observe=2.0):
    """crashed = node id (0, 1 or 2). Everyone else asks to withdraw."""
    account = BankAccount()
    counter = MessageCounter()
    nodes = [CountingNode(i, NAMES[i], account, counter) for i in range(3)]
    lines = [f"*** {NAMES[crashed]} CRASHED (it will never reply) ***"]
    for node in nodes:
        node.daemon = True
        make_logger(node, lines)
        for other in nodes:
            if other is not node:
                node.peers.append(other)

    requesters = [i for i in range(3) if i != crashed]
    for i in requesters:
        nodes[i].wants_edit = True
    for i in range(3):
        if i != crashed:
            nodes[i].start()

    time.sleep(observe)                     # give it plenty of time to finish

    info = []
    for i in range(3):
        info.append({"name": NAMES[i], "crashed": i == crashed,
                     "state": nodes[i].state, "replies": nodes[i].replies,
                     "needed": len(nodes[i].peers), "done": nodes[i].done})
    stop_all(nodes)

    starved = [NAMES[i] for i in requesters if not nodes[i].done]
    return {"nodes": info, "edited": list(account.edit_order), "starved": starved,
            "balance": account.balance, "log": lines}


def run_crash_token_ring(crashed, observe=2.0):
    account = BankAccount()
    counter = MessageCounter()
    nodes = build_ring(account, counter, NAMES)
    lines = [f"*** {NAMES[crashed]} CRASHED (it will never pass the token on) ***"]
    for node in nodes:
        node.daemon = True
        make_logger(node, lines)

    requesters = [i for i in range(3) if i != crashed]
    for i in requesters:
        nodes[i].wants_edit = True
    for i in range(3):
        if i != crashed:
            nodes[i].start()
    nodes[0].inbox.put({"type": "TOKEN", "time": 0})    # token starts at ATM 1

    time.sleep(observe)

    # If the token is sitting unread in the dead node's inbox, it is lost
    token_lost = not nodes[crashed].inbox.empty()
    info = []
    for i in range(3):
        info.append({"name": NAMES[i], "crashed": i == crashed,
                     "done": nodes[i].done, "wants_edit": nodes[i].wants_edit})
    stop_all(nodes)

    starved = [NAMES[i] for i in requesters if not nodes[i].done]
    return {"nodes": info, "edited": list(account.edit_order), "starved": starved,
            "token_lost": token_lost, "lost_at": NAMES[crashed],
            "balance": account.balance, "log": lines}


if __name__ == "__main__":
    for crashed in range(3):
        ra = run_crash_ricart_agrawala(crashed)
        ring = run_crash_token_ring(crashed)
        print(f"{NAMES[crashed]} crashed")
        print("  RA  : edited", ra["edited"], "stuck:", ra["starved"])
        print("  Ring: edited", ring["edited"], "starved:", ring["starved"],
              "token lost:", ring["token_lost"])
