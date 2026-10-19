"""Crash recovery for both algorithms, added WITHOUT changing node.py or token_ring.py.

Ricart-Agrawala with recovery (RecoveringNode)
  - An ATM that has to wait for a peer now uses a timeout. If a peer has sent
    neither a REPLY nor an ACK within RA_TIMEOUT seconds, the ATM marks it as
    failed, removes it from the group and carries on without it.
  - Why the ACK? In Ricart-Agrawala a LIVE peer may stay silent for a long time on
    purpose (it is withdrawing, or it deferred our reply). So a peer that defers us
    now sends a quick ACK ("I got your request, I'll reply later"). Only a peer
    that is completely silent counts as crashed.

Token Ring with recovery (RecoveringRingNode)
  - Every ATM sends a small ALIVE heartbeat to all the others, so each ATM knows who
    is still alive. The ring skips ATMs that went silent.
  - If an ATM has not seen the token for TOKEN_TIMEOUT seconds, the lowest-id ATM
    that it believes is alive creates a new token. Because all ATMs use the same
    rule, only one of them regenerates it.

Limitation (both): a failure detector can only see silence, so a SLOW ATM can be
wrongly treated as crashed. Then the others carry on without it and it may enter
the critical section at the same time as someone else.

Run a demo with:  python recovery.py
"""
import threading
import time

from bank import BankAccount, START_BALANCE
from comparison import NAMES
from node import Node, RELEASED, WANTED
from token_ring import MessageCounter, TokenRingNode

RA_TIMEOUT = 1.0        # Ricart-Agrawala: give up on a silent peer after this long
HEARTBEAT = 0.2         # Token Ring: how often ATMs say "I'm alive"
DEAD_AFTER = 1.5        # Token Ring: silent for this long = crashed
TOKEN_TIMEOUT = 1.5     # Token Ring: no token seen for this long = token lost

WAVE2_AT = 3.5          # demo: second round of withdrawals starts at this time
TOTAL_TIME = 6.5        # demo: how long each run is watched


# ------------------------------------------------------------ Ricart-Agrawala
class RecoveringNode(Node):
    """Ricart-Agrawala node that gives up on peers that never answer."""

    def __init__(self, node_id, name, account, events, t0, timeout=RA_TIMEOUT,
                 clock_start=0):
        super().__init__(node_id, name, account, clock_start)
        self.events = events              # shared list: who detected which failure, when
        self.t0 = t0                      # start of the experiment (for timestamps)
        self.timeout = timeout
        self.failed = set()               # ids of peers I have given up on
        self.heard = set()                # peers that answered (REPLY or ACK) this request
        self.request_started = None

    # ----- sending a request: remember when, so we can time out -----
    def request_cs(self):
        self.heard = set()
        self.request_started = time.time()
        super().request_cs()

    # ----- receiving -----
    def handle(self, message):
        sender_id = message["from"]
        if sender_id in self.failed:
            return                        # ignore ATMs we already gave up on

        if message["type"] == "ACK":      # "I'm alive, I'll reply later"
            self.clock.update(message["time"])
            self.heard.add(sender_id)
            self.log(f"got ACK from {self.peers_by_id(sender_id).name} (it will reply later)")
            return

        if message["type"] == "REPLY":
            self.heard.add(sender_id)
        super().handle(message)           # the normal Ricart-Agrawala rules

        # If we made the sender wait, tell it we are alive (so it doesn't time out)
        if message["type"] == "REQUEST":
            sender = self.peers_by_id(sender_id)
            if sender in self.deferred:
                self.send(sender, "ACK", self.clock.tick())

    # ----- failure detection, in a helper thread -----
    def run(self):
        threading.Thread(target=self.watch_for_failures, daemon=True).start()
        super().run()                     # the normal node loop

    def watch_for_failures(self):
        while self.running:
            time.sleep(0.1)
            if self.state != WANTED:
                continue                  # only matters while we are waiting for replies
            if time.time() - self.request_started < self.timeout:
                continue
            # Peers that answered neither with a REPLY nor an ACK are silent: give up on them
            for peer in [p for p in self.peers if p.node_id not in self.heard]:
                self.give_up_on(peer)

    def give_up_on(self, peer):
        self.failed.add(peer.node_id)
        self.peers = [p for p in self.peers if p is not peer]       # remove from the group
        self.deferred = [p for p in self.deferred if p is not peer]
        at = round(time.time() - self.t0, 2)
        self.events.append({"kind": "detected", "by": self.name, "failed": peer.name, "at": at})
        self.log(f"FAILURE DETECTED at +{at} s: no REPLY or ACK from {peer.name} "
                 f"within {self.timeout} s, removing it from the group")


# ------------------------------------------------------------ Token Ring
class RingContext:
    """Shared bookkeeping for one Token Ring run."""

    def __init__(self, t0):
        self.t0 = t0
        self.lock = threading.Lock()
        self.events = []                  # failures detected, tokens regenerated
        self.tokens_created = 0           # how many NEW tokens were made


class RecoveringRingNode(TokenRingNode):
    """Token Ring node with heartbeats, ring repair and token regeneration."""

    def __init__(self, node_id, name, account, counter, context):
        super().__init__(node_id, name, account, counter)
        self.context = context
        self.everyone = []                # all ring nodes, in ring order
        self.dead = set()                 # ids I believe have crashed
        self.last_heard = {}              # id -> last time I got an ALIVE from it
        self.last_token_seen = time.time()

    # ----- receiving: heartbeats or the token -----
    def handle_token(self, message):
        if message["type"] == "ALIVE":
            self.last_heard[message["from"]] = time.time()
            return
        self.last_token_seen = time.time()
        super().handle_token(message)     # the normal Token Ring rules

    # ----- helper thread: heartbeats, failure detection, token regeneration -----
    def run(self):
        now = time.time()
        for node in self.everyone:
            self.last_heard[node.node_id] = now
        threading.Thread(target=self.background, daemon=True).start()
        super().run()                     # the normal node loop

    def background(self):
        while self.running:
            time.sleep(HEARTBEAT)
            now = time.time()
            for peer in self.everyone:                    # 1. say "I'm alive"
                if peer is not self:
                    peer.inbox.put({"type": "ALIVE", "from": self.node_id})

            for peer in self.everyone:                    # 2. who has gone silent?
                if (peer is not self and peer.node_id not in self.dead
                        and now - self.last_heard[peer.node_id] > DEAD_AFTER):
                    self.mark_dead(peer, now)

            alive_ids = [n.node_id for n in self.everyone if n.node_id not in self.dead]
            if (self.node_id == min(alive_ids)            # 3. lowest alive ATM only
                    and now - self.last_token_seen > TOKEN_TIMEOUT):
                self.regenerate_token(now)

    def mark_dead(self, peer, now):
        self.dead.add(peer.node_id)
        # repair the ring: the next node is the next ALIVE one after me
        count = len(self.everyone)
        for step in range(1, count):
            candidate = self.everyone[(self.node_id + step) % count]
            if candidate.node_id not in self.dead:
                self.next_node = candidate
                break
        at = round(now - self.context.t0, 2)
        with self.context.lock:
            self.context.events.append({"kind": "detected", "by": self.name,
                                       "failed": peer.name, "at": at})
        self.log(f"FAILURE DETECTED at +{at} s: no heartbeat from {peer.name}, "
                 f"the ring now skips it (next ATM is {self.next_node.name})")

    def regenerate_token(self, now):
        self.last_token_seen = now        # don't regenerate again straight away
        at = round(now - self.context.t0, 2)
        with self.context.lock:
            self.context.tokens_created += 1
            self.context.events.append({"kind": "regenerated", "by": self.name, "at": at})
        self.log(f"TOKEN REGENERATED at +{at} s by {self.name} "
                 f"(lowest-id ATM that is alive)")
        self.inbox.put({"type": "TOKEN", "time": self.clock.time})


# ------------------------------------------------------------ the demo scenario
def make_logger(node, lines, t0):
    def log(text):
        lines.append(f"+{time.time() - t0:4.1f}s [{node.name} t={node.clock.time}] {text}")
    node.log = log


def request_again(node):
    """Second round of withdrawals: only for ATMs that finished the first one."""
    if node.done:
        node.done = False
        node.wants_edit = True


def summarize(account, nodes, crashed, lines, events, extra):
    survivors = [n for n in nodes if n.node_id != crashed]
    counts = {n.name: account.edit_order.count(n.name) for n in nodes}
    completed = len(account.edit_order)
    result = {
        "nodes": [{"name": n.name, "crashed": n.node_id == crashed,
                   "withdrawals": counts[n.name]} for n in nodes],
        "completed": completed,
        "wanted": 2 * len(survivors),     # two rounds of withdrawals per surviving ATM
        "edit_order": list(account.edit_order),
        "balance": account.balance,
        "expected_balance": START_BALANCE - completed * account.amount,
        "max_active": account.max_active,
        "events": list(events),
        "log": lines,
    }
    result.update(extra)
    return result


def run_ra_scenario(crashed, recover):
    """One ATM crashed from the start. Survivors withdraw at +0 s and again at WAVE2_AT."""
    t0 = time.time()
    account = BankAccount()
    events = []
    lines = [f"+ 0.0s *** {NAMES[crashed]} CRASHED (it will never reply) ***"]
    if recover:
        nodes = [RecoveringNode(i, NAMES[i], account, events, t0) for i in range(3)]
    else:
        nodes = [Node(i, NAMES[i], account) for i in range(3)]
    for node in nodes:
        node.daemon = True
        make_logger(node, lines, t0)
        node.peers = [other for other in nodes if other is not node]

    survivors = [n for n in nodes if n.node_id != crashed]
    for node in survivors:
        node.wants_edit = True
    for node in survivors:
        node.start()                      # the crashed ATM's thread is never started

    time.sleep(WAVE2_AT)
    for node in survivors:
        request_again(node)
    time.sleep(TOTAL_TIME - WAVE2_AT)

    waiting = [n.name for n in survivors if n.wants_edit]
    result = summarize(account, nodes, crashed, lines, events,
                       {"kind": "ra", "recovered": recover, "stuck": waiting})
    for node in survivors:
        node.stop()
    return result


def run_ring_scenario(crashed, recover):
    t0 = time.time()
    account = BankAccount()
    counter = MessageCounter()
    context = RingContext(t0)
    lines = [f"+ 0.0s *** {NAMES[crashed]} CRASHED (it will never pass the token on) ***"]
    if recover:
        nodes = [RecoveringRingNode(i, NAMES[i], account, counter, context) for i in range(3)]
    else:
        nodes = [TokenRingNode(i, NAMES[i], account, counter) for i in range(3)]
    for i, node in enumerate(nodes):
        node.daemon = True
        node.next_node = nodes[(i + 1) % 3]
        make_logger(node, lines, t0)
        if recover:
            node.everyone = nodes

    survivors = [n for n in nodes if n.node_id != crashed]
    for node in survivors:
        node.wants_edit = True
    for node in survivors:
        node.start()
    nodes[0].inbox.put({"type": "TOKEN", "time": 0})     # token starts at ATM 1

    time.sleep(WAVE2_AT)
    for node in survivors:
        request_again(node)
    time.sleep(TOTAL_TIME - WAVE2_AT)

    # Plain ring: the token is lost if it is sitting unread in the dead ATM's inbox
    token_lost = (not recover) and not nodes[crashed].inbox.empty()
    starved = [n.name for n in survivors if n.wants_edit]
    result = summarize(account, nodes, crashed, lines, context.events,
                       {"kind": "ring", "recovered": recover, "token_lost": token_lost,
                        "starved": starved, "tokens_created": context.tokens_created})
    for node in survivors:
        node.stop()
    return result


if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {(kind, rec): pool.submit(run, 2, rec)
                for kind, run in (("RA", run_ra_scenario), ("ring", run_ring_scenario))
                for rec in (False, True)}
    for (kind, rec), future in jobs.items():
        r = future.result()
        print(f"{kind:>4} recovery={rec!s:<5} withdrawals {r['completed']}/{r['wanted']} "
              f"balance {r['balance']} events {r['events']}")
