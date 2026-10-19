"""Token Ring mutual exclusion for the same 3 ATMs.

The ATMs sit in a ring: ATM 1 -> ATM 2 -> ATM 3 -> ATM 1.
A single TOKEN message travels around the ring. Only the ATM holding
the token may use the account. When done (or if the ATM doesn't want
to edit) they pass the token to the next ATM.

Run a demo with:  python token_ring.py
"""
import queue
import threading
import time

from node import LamportClock, SharedAccount, print_lock

TOKEN_HOLD_TIME = 0.05    # an idle ATM keeps the token briefly (avoids a busy spin)
EDIT_TIME = 0.3           # same "typing" time as the Ricart-Agrawala nodes


class MessageCounter:
    """Counts messages sent, so algorithms can be compared."""

    def __init__(self):
        self.lock = threading.Lock()
        self.count = 0
        self.count_at_last_edit_end = 0   # messages sent when the last edit finished

    def add(self):
        with self.lock:
            self.count += 1

    def edit_finished(self):
        with self.lock:
            self.count_at_last_edit_end = self.count


class TokenRingNode(threading.Thread):
    def __init__(self, node_id, name, account, counter=None, clock_start=0):
        super().__init__()
        self.node_id = node_id
        self.name = name
        self.inbox = queue.Queue()        # the token arrives here
        self.clock = LamportClock(clock_start)
        self.next_node = None             # next ATM in the ring
        self.account = account
        self.counter = counter or MessageCounter()
        self.running = True

        self.wants_edit = False           # set from outside to ask for an edit
        self.done = False                 # True once my edit has finished
        self.request_time = None          # wall-clock time I asked (for waiting stats)
        self.edit_start_time = None       # wall-clock time I started editing
        self.has_token = False

    # ---------- logging ----------
    def log(self, text):
        with print_lock:
            print(f"[{self.name:<5} t={self.clock.time:<2}] {text}")

    # ---------- messaging ----------
    def pass_token(self):
        # Sending is an event: tick the clock and stamp the token
        stamp = self.clock.tick()
        self.has_token = False
        self.next_node.inbox.put({"type": "TOKEN", "time": stamp})
        self.counter.add()
        self.log(f"TOKEN -> {self.next_node.name}")

    # ---------- critical section ----------
    def edit_account(self):
        self.edit_start_time = time.time()
        self.account.start_edit(self.name)
        self.log("WITHDRAW START")
        time.sleep(EDIT_TIME)
        self.account.end_edit()
        self.clock.tick()
        self.log("WITHDRAW END")
        self.counter.edit_finished()
        self.wants_edit = False
        self.done = True

    # ---------- main loop ----------
    def handle_token(self, message):
        self.clock.update(message["time"])
        self.has_token = True
        self.log(f"got TOKEN (sent at t={message['time']})")

        # Only the token holder may edit
        if self.wants_edit:
            self.edit_account()
        else:
            time.sleep(TOKEN_HOLD_TIME)   # nothing to do, pass it on
        self.pass_token()

    def run(self):
        while self.running:
            try:
                message = self.inbox.get(timeout=0.05)
            except queue.Empty:
                continue
            self.handle_token(message)

    def stop(self):
        self.running = False


def build_ring(account, counter, names=("ATM 1", "ATM 2", "ATM 3")):
    """Create the nodes and link them into a ring."""
    nodes = []
    for i in range(len(names)):
        nodes.append(TokenRingNode(i, names[i], account, counter))
    for i in range(len(nodes)):
        nodes[i].next_node = nodes[(i + 1) % len(nodes)]   # last wraps to first
    return nodes


def start_ring(nodes):
    """Start all threads and give the token to the first ATM."""
    for node in nodes:
        node.start()
    nodes[0].inbox.put({"type": "TOKEN", "time": 0})


if __name__ == "__main__":
    # Demo: all 3 ATMs want to edit
    account = SharedAccount()
    counter = MessageCounter()
    ring = build_ring(account, counter)
    for node in ring:
        node.wants_edit = True
    start_ring(ring)

    while not all(node.done for node in ring):
        time.sleep(0.05)
    for node in ring:
        node.stop()
    for node in ring:
        node.join()

    print("\nEdit order:", account.edit_order)
    print("Max editors at once:", account.max_active)
    print("Token messages used:", counter.count_at_last_edit_end)
