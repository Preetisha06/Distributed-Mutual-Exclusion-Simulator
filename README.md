# MutexBank: Distributed Mutual Exclusion with 3 ATMs and 1 Bank Account

A small Python project that simulates **mutual exclusion** (only one process in the
critical section at a time) in a distributed system. It compares two message-based
algorithms, **Ricart-Agrawala** and **Token Ring**, and shows what goes wrong when a
node crashes. A Streamlit page lets you watch it all live.

---

## 1. The problem

Three ATMs are connected to one bank account that starts with a balance of **1000**.
Each withdrawal does three steps:

1. **Read** the balance
2. **Wait** briefly (counting the cash)
3. **Write** the new balance (read value minus 100)

Those three steps are the **critical section**. If two ATMs run them at the same time,
both read 1000, both write 900, and one withdrawal is lost. The bank has just given out
200 but only recorded 100.

**Mutual exclusion** means: at any moment, at most one ATM is inside the critical section.

---

## 2. Why a semaphore works on one machine but not across machines

**On one computer** (see `local_os.py`): the ATMs are threads that share the same memory.
The operating system gives us a **semaphore** (a counter starting at 1):

- `acquire()`: if the counter is 1, set it to 0 and go in. If it is 0, wait.
- `release()`: set it back to 1 so the next waiting thread can go in.

Because every thread can see the *same* semaphore in shared memory, only one gets
through at a time. Our demo shows this: 3 threads, 2 withdrawals each, correct final
balance 400.

| Version | Final balance | Correct? |
|---|---|---|
| No lock | 800 | No, withdrawals were lost |
| With semaphore | 400 | Yes |

**Across machines**, real ATMs are separate computers. They have **no shared memory**, so
there is no single semaphore they can all see. The only thing they can do is **send
messages** to each other. So we need algorithms where the nodes agree on who goes next
using messages only. That is what Ricart-Agrawala and Token Ring do.

---

## 3. Lamport logical clock

Different machines have different physical clocks, so we cannot trust them to order
events. A **Lamport clock** is just a counter in each node that respects cause and effect.

Rules (see `LamportClock` in `node.py`):

1. **Local event or sending a message:** `clock = clock + 1`. Send the new value with the message.
2. **Receiving a message:** `clock = max(my clock, message's clock) + 1`.

So if event A could have caused event B, then A's number is smaller than B's. Ricart-Agrawala
uses this number as the **timestamp** of a request: the smaller timestamp is "earlier".

If two requests have the **same** timestamp, we break the tie with the **node id** (lower id
wins). So requests are compared as the pair `(timestamp, node id)`.

---

## 4. Ricart-Agrawala (permission based)

Idea: *to enter, ask everyone else for permission, and enter only when all of them say yes.*

Each node is in one of three states: **RELEASED** (idle), **WANTED** (asked, waiting), **HELD**
(in the critical section).

### Step by step

**To enter the critical section**
1. Set state to WANTED. Tick the Lamport clock; that value is the request timestamp.
2. Send `REQUEST(timestamp, my id)` to **every other** node.
3. Wait until you have received a `REPLY` from **every other** node.
4. Set state to HELD and do the withdrawal.

**When a node receives a REQUEST**
- If I am **HELD**, or I am **WANTED with an earlier** `(timestamp, id)` than theirs:
  **defer**, which means remember them and do not reply yet.
- Otherwise: send `REPLY` immediately.

**To leave**
1. Set state to RELEASED.
2. Send `REPLY` to every node you deferred.

### Why it is safe
Two nodes cannot both be in: each would need a reply from the other, but the one with the
later `(timestamp, id)` is always deferred by the earlier one.

### Message cost
For N nodes: `(N-1)` requests + `(N-1)` replies = **2(N-1)** messages per entry. For 3 nodes
that is **4**, always.

Code: `node.py`. Test: `test_mutex.py`.

---

## 5. Token Ring (token based)

Idea: *a single token goes round a ring; only the holder may enter.*

The ATMs sit in a ring: ATM 1 → ATM 2 → ATM 3 → ATM 1.

### Step by step
1. At the start, ATM 1 holds the token.
2. A node that receives the token checks: do I want to withdraw?
   - **Yes:** do the withdrawal (it is safe, because nobody else has the token).
   - **No:** keep it for a moment and move on.
3. Pass the token to the **next** node in the ring (one `TOKEN` message).
4. Repeat forever.

### Why it is safe
There is exactly one token, so at most one node can be in the critical section.

### Message cost
Each token pass is one message. A request waits between 0 and N-1 passes for the token.
Cost per entry is between **1 and N-1** passes: low when many nodes want to enter (the
token is always useful), higher when requests are rare (the token travels a long way for
one withdrawal).

Order of service is **ring order**, not request order, so it ignores timestamps.

Code: `token_ring.py` (Lamport clocks are used on the token too).

---

## 6. Comparison results

All nodes request at the same moment. Message counts are exact. The same requests are run
through both algorithms in `comparison.py`.

| Who withdraws | Ricart-Agrawala | Token Ring |
|---|---|---|
| ATM 1, 2, 3 (3 entries) | 12 messages, **4.0** per entry | 2 messages, **0.67** per entry |
| ATM 3 only (1 entry) | 4 messages, **4.0** per entry | 2 messages, **2.0** per entry |
| ATM 1 and 3 (2 entries) | 8 messages, **4.0** per entry | 2 messages, **1.0** per entry |

In every run the final balance is correct (1000 minus 100 per withdrawal) and never more
than one ATM is in the critical section.

| | Ricart-Agrawala | Token Ring |
|---|---|---|
| Messages per entry | Always 2(N-1) = 4 | 1 to N-1, depends on load |
| Fault tolerance | No single point of failure, but needs a reply from *everyone*, so one crash blocks all | Lost token or crashed node breaks the ring |
| Waiting | Only waits for replies (quick if nobody else wants in). Served in timestamp order (fair) | Waits for the token, up to N-1 hops even if nobody else wants in. Served in ring order |

Notes: Token Ring messages are counted up to the last withdrawal (otherwise the idle token
would circulate forever). Wait times are wall-clock and include the 0.3 s each ATM spends
in its withdrawal, so they vary slightly between runs. The token starts at ATM 1, which
favours it.

---

## 7. Crash results

`crash.py` simulates a crash by never starting one node's thread, so it never answers. The
other two ATMs try to withdraw, and we watch for 2 seconds.

**Ricart-Agrawala: stuck.** Each surviving ATM needs a `REPLY` from *every* other node,
including the dead one, which never comes. Both wait forever. Nobody withdraws and the
balance stays 1000. This is the same whichever ATM crashes.

**Token Ring: token lost.** The token is eventually passed to the dead node and never
leaves. ATMs *before* the dead one in the ring still get their turn:

| Crashed | Who withdrew before the token was lost | Starved |
|---|---|---|
| ATM 1 | nobody | ATM 2, ATM 3 |
| ATM 2 | ATM 1 | ATM 3 |
| ATM 3 | ATM 1, ATM 2 | none left to starve, but the token is gone for good |

**Takeaway:** neither algorithm as written survives a crash. Real systems add failure
detection (timeouts), and for Token Ring, token regeneration and ring repair.

---

### Crash recovery (the "With recovery" switch)

`recovery.py` adds recovery without changing `node.py` or `token_ring.py` (it subclasses the nodes).

**Ricart-Agrawala:** an ATM that waits for a peer uses a 1 s timeout. If the peer has sent neither
a `REPLY` nor an `ACK`, the ATM marks it **failed**, removes it from the group and carries on. The
event shows which ATM noticed and when (about +1.0 s). The `ACK` is needed because a live peer can
stay silent for a while on purpose (it is withdrawing, or it deferred our reply): a peer that
defers us sends a quick `ACK` ("got your request, I'll reply later"), so only a completely silent
ATM is treated as crashed.

**Token Ring:** every ATM sends `ALIVE` heartbeats, so the ring knows who is dead and **skips** it.
If an ATM has not seen the token for 1.5 s, the **lowest-id ATM that is alive** creates a new
token. All ATMs use the same rule, so only one new token is created.

In the demo each surviving ATM withdraws twice (at the start and at +3.5 s). Result for ATM 3
crashed: without recovery 0 of 4 withdrawals (Ricart-Agrawala) and 2 of 4 (Token Ring); with
recovery 4 of 4 for both, and the final balance is exactly 1000 - 100 x withdrawals, with never
more than one ATM in the critical section.

**Limitation:** a failure detector only sees silence, so a *slow* ATM can be wrongly treated as
crashed. The others then carry on without it and it may enter the critical section at the same
time as someone else, breaking mutual exclusion. A longer timeout means fewer false alarms but
slower recovery. `test_recovery.py` demonstrates the false alarm.

## 8. Files

| File | What it does |
|---|---|
| `node.py` | Lamport clock, `SharedAccount`, and the **Ricart-Agrawala** node (a thread with an inbox queue) |
| `token_ring.py` | The **Token Ring** node and ring setup |
| `bank.py` | `BankAccount`: the shared account with read / wait / write |
| `local_os.py` | Local version: 3 threads, no lock vs semaphore |
| `comparison.py` | Runs both algorithms on the same requests and measures messages and waiting |
| `scalability.py` | Runs both algorithms for N = 3, 5, 7, 10 ATMs, heavy and light load |
| `crash.py` | Crash demo for both algorithms (no recovery) |
| `recovery.py` | Crash recovery: Ricart-Agrawala timeouts, Token Ring heartbeats and token regeneration |
| `app.py` | Streamlit UI with four tabs (see below) |
| `simulation.py` | Connects the algorithms to the UI: step-by-step message delivery and plain-English explanations |
| `visuals.py` | Network diagram (ATM circles, arrows, token) and the colour-coded message log |
| `main.py` | Simple terminal demo of Ricart-Agrawala |
| `test_mutex.py` | Tests Ricart-Agrawala: mutual exclusion and timestamp order |
| `test_features.py` | Tests bank account, local race vs semaphore, crash demo |
| `test_scalability.py` | Tests the N = 3 to 10 runs: exact message counts and trends |
| `test_recovery.py` | Tests recovery for every crashed ATM, one new token only, correct balance, slow-ATM limitation |
| `test_ui.py` | Tests step-by-step mode and clicks every tab and button in the app |

The Streamlit app is called **MutexBank**. Its header sits above every tab, with a **Dark mode**
switch next to it (you can also open `http://localhost:8501/?theme=dark` to start in dark mode).
It has four tabs:

1. **Local OS**: a short "How it works" intro, and the no-lock vs semaphore demo.
2. **Live Demo**: pick **Ricart-Agrawala** or **Token Ring**, and **Free-running** or
   **Step-by-step**. Shows a network diagram (grey = Idle, yellow = Waiting,
   green = Withdrawing, red = Crashed; arrows are messages; in Token Ring the token is
   highlighted), the balance as a big number with a small chart, ATM cards, and a
   colour-coded message log (oldest first: REQUEST blue, REPLY green, DEFERRED orange,
   WITHDRAW purple, TOKEN teal).
   In **Step-by-step** mode messages are held back; press **Next** to deliver one at a
   time. Each step is explained, e.g. "ATM 1 replies OK to ATM 3 because ATM 3's
   ticket (1) is smaller than its own (4)". A "ticket" is the Lamport timestamp.
3. **Compare**: runs both algorithms on the same requests (bar chart starts at 0). A **Scalability**
   section below it runs N = 3, 5, 7 and 10 ATMs under heavy load (all withdraw at once) and light
   load (one ATM withdraws) and plots messages per entry against N, with the theoretical
   2(N-1) for Ricart-Agrawala as a dashed line.
4. **Crash**: pick a crashed ATM and see Ricart-Agrawala stuck and Token Ring lose the token.
   Switch on **With recovery** to see each algorithm run without and with recovery, side by side
   (see "Crash recovery" below). The default is still no recovery.

The step-by-step mode uses the real algorithm code: each node's inbox is swapped for a
"gated" inbox that holds messages until you press Next. The algorithms are not changed.

---

## 9. How to run everything

Needs Python 3 (tested on 3.12).

```powershell
cd C:\Users\Preetisha\Downloads\mutex-simulator
pip install -r requirements.txt     # installs streamlit
```

**The UI** (opens in your browser, usually http://localhost:8501):
```powershell
streamlit run app.py
```

**Terminal demos:**
```powershell
python main.py          # Ricart-Agrawala, 3 ATMs all request at once
python token_ring.py    # Token Ring demo
python local_os.py      # no lock vs semaphore
python comparison.py    # messages and waiting, both algorithms
python crash.py         # crash results
```

**Tests:**
```powershell
python test_mutex.py      # mutual exclusion + smallest timestamp goes first
python test_features.py   # bank balance, local race, crash behaviour
python test_recovery.py     # crash recovery (about 10 seconds)
python test_scalability.py  # message counts for N = 3, 5, 7, 10
python test_ui.py         # step-by-step mode + every tab and button in the app
```

Everything except the UI uses only the Python standard library.

---

## 10. Likely viva questions

**1. What is mutual exclusion?**
Only one process may be in the critical section at a time, so shared data is never
updated by two processes at once.

**2. What is a critical section? What is it in this project?**
The code that touches shared data. Here it is one ATM's read-balance, wait, write-balance
withdrawal.

**3. What is a race condition? Show an example.**
The result depends on timing. Two ATMs read 1000 and both write 900, so a withdrawal is
lost. In `local_os.py` without a lock we get 800 instead of 400.

**4. Why does a semaphore work on one machine?**
Threads share memory, so they all see the same semaphore. `acquire` lets only one in and
`release` lets the next in, and the OS makes these operations atomic.

**5. Why can't we use a semaphore across machines?**
There is no shared memory between machines. The only communication is messages, which can
be delayed, so we need message-based algorithms.

**6. What is a Lamport clock and what are its rules?**
A logical counter that orders events without physical time. Tick before a local event or
send; on receive, set it to `max(own, received) + 1`. If A causes B, then A's time is
smaller.

**7. Does a smaller Lamport timestamp mean the event really happened first?**
No. It only guarantees the reverse: if A happened-before B, A's time is smaller. Two
unrelated events can have any order. That is fine here because we only need a consistent
order to agree on.

**8. How does Ricart-Agrawala work?**
To enter, send a timestamped REQUEST to all others and wait for REPLY from all. A node
replies at once unless it is in the critical section or has an earlier pending request, in
which case it defers the reply until it leaves.

**9. How are ties between equal timestamps broken?**
By node id: compare `(timestamp, id)` and the lower one wins. This gives a total order.

**10. How many messages does Ricart-Agrawala use per entry?**
2(N-1): N-1 requests plus N-1 replies. For 3 nodes, 4.

**11. How does Token Ring work, and what does it cost in messages?**
One token circulates around the ring and only the holder may enter. Cost is 1 to N-1
token passes per entry, depending on how many nodes want in. In our test, three requests
used 2 passes in total (0.67 per entry), but a single request from ATM 3 used 2 passes.

**12. Which is better, Ricart-Agrawala or Token Ring?**
Neither always. Token Ring uses fewer messages under heavy load, but a token has to
travel even for one request. Ricart-Agrawala has a fixed cost and serves in timestamp
order (fair), but sends many more messages. Both are weak against crashes.

**13. What happens in Ricart-Agrawala if a node crashes?**
Everyone who needs a reply from it waits forever (deadlock-like blocking), since entry
needs replies from all nodes. In the demo, nobody withdraws and the balance stays 1000.

**14. What happens in Token Ring if a node crashes or the token is lost?**
The token is passed to the dead node and vanishes, so no one can ever enter again. In the
demo, ATMs before the dead one in the ring get a turn first and everyone after it starves.

**15. How could these crashes be handled?**
Add failure detection with timeouts. For Ricart-Agrawala, stop waiting for nodes declared
dead (or use majority/quorum-based variants such as Maekawa). For Token Ring, detect the
lost token with a timer, elect a node to regenerate it (making sure there is only one),
and repair the ring by skipping the dead node.
