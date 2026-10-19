"""A node = one ATM using a shared account, using Ricart-Agrawala.

Each node runs as a thread, has an inbox queue and a Lamport clock.
Critical section = withdrawing from (editing) the shared account.
"""
import queue
import threading
import time

# Node states in Ricart-Agrawala
RELEASED = "RELEASED"   # not interested in editing
WANTED = "WANTED"       # asked everyone for permission, waiting for replies
HELD = "HELD"           # currently editing

print_lock = threading.Lock()   # so log lines from different threads don't mix


class LamportClock:
    """Logical clock: gives every event a number that respects causality."""

    def __init__(self, start=0):
        self.time = start

    def tick(self):
        # Local event or sending a message: move the clock forward by 1
        self.time += 1
        return self.time

    def update(self, received_time):
        # Receiving a message: jump past the sender's time, then count the event
        self.time = max(self.time, received_time) + 1
        return self.time


class SharedAccount:
    """The shared resource. Records who edited, and checks for overlaps."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active_editors = 0     # how many ATMs are editing right now
        self.max_active = 0         # highest number ever editing at once
        self.edit_order = []        # names, in the order editing started

    def start_edit(self, name):
        with self.lock:
            self.active_editors += 1
            self.max_active = max(self.max_active, self.active_editors)
            self.edit_order.append(name)

    def end_edit(self):
        with self.lock:
            self.active_editors -= 1


class Node(threading.Thread):
    def __init__(self, node_id, name, account, clock_start=0):
        super().__init__()
        self.node_id = node_id
        self.name = name              # e.g. "ATM 1"
        self.inbox = queue.Queue()    # other nodes put messages here
        self.clock = LamportClock(clock_start)
        self.peers = []               # filled in after all nodes exist
        self.account = account
        self.running = True

        # Ricart-Agrawala state
        self.state = RELEASED
        self.request_ts = None        # timestamp of my current REQUEST
        self.replies = 0              # REPLYs received for my request
        self.deferred = []            # peers whose reply I am holding back

        self.wants_edit = False       # set by the test/main to ask for an edit
        self.done = False             # True once my edit has finished

    # ---------- logging ----------
    def log(self, text):
        with print_lock:
            print(f"[{self.name:<5} t={self.clock.time:<2}] {text}")

    # ---------- messaging ----------
    def send(self, peer, msg_type, stamp):
        message = {"from": self.node_id, "type": msg_type, "time": stamp}
        peer.inbox.put(message)

    def request_cs(self):
        # Ask every other node for permission to edit
        self.state = WANTED
        self.request_ts = self.clock.tick()   # ONE timestamp for all requests
        self.replies = 0
        for peer in self.peers:
            self.send(peer, "REQUEST", self.request_ts)
            self.log(f"REQUEST -> {peer.name} (request ts={self.request_ts})")

    def send_reply(self, peer):
        stamp = self.clock.tick()
        self.send(peer, "REPLY", stamp)
        self.log(f"REPLY -> {peer.name}")

    # ---------- handling incoming messages ----------
    def handle(self, message):
        self.clock.update(message["time"])
        sender = self.peers_by_id(message["from"])

        if message["type"] == "REPLY":
            self.replies += 1
            self.log(f"got REPLY from {sender.name} ({self.replies}/{len(self.peers)})")

        elif message["type"] == "REQUEST":
            their_ts = message["time"]
            self.log(f"got REQUEST from {sender.name} (their ts={their_ts})")

            # Defer if I'm editing, or if I'm waiting with an EARLIER request.
            # Ties on the timestamp are broken by node id (lower id wins).
            mine = (self.request_ts, self.node_id)
            theirs = (their_ts, sender.node_id)
            if self.state == HELD or (self.state == WANTED and mine < theirs):
                self.deferred.append(sender)
                self.log(f"DEFERRED reply to {sender.name} (state={self.state})")
            else:
                self.send_reply(sender)

    def peers_by_id(self, node_id):
        for peer in self.peers:
            if peer.node_id == node_id:
                return peer

    # ---------- critical section ----------
    def edit_account(self):
        self.state = HELD
        self.account.start_edit(self.name)
        self.log(f"WITHDRAW START (request ts={self.request_ts})")
        time.sleep(0.3)                       # pretend to type for a while
        self.account.end_edit()
        self.clock.tick()
        self.log("WITHDRAW END")

        # Leave the critical section: answer everyone I made wait
        self.state = RELEASED
        for peer in self.deferred:
            self.send_reply(peer)
        self.deferred = []
        self.wants_edit = False
        self.done = True

    # ---------- main loop ----------
    def run(self):
        while self.running:
            # 1. If I want to edit and haven't asked yet, send REQUESTs
            if self.wants_edit and self.state == RELEASED and not self.done:
                self.request_cs()

            # 2. Handle one incoming message (if any)
            try:
                message = self.inbox.get(timeout=0.05)
                self.handle(message)
            except queue.Empty:
                pass

            # 3. If everyone replied, it is my turn to edit
            if self.state == WANTED and self.replies == len(self.peers):
                self.edit_account()

    def stop(self):
        self.running = False
