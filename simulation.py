"""Live simulation support for the Streamlit app.

The algorithms (node.py, token_ring.py) are NOT changed. We only:
  - give every node a special inbox (GatedQueue). In normal mode it delivers
    messages straight away. In step-by-step mode it holds them until the
    user clicks "Next", so we can deliver and explain one message at a time;
  - subclass the nodes so their log lines go to a list the UI can show.
"""
import queue
import threading
import time

from bank import BankAccount
from comparison import NAMES
from node import Node, RELEASED, WANTED, HELD
from token_ring import MessageCounter, TokenRingNode

TOKEN_DELAY = 0.7           # free-running ring: how long the token "travels"


# ---------------------------------------------------------------- network
class GatedQueue(queue.Queue):
    """An inbox that asks the Network what to do with each incoming message."""

    def __init__(self, network, owner_id):
        super().__init__()
        self.network = network
        self.owner_id = owner_id

    def put(self, item, block=True, timeout=None):
        self.network.send(self, item)       # nodes call put() to send

    def real_put(self, item):
        super().put(item)                   # actually deliver to the node


class Network:
    """Sits between the nodes: delivers, holds (step mode) and explains messages."""

    def __init__(self, kind):
        self.kind = kind                    # "ra" or "ring"
        self.lock = threading.Lock()
        self.step_mode = False
        self.token_delay = 0
        self.pending = []                   # messages held back in step mode
        self.recent = []                    # (time, message) just delivered
        self.in_transit = None              # token currently "travelling"
        self.token_started = False
        self.steps = []                     # plain-English explanations
        self.nodes = []

    # ----- sending -----
    def sender_of(self, queue_, item):
        if "from" in item:                  # Ricart-Agrawala messages say who sent them
            return item["from"]
        if not self.token_started:          # the very first token has no sender
            self.token_started = True
            return None
        return (queue_.owner_id - 1) % len(self.nodes)   # token comes from the previous node

    def send(self, queue_, item):
        msg = {"from": self.sender_of(queue_, item), "to": queue_.owner_id,
               "type": item["type"], "time": item["time"],
               "item": item, "queue": queue_}
        if self.step_mode:
            with self.lock:
                self.pending.append(msg)    # wait for the Next button
            return
        if msg["type"] == "TOKEN" and self.token_delay:
            self.in_transit = msg           # let the viewer see the token travel
            time.sleep(self.token_delay)
        self.deliver(msg)
        self.in_transit = None

    def deliver(self, msg):
        with self.lock:
            self.recent.append((time.time(), msg))
            self.recent = self.recent[-30:]
        msg["queue"].real_put(msg["item"])

    def set_step_mode(self, on):
        if on == self.step_mode:
            return
        self.step_mode = on
        if not on:                          # leaving step mode: release everything held
            with self.lock:
                held, self.pending = self.pending, []
            for msg in held:
                self.deliver(msg)

    # ----- what the diagram should draw -----
    def arrows(self):
        """Messages to draw as arrows: held ones in step mode, else just-sent ones."""
        now = time.time()
        with self.lock:
            if self.step_mode:
                msgs = list(self.pending)
            else:
                msgs = [m for t, m in self.recent if now - t < 1.2]
        return [m for m in msgs if m["from"] is not None]

    def token_info(self):
        for node in self.nodes:
            if getattr(node, "has_token", False):
                return {"kind": "at", "node": node.node_id}
        with self.lock:
            msgs = list(self.pending)
        if self.in_transit:
            msgs.append(self.in_transit)
        for m in msgs:
            if m["type"] == "TOKEN":
                if m["from"] is None:
                    return {"kind": "at", "node": m["to"]}
                return {"kind": "moving", "frm": m["from"], "to": m["to"]}
        return None

    # ----- step-by-step -----
    def describe(self, msg):
        """One-line description of a held message, for the 'up next' list."""
        to = NAMES[msg["to"]]
        if msg["from"] is None:
            return f"token is created at {to}"
        text = f"{NAMES[msg['from']]} → {to}: {msg['type']}"
        if msg["type"] == "REQUEST":
            text += f" (ticket {msg['time']})"
        return text

    def step(self, index=0):
        """Deliver a held message (the oldest by default) and explain what happened."""
        with self.lock:
            if not self.pending:
                return None
            msg = self.pending.pop(index)
        receiver = self.nodes[msg["to"]]
        before = {"state": getattr(receiver, "state", None),
                  "request_ts": getattr(receiver, "request_ts", None),
                  "wants": receiver.wants_edit}

        self.deliver(msg)
        end = time.time() + 1.5             # wait until the node has handled it
        while not msg["queue"].empty() and time.time() < end:
            time.sleep(0.02)
        time.sleep(0.15)

        if msg["type"] == "TOKEN":
            text = self.explain_token(msg, receiver, before)
        elif msg["type"] == "REQUEST":
            text = self.explain_request(msg, receiver, before)
        else:
            text = self.explain_reply(msg, receiver)
        self.steps.append(text)
        return text

    def explain_request(self, msg, receiver, before):
        sender = self.nodes[msg["from"]]
        me, other = receiver.name, sender.name
        their_ts = msg["time"]
        head = f"{other} asks {me} for permission (ticket {their_ts}). "
        deferred = sender in receiver.deferred      # what the real algorithm did

        if before["state"] == HELD:
            return head + (f"{me} makes {other} WAIT (deferred) because {me} is "
                           f"withdrawing right now. It will reply when it finishes.")
        if before["state"] == WANTED:
            mine, theirs = before["request_ts"], their_ts
            if mine == theirs:
                why = (f"both tickets are {mine}, and {me if deferred else other} "
                       f"has the lower ID")
            elif deferred:
                why = f"{me}'s own ticket ({mine}) is smaller than {other}'s ({theirs})"
            else:
                why = f"{other}'s ticket ({theirs}) is smaller than its own ({mine})"
            if deferred:
                return head + f"{me} makes {other} WAIT (deferred) because {why}, so {me} goes first."
            return head + f"{me} replies OK to {other} because {why}."
        return head + f"{me} replies OK to {other} because it doesn't need the account."

    def explain_reply(self, msg, receiver):
        sender = self.nodes[msg["from"]]
        needed = len(receiver.peers)
        text = (f"{sender.name} says OK to {receiver.name}. "
                f"{receiver.name} now has {receiver.replies} of {needed} OKs.")
        if receiver.replies == needed:
            text += f" That is everyone, so {receiver.name} starts withdrawing!"
        return text

    def explain_token(self, msg, receiver, before):
        me = receiver.name
        nxt = receiver.next_node.name
        if msg["from"] is None:
            return f"The token starts at {me}. Only the token holder may withdraw."
        sender = self.nodes[msg["from"]].name
        if before["wants"]:
            return (f"{me} receives the token from {sender} and wants to withdraw, "
                    f"so it withdraws now. Afterwards it passes the token to {nxt}.")
        return (f"{me} receives the token from {sender} but doesn't need the account, "
                f"so it passes the token on to {nxt}.")


# ---------------------------------------------------------------- nodes
class UIBank(BankAccount):
    """Same account, but pauses after reading so the viewer can see it."""

    def start_edit(self, name):
        super().start_edit(name)            # reads the balance
        time.sleep(0.8)                     # "ATM is counting the cash"


class UINode(Node):
    """Ricart-Agrawala node whose log lines go to a list the UI shows."""

    def __init__(self, node_id, name, account, log_lines, log_lock):
        super().__init__(node_id, name, account)
        self.log_lines = log_lines
        self.log_lock = log_lock

    def log(self, text):
        line = f"[{self.name:<5} t={self.clock.time:<2}] {text}"
        with self.log_lock:
            self.log_lines.append(line)


class UIRingNode(TokenRingNode):
    """Token Ring node whose log lines go to a list the UI shows."""

    def __init__(self, node_id, name, account, counter, log_lines, log_lock):
        super().__init__(node_id, name, account, counter)
        self.log_lines = log_lines
        self.log_lock = log_lock

    def log(self, text):
        line = f"[{self.name:<5} t={self.clock.time:<2}] {text}"
        with self.log_lock:
            self.log_lines.append(line)


# ---------------------------------------------------------------- the simulation
all_sims = []       # so Reset can stop old threads


class Sim:
    def __init__(self, kind, nodes, account, network, log_lines, log_lock):
        self.kind = kind
        self.nodes = nodes
        self.account = account
        self.network = network
        self.log_lines = log_lines
        self.log_lock = log_lock

    def status(self, node):
        """Idle / Waiting / Withdrawing for the colours and cards."""
        if self.kind == "ra":
            return {RELEASED: "Idle", WANTED: "Waiting", HELD: "Withdrawing"}[node.state]
        if self.account.current_atm == node.name:
            return "Withdrawing"
        return "Waiting" if node.wants_edit else "Idle"

    def request(self, node):
        """The user clicked 'Withdraw at this ATM'."""
        if self.kind == "ra":
            if node.state != RELEASED or node.wants_edit:
                return
        elif node.wants_edit:
            return
        node.done = False
        node.wants_edit = True              # the node thread picks this up
        if self.network.step_mode:
            self.explain_request_start(node)

    def explain_request_start(self, node):
        if self.kind == "ra":
            end = time.time() + 1
            while node.state != WANTED and time.time() < end:
                time.sleep(0.02)
            others = " and ".join(p.name for p in node.peers)
            self.network.steps.append(
                f"{node.name} wants to withdraw. It takes ticket {node.request_ts} "
                f"(its Lamport clock) and sends a REQUEST to {others}.")
        else:
            self.network.steps.append(
                f"{node.name} wants to withdraw, but it must wait until the token arrives.")

    def stop(self):
        for node in self.nodes:
            node.stop()


def build_sim(kind):
    """Create 3 ATMs for 'ra' (Ricart-Agrawala) or 'ring' (Token Ring) and start them."""
    account = UIBank()
    network = Network(kind)
    log_lines = []
    log_lock = threading.Lock()

    if kind == "ra":
        nodes = [UINode(i, NAMES[i], account, log_lines, log_lock) for i in range(3)]
        for node in nodes:
            for other in nodes:
                if other is not node:
                    node.peers.append(other)
    else:
        counter = MessageCounter()
        nodes = [UIRingNode(i, NAMES[i], account, counter, log_lines, log_lock)
                 for i in range(3)]
        for i in range(3):
            nodes[i].next_node = nodes[(i + 1) % 3]

    network.nodes = nodes
    for node in nodes:
        node.daemon = True                  # threads die when the app exits
        node.inbox = GatedQueue(network, node.node_id)
        node.start()
    if kind == "ring":
        nodes[0].inbox.put({"type": "TOKEN", "time": 0})    # token starts at ATM 1
        network.token_delay = TOKEN_DELAY   # from now on the token visibly travels

    sim = Sim(kind, nodes, account, network, log_lines, log_lock)
    all_sims.append(sim)
    return sim


def stop_all_sims():
    for sim in all_sims:
        sim.stop()
    all_sims.clear()
