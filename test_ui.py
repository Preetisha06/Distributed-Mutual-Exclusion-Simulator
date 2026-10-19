"""Tests for the UI support code (step-by-step mode) and every tab/button.

Run with:  python test_ui.py
"""
import time

from streamlit.testing.v1 import AppTest

from simulation import build_sim, stop_all_sims


def drain(sim, timeout=40):
    """Press 'Next' until every message is delivered and every ATM is done."""
    net = sim.network
    end = time.time() + timeout
    while time.time() < end:
        if net.pending:
            net.step()
        elif any(n.wants_edit for n in sim.nodes):
            time.sleep(0.1)            # a withdrawal is in progress
        else:
            return
    raise AssertionError("did not finish")


# ---- 1. Step-by-step Ricart-Agrawala, with the explanations ----
print("1. Step-by-step Ricart-Agrawala")
sim = build_sim("ra")
net = sim.network
net.set_step_mode(True)
atm1, atm2, atm3 = sim.nodes

sim.request(atm3)                                   # ATM 3 gets ticket 1
assert atm3.request_ts == 1
assert len(net.pending) == 2 and net.pending[0]["type"] == "REQUEST"
net.step(); net.step()                              # ATM 1 and ATM 2 receive it
net.step(); net.step()                              # ATM 3 gets two OKs (replies pending)
# hold the replies back: look at what happened so far
assert "starts withdrawing" in net.steps[-1], net.steps[-1]
print("   ", net.steps[-1])
drain(sim)

# now two ATMs compete with different tickets
sim.request(atm3)                                   # ticket is bigger now (clock moved on)
sim.request(atm1)
drain(sim)
all_text = " | ".join(net.steps)
assert "WAIT" in all_text and "replies OK" in all_text
assert "ticket" in all_text
assert sim.account.max_active == 1
assert sim.account.balance == 700, sim.account.balance
for line in net.steps:
    print("   -", line)
stop_all_sims()

# ---- 2. The exact example: later ticket gets OK'd, earlier ticket makes it wait ----
print("2. Ticket comparison wording")
sim = build_sim("ra")
net = sim.network
net.set_step_mode(True)
atm1, atm2, atm3 = sim.nodes
sim.request(atm3)                                   # ticket 1
net.step(); net.step()                              # ATM 1, ATM 2 get it and reply
sim.request(atm1)                                   # clock has moved, so ticket is larger
assert atm1.request_ts > atm3.request_ts
# deliver ATM 1's REQUEST to ATM 3 while ATM 3 is still waiting for ATM 1's OK
index = [i for i, m in enumerate(net.pending)
         if m["type"] == "REQUEST" and m["from"] == 0 and m["to"] == 2][0]
texts = [net.step(index)]
joined = " ".join(texts)
assert f"own ticket ({atm3.request_ts}) is smaller than ATM 1's ({atm1.request_ts})" in joined, joined
print("   ", texts[0])
drain(sim)
assert sim.account.max_active == 1
stop_all_sims()

# ---- 3. Step-by-step Token Ring ----
print("3. Step-by-step Token Ring")
sim = build_sim("ring")
net = sim.network
net.set_step_mode(True)
sim.request(sim.nodes[1])                           # ATM 2 wants to withdraw
end = time.time() + 10
while sim.nodes[1].wants_edit and time.time() < end:
    if net.pending:
        net.step()
    else:
        time.sleep(0.1)
end = time.time() + 5
while not net.pending and time.time() < end:        # token goes on to ATM 3
    time.sleep(0.1)
net.step()                                          # ATM 3 gets it but doesn't want it
assert sim.account.balance == 900 and sim.account.edit_order == ["ATM 2"]
assert any("withdraws now" in t for t in net.steps)
assert any("doesn't need the account" in t for t in net.steps)
for line in net.steps:
    print("   -", line)
stop_all_sims()

# ---- 4. Free-running mode still works, and leaving step mode releases messages ----
print("4. Mode switching")
sim = build_sim("ra")
sim.network.set_step_mode(True)
sim.request(sim.nodes[0])
time.sleep(0.5)
assert sim.network.pending
sim.network.set_step_mode(False)                    # release everything
drain(sim)
assert sim.account.balance == 900
stop_all_sims()

# ---- 5. Every tab and button in the Streamlit app ----
print("5. Streamlit app, every tab and button")
at = AppTest.from_file("app.py", default_timeout=60).run()
assert not at.exception, list(at.exception)
assert [t.label for t in at.tabs] == ["1. Local OS", "2. Live Demo", "3. Compare", "4. Crash"]


def click(key=None, label=None):
    button = at.button(key=key) if key else [b for b in at.button if b.label == label][0]
    button.click().run()
    assert not at.exception, (key or label, list(at.exception))


click(label="Run local demo")
click(key="req_ra_0")                               # free-running RA
click(key="all_ra")
time.sleep(5)
at.run()
assert not at.exception, list(at.exception)
at.radio(key="mode").set_value("Step-by-step").run()
click(key="req_ra_1")
for _ in range(4):
    click(key="next_ra")
assert any("step-box" in m.value for m in at.markdown), "step explanation missing"
at.radio(key="algo").set_value("Token Ring").run()
assert not at.exception
click(key="req_ring_2")
click(key="next_ring")
at.radio(key="mode").set_value("Free-running").run()
click(key="all_ring")
click(key="reset_ring")
click(label="Run both algorithms")
click(label="Run scalability test")
assert set(at.session_state["scalability"]) == {"heavy", "light"}
assert at.toggle(key="recovery").value is False      # the default stays "no recovery"
click(label="💥 Crash it and run both algorithms")
assert not at.exception
at.toggle(key="recovery").set_value(True).run()      # now the "With recovery" view
assert not at.exception, list(at.exception)
click(label="💥 Crash it and compare with / without recovery")
rec = at.session_state["crash_rec"]
assert rec[("ra", False)]["completed"] == 0 and rec[("ra", True)]["completed"] == 4
assert rec[("ring", False)]["token_lost"] and rec[("ring", True)]["tokens_created"] == 1
assert all(rec[k]["balance"] == rec[k]["expected_balance"] for k in rec if k != "id")
at.toggle(key="recovery").set_value(False).run()
assert not at.exception
print("   no exceptions in any tab")

# ---- 6. Header on every run, and dark mode ----
print("6. Header and dark mode")
assert any("MutexBank" in m.value for m in at.markdown), "header missing"
at.toggle(key="dark").set_value(True).run()
assert not at.exception, list(at.exception)
assert any("MutexBank" in m.value for m in at.markdown), "header missing in dark mode"
assert any("#0E1420" in m.value for m in at.markdown), "dark colours not applied"
click(label="Run local demo")                       # every tab still works in dark mode
click(key="all_ring")
click(label="Run both algorithms")
click(label="💥 Crash it and run both algorithms")
at.toggle(key="dark").set_value(False).run()
assert not at.exception, list(at.exception)
assert any("#FFFFFF" in m.value and "MutexBank" not in m.value for m in at.markdown)
print("   header present, dark and light mode both work")
stop_all_sims()

print("\nAll UI tests passed.")
