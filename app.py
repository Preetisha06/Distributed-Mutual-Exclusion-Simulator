"""Streamlit UI: 3 ATMs withdrawing from one shared bank account.

Run with:  streamlit run app.py
The algorithms live in node.py (Ricart-Agrawala) and token_ring.py and are
not changed here. simulation.py wires them to the UI, visuals.py draws.
"""
from concurrent.futures import ThreadPoolExecutor
from string import Template

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from bank import START_BALANCE
from comparison import NAMES, run_ricart_agrawala, run_token_ring
from crash import run_crash_ricart_agrawala, run_crash_token_ring
from local_os import run_local
from scalability import SIZES, run_scalability, theory_ricart_agrawala
from recovery import run_ra_scenario, run_ring_scenario
from simulation import build_sim, stop_all_sims
from visuals import (STATUS_COLORS, MSG_COLORS, THEMES, log_html, message_arrows,
                     network_svg)

st.set_page_config(page_title="MutexBank", page_icon="🏧", layout="wide")

# Colours for the two modes (the status / message colours stay the same in both)
PALETTE = {
    False: dict(bg="#FFFFFF", panel="#EEF2F8", text="#1B2430", muted="#5B6675",
                border="#D5DCE6", step="#EEF4FF", accent="#2F6FDE", banner="#2F6FDE"),
    True: dict(bg="#0E1420", panel="#172033", text="#E8EDF5", muted="#9AA7BA",
               border="#2C3A52", step="#14264A", accent="#6FA0FF", banner="#1F4FAE"),
}

# Bigger fonts for projectors, plus the colours of the chosen mode
CSS = Template("""
<style>
html, body, [class*="st-"], .stMarkdown, p, li { font-size: 1.12rem; }
h2, h3 { font-size: 2rem !important; }
.stTabs [data-baseweb="tab"] p { font-size: 1.35rem; font-weight: 700; }
.stButton button p { font-size: 1.15rem; font-weight: 600; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * { font-size: 3.2rem; }
[data-testid="stMetricLabel"] p, [data-testid="stMetricDelta"] { font-size: 1.1rem; }
table { font-size: 1.1rem; }
.balance-label { font-size: 1.3rem; font-weight: 600; color: $muted; }
.balance-big { font-size: 6rem; font-weight: 800; line-height: 1.05; color: $text; }
.step-box { background: $step; border-left: 8px solid $accent; border-radius: 8px;
            padding: 16px 20px; font-size: 1.5rem; font-weight: 600; color: $text; }
.badge { color: white; padding: 2px 12px; border-radius: 12px; font-weight: 700; }
.mb-banner { background: $banner; border-radius: 14px; padding: 14px 26px; }
.mb-banner .mb-name { color: white; font-size: 2.8rem; font-weight: 800; line-height: 1.1; }
.mb-banner .mb-tag { color: #DCE7FF; font-size: 1.2rem; font-weight: 500; }

/* colours of the chosen mode */
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"],
[data-testid="stMain"] { background: $bg !important; }
.stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp h5, .stApp h6, .stApp table, .stApp th, .stApp td,
[data-testid="stMetricValue"], [data-testid="stMetricValue"] *,
[data-testid="stMetricLabel"] p, [data-testid="stExpander"] summary p { color: $text; }
[data-testid="stToolbar"] button, [data-testid="stToolbar"] span { color: $muted !important; }
[data-testid="stCaptionContainer"] p { color: $muted; }
.stTabs [data-baseweb="tab"] p { color: $muted; }
.stTabs [aria-selected="true"] p { color: $accent; }
[data-testid="stBaseButton-secondary"] { background: $panel; border: 1px solid $border; }
[data-testid="stBaseButton-secondary"] p { color: $text; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: $border !important; }
.stApp th { background: $panel; }
.stApp th, .stApp td { border-color: $border; }
[data-testid="stExpander"] { border-color: $border; }
[data-baseweb="select"] div:not([data-baseweb="tag"] *) { background-color: $panel !important; border-color: $border !important; }
[data-baseweb="select"] * { color: $text; }
[data-baseweb="popover"] ul, [data-baseweb="menu"] { background: $panel; color: $text; }
</style>
""")


BLANK_LINE = "\n\n"        # separates the bullet points in a markdown box


def is_dark():
    return st.session_state.get("dark", False)


def style_chart(chart, font_size=15):
    """Colour an Altair chart for the current mode."""
    t = THEMES[is_dark()]
    return (chart.configure(background=t["bg"])
            .configure_axis(labelFontSize=font_size, titleFontSize=font_size,
                            labelColor=t["text"], titleColor=t["text"],
                            gridColor=t["border"], domainColor=t["border"],
                            tickColor=t["border"])
            .configure_legend(labelColor=t["text"], titleColor=t["text"],
                              labelFontSize=font_size, titleFontSize=font_size,
                              orient="top", symbolStrokeWidth=4)
            .configure_view(stroke=None))


@st.cache_resource
def get_sim(kind):
    """Create (once) and keep running the live simulation: 'ra' or 'ring'."""
    return build_sim(kind)


def badge(text, color, dark_text=False):
    return (f'<span class="badge" style="background:{color};'
            f'color:{"#1B2430" if dark_text else "white"}">{text}</span>')


# ---- header shown above every tab ----
banner_col, switch_col = st.columns([5, 1])
with switch_col:
    st.write("")
    st.toggle("🌙 Dark mode", key="dark",
              value=st.query_params.get("theme") == "dark")   # ?theme=dark starts dark
st.query_params["theme"] = "dark" if is_dark() else "light"
st.markdown(CSS.substitute(PALETTE[is_dark()]), unsafe_allow_html=True)
with banner_col:
    st.markdown('<div class="mb-banner"><div class="mb-name">🏧 MutexBank</div>'
                '<div class="mb-tag">3 ATMs, 1 shared account: mutual exclusion in a '
                'distributed system</div></div>', unsafe_allow_html=True)

tab_local, tab_live, tab_compare, tab_crash = st.tabs(
    ["1. Local OS", "2. Live Demo", "3. Compare", "4. Crash"])


# ======================= Tab 1: Local OS version =======================
with tab_local:
    st.header("How it works")
    st.markdown(f"""
- **The problem:** 3 ATMs share one bank account (balance **{START_BALANCE}**).
  Each withdrawal *reads* the balance, *waits* briefly, then *writes* the new balance.
  If two ATMs do this at the same time, one withdrawal is lost. That read-wait-write is the **critical section**.
- **One computer:** threads share memory, so the operating system's **semaphore** keeps them in line.
- **Many computers:** no shared memory, so the ATMs can only send **messages**. We try two message-based algorithms:
  - **Ricart-Agrawala:** ask everyone for permission using a numbered **ticket** (a Lamport clock value). Smallest ticket goes first.
  - **Token Ring:** pass one **token** around a ring. Only the holder may withdraw.
- Use the tabs above: **Live Demo** to watch it, **Compare** to measure messages, **Crash** to see what breaks.
""")

    st.header("Local OS version (one machine)")
    st.write("Three threads on one computer withdraw from the same account "
             f"(2 withdrawals of 100 each, so the correct final balance is {START_BALANCE - 600}).")

    if st.button("Run local demo"):
        st.session_state["local"] = {"no_lock": run_local(False),
                                     "lock": run_local(True)}

    local = st.session_state.get("local")
    if local:
        left, right = st.columns(2)
        for column, title, key in [(left, "❌ NO lock", "no_lock"),
                                   (right, "✅ With semaphore", "lock")]:
            r = local[key]
            with column.container(border=True):
                st.subheader(title)
                st.metric("Final balance", r["final"], f"expected {r['expected']}",
                          delta_color="off")
                if r["final"] == r["expected"]:
                    st.success("Correct")
                else:
                    st.error(f"Wrong! {r['final'] - r['expected']} too much money left: "
                             "withdrawals were lost")
                st.table([{"ATM": n, "read": a, "wrote": b}
                          for n, a, b in r["history"]])

    st.info("**Why this works locally:** all threads share one memory, so the "
            "operating system can offer a **semaphore**. A thread must acquire it "
            "before entering the critical section and release it after, so only one "
            "thread runs read-wait-write at a time.\n\n"
            "**Why it doesn't work across machines:** real ATMs are separate "
            "computers with **no shared memory**, so there is no semaphore they can "
            "all see. They can only send **messages**, so we need message-based "
            "algorithms like Ricart-Agrawala and Token Ring.")


# ======================= Tab 2: live demo =======================
@st.fragment(run_every=0.7)
def live_view(kind):
    """The live part of the page; re-runs every 0.7s so it updates by itself."""
    sim = get_sim(kind)
    net = sim.network
    account = sim.account
    ring = kind == "ring"

    # ----- buttons -----
    cols = st.columns(5)
    for i, node in enumerate(sim.nodes):
        if cols[i].button(f"Withdraw at {node.name}", key=f"req_{kind}_{i}",
                          use_container_width=True):
            sim.request(node)
    if cols[3].button("Request all at once", type="primary", key=f"all_{kind}",
                      use_container_width=True):
        for node in sim.nodes:
            sim.request(node)
    if cols[4].button("🔄 Reset", key=f"reset_{kind}", use_container_width=True):
        stop_all_sims()                      # stop old threads, then start fresh
        get_sim.clear()
        st.rerun()

    # ----- step-by-step panel -----
    if net.step_mode:
        pending = list(net.pending)
        left, right = st.columns([1, 3])
        if left.button(f"Next ▶  ({len(pending)} waiting)", key=f"next_{kind}",
                       type="primary", disabled=not pending, use_container_width=True):
            net.step()                       # deliver ONE message and explain it
        pending = list(net.pending)
        if pending:
            right.markdown("**Up next:** " + net.describe(pending[0])
                           + (f"  (then {len(pending) - 1} more)" if len(pending) > 1 else ""))
        else:
            right.markdown("*Nothing waiting. Press a Withdraw button, or wait for a "
                           "withdrawal to finish.*")
        if net.steps:
            st.markdown(f'<div class="step-box">Step {len(net.steps)}: {net.steps[-1]}</div>',
                        unsafe_allow_html=True)
            if len(net.steps) > 1:
                with st.expander("Earlier steps"):
                    for n in range(len(net.steps) - 1, 0, -1):
                        st.markdown(f"**{n}.** {net.steps[n - 1]}")
        else:
            st.markdown('<div class="step-box">Press a <b>Withdraw</b> button to begin, '
                        'then <b>Next</b> to move one message at a time.</div>',
                        unsafe_allow_html=True)

    # ----- diagram (left) and balance (right) -----
    diagram_col, balance_col = st.columns([3, 2])
    statuses = [sim.status(n) for n in sim.nodes]
    notes = [f"clock t={n.clock.time}" for n in sim.nodes]
    with diagram_col:
        if ring:
            svg = network_svg(NAMES, statuses, notes, ring_edges=True,
                              token=net.token_info(), dark=is_dark())
        else:
            svg = network_svg(NAMES, statuses, notes,
                              arrows=message_arrows(net.arrows(), NAMES), dark=is_dark())
        components.html(svg, height=430)

    with balance_col:
        st.markdown(f'<div class="balance-label">Account balance</div>'
                    f'<div class="balance-big">{account.balance}</div>',
                    unsafe_allow_html=True)
        atm = account.current_atm
        if atm:
            st.markdown(f"🏧 **{atm}** read {account.read_value}, "
                        f"will write {account.read_value - account.amount}")
        else:
            st.markdown("✅ Account is free")
        balances = [START_BALANCE] + [h[2] for h in account.history]
        df = pd.DataFrame({"Withdrawals so far": range(len(balances)),
                           "Balance": balances})
        chart = alt.Chart(df).mark_line(
            interpolate="step-after", point=True, strokeWidth=4, color=PALETTE[is_dark()]["accent"]
        ).encode(
            x=alt.X("Withdrawals so far:Q", axis=alt.Axis(tickMinStep=1)),
            y=alt.Y("Balance:Q", scale=alt.Scale(domain=[0, START_BALANCE])),
        ).properties(height=200)
        st.altair_chart(style_chart(chart), use_container_width=True, theme=None)

    # ----- ATM cards -----
    cols = st.columns(3)
    for i, node in enumerate(sim.nodes):
        status = statuses[i]
        with cols[i].container(border=True):
            st.markdown(f"#### {node.name}")
            st.markdown(badge(status, STATUS_COLORS[status],
                              dark_text=status in ("Idle", "Waiting")),
                        unsafe_allow_html=True)
            st.markdown(f"**Lamport clock:** {node.clock.time}")
            if ring:
                st.markdown(f"**Holds the token:** {'yes' if node.has_token else 'no'}")
            else:
                if status != "Idle":
                    st.markdown(f"**Ticket:** {node.request_ts}")
                deferred = ", ".join(p.name for p in node.deferred) or "none"
                st.markdown(f"**Deferring replies to:** {deferred}")

    # ----- message log, oldest first -----
    st.subheader("Message log")
    with sim.log_lock:
        recent = sim.log_lines[-80:]
    components.html(log_html(recent, show_token=ring, dark=is_dark()), height=380)


with tab_live:
    st.header("Live demo")
    left, right = st.columns(2)
    algo = left.radio("Algorithm", ["Ricart-Agrawala", "Token Ring"],
                      horizontal=True, key="algo")
    mode = right.radio("Mode", ["Free-running", "Step-by-step"],
                       horizontal=True, key="mode")
    kind = "ra" if algo == "Ricart-Agrawala" else "ring"
    get_sim(kind).network.set_step_mode(mode == "Step-by-step")
    live_view(kind)


# ======================= Tab 3: comparison =======================
with tab_compare:
    st.header("Ricart-Agrawala vs Token Ring")
    st.caption("Both algorithms get exactly the same requests, all made at the same "
               "moment, on fresh copies of the 3 ATMs (separate from the live demo).")

    chosen = st.multiselect("Which ATMs withdraw?", NAMES, default=NAMES)

    if st.button("Run both algorithms"):
        requesters = [NAMES.index(name) for name in chosen]
        if not requesters:
            st.warning("Pick at least one ATM.")
        else:
            with st.spinner("Running both algorithms..."):
                st.session_state["comparison"] = {
                    "who": chosen,
                    "ra": run_ricart_agrawala(requesters),
                    "ring": run_token_ring(requesters),
                }

    result = st.session_state.get("comparison")
    if result:
        ra, ring_r = result["ra"], result["ring"]
        st.write(f"Withdrawals from: **{', '.join(result['who'])}** "
                 f"({ra['entries']} critical section entries)")

        left, right = st.columns(2)
        for column, title, r in [(left, "Ricart-Agrawala", ra), (right, "Token Ring", ring_r)]:
            with column.container(border=True):
                st.subheader(title)
                st.metric("Messages per entry", f"{r['per_entry']:.2f}")
                st.write(f"Total messages: **{r['messages']}**")
                st.write(f"Average wait: **{r['avg_wait']:.2f} s**")
                st.write(f"Order: {' → '.join(r['order'])}")
                st.write(f"Final balance: **{r['balance']}** "
                         f"(expected {r['expected_balance']})")
                st.write(f"Max ATMs in the critical section at once: **{r['max_active']}**")

        # Bar chart: starts at 0, value written on each bar
        bars_df = pd.DataFrame({
            "Algorithm": ["Ricart-Agrawala", "Token Ring"],
            "Messages per entry": [ra["per_entry"], ring_r["per_entry"]],
        })
        top = max(bars_df["Messages per entry"].max() * 1.25, 1)
        bars = alt.Chart(bars_df).mark_bar(size=50).encode(
            x=alt.X("Messages per entry:Q", scale=alt.Scale(domain=[0, top], nice=False),
                    title="Messages per critical section entry",
                    axis=alt.Axis(tickMinStep=1, format="d")),
            y=alt.Y("Algorithm:N", title=None, sort=None),
            color=alt.Color("Algorithm:N", legend=None, scale=alt.Scale(
                domain=["Ricart-Agrawala", "Token Ring"],
                range=[MSG_COLORS["REQUEST"], MSG_COLORS["TOKEN"]])),
        )
        labels = bars.mark_text(align="left", dx=6, fontSize=20, fontWeight="bold").encode(
            text=alt.Text("Messages per entry:Q", format=".2f"), color=alt.value(THEMES[is_dark()]["text"]))
        st.altair_chart(style_chart((bars + labels).properties(height=200), 17),
                        use_container_width=True, theme=None)

    st.subheader("Summary table")
    st.table({
        "": ["Messages per entry", "Fault tolerance", "Waiting"],
        "Ricart-Agrawala": [
            "Always 2(N-1) = 4: a REQUEST and a REPLY for each of the other 2 ATMs",
            "No single point of failure, but every ATM must reply, "
            "so one crashed ATM blocks everyone",
            "Waits only for replies (fast if nobody else wants to withdraw). "
            "Served in ticket order, so it is fair",
        ],
        "Token Ring": [
            "Varies: 1 to N-1 token passes per entry (fewer under heavy load, "
            "more when requests are rare)",
            "A lost token or a crashed ATM breaks the ring; "
            "needs token regeneration and ring repair",
            "Waits for the token to arrive, up to N-1 hops even when nobody else "
            "is withdrawing. Served in ring order, not request order",
        ],
    })
    st.caption("Message counts are exact. Wait times are wall-clock and include the "
               "0.3 s each ATM spends in its withdrawal, so they vary a little between runs. "
               "The token starts at ATM 1, which favours it in the ring.")

    # ---------------- Scalability ----------------
    st.divider()
    st.header("Scalability: what happens with more ATMs?")
    st.write(f"Both algorithms are run with N = {', '.join(str(n) for n in SIZES)} ATMs, "
             "in two cases: **heavy load** (all ATMs withdraw at once) and **light load** "
             "(only the last ATM withdraws, which is the worst case for the ring because "
             "the token starts at ATM 1 and has to travel all the way to it).")

    if st.button("Run scalability test"):
        with st.spinner("Running 16 simulations..."):
            st.session_state["scalability"] = run_scalability()

    scal = st.session_state.get("scalability")
    if scal:
        # all runs must still be correct: one ATM at a time, right final balance
        runs = [r for case in scal.values() for algo in case.values() for r in algo.values()]
        if all(r["max_active"] == 1 and r["balance"] == r["expected_balance"] for r in runs):
            st.success(f"All {len(runs)} runs correct: never more than one ATM in the "
                       "critical section, and the final balance was always right.")
        else:
            st.error("A run broke mutual exclusion or lost money!")

        THEORY = "Theory 2(N−1) (dashed)"
        SERIES = ["Ricart-Agrawala", "Token Ring", THEORY]

        def scal_chart(case):
            rows = []
            for n in SIZES:
                rows.append({"N": n, "Series": "Ricart-Agrawala",
                             "Messages per entry": scal[case]["ra"][n]["per_entry"]})
                rows.append({"N": n, "Series": "Token Ring",
                             "Messages per entry": scal[case]["ring"][n]["per_entry"]})
                rows.append({"N": n, "Series": THEORY,
                             "Messages per entry": theory_ricart_agrawala(n)})
            chart = alt.Chart(pd.DataFrame(rows)).encode(
                x=alt.X("N:Q", title="Number of ATMs (N)",
                        axis=alt.Axis(values=SIZES, format="d"), scale=alt.Scale(domain=[2.5, 10.5])),
                y=alt.Y("Messages per entry:Q", scale=alt.Scale(domain=[0, 20]),
                        title="Messages per critical section entry"),
                color=alt.Color("Series:N", title=None, scale=alt.Scale(
                    domain=SERIES, range=[MSG_COLORS["REQUEST"], MSG_COLORS["TOKEN"],
                                          MSG_COLORS["DEFERRED"]]),
                    legend=alt.Legend(orient="top", symbolStrokeWidth=5)),
            ).properties(height=320)
            # measured lines first, then the dashed theory line on top of them
            measured = chart.transform_filter(alt.datum.Series != THEORY).mark_line(
                point=True, strokeWidth=4)
            theory = chart.transform_filter(alt.datum.Series == THEORY).mark_line(
                strokeWidth=4, strokeDash=[10, 8])
            return style_chart(measured + theory)

        left, right = st.columns(2)
        with left:
            st.subheader("Heavy load: all ATMs withdraw")
            st.altair_chart(scal_chart("heavy"), use_container_width=True, theme=None)
        with right:
            st.subheader("Light load: one ATM withdraws")
            st.altair_chart(scal_chart("light"), use_container_width=True, theme=None)

        top = max(SIZES)
        ra3 = scal["heavy"]["ra"][3]["per_entry"]
        ra_top = scal["heavy"]["ra"][top]["per_entry"]
        ring_heavy = scal["heavy"]["ring"][top]["per_entry"]
        ring_light = scal["light"]["ring"][top]["per_entry"]
        takeaway = [
            "**Takeaway**",
            f"- **Ricart-Agrawala** always costs 2(N−1) messages per withdrawal, whatever the load. "
            f"Its line sits exactly on the dashed theory line and climbs steadily "
            f"({ra3:.0f} at N=3, {ra_top:.0f} at N={top}) because every other ATM must be asked every time.",
            f"- **Token Ring, heavy load:** very cheap and almost flat, under 1 message per withdrawal "
            f"({ring_heavy:.2f} at N={top}), because the token is nearly always used by someone.",
            f"- **Token Ring, light load:** up to N−1 token passes for a single withdrawal "
            f"({ring_light:.0f} at N={top}), because the token must travel round to the ATM that wants it. "
            f"Still fewer messages than Ricart-Agrawala, but it also means a long wait.",
            "- **Rule of thumb:** Token Ring wins on messages as N grows, especially under heavy load. "
            "Ricart-Agrawala answers faster when the system is quiet, but its message cost grows with every ATM.",
        ]
        st.info(BLANK_LINE.join(takeaway))


# ======================= Tab 4: crash =======================
def crash_diagram(res, kind, crashed):
    """Network picture of the state after the crash experiment."""
    statuses, notes = [], []
    for n in res["nodes"]:
        if n["crashed"]:
            statuses.append("Crashed")
            notes.append("not responding")
        elif n["done"]:
            statuses.append("Idle")
            notes.append("withdrew")
        else:
            statuses.append("Waiting")
            notes.append(f"{n['replies']}/{n['needed']} OKs" if kind == "ra"
                         else "never got the token")
    if kind == "ra":
        # each waiting ATM keeps asking the dead one, who never answers
        arrows = [{"frm": i, "to": crashed, "label": "REQUEST, no reply",
                   "color": MSG_COLORS["REQUEST"], "dashed": True}
                  for i in range(3) if statuses[i] == "Waiting"]
        return network_svg(NAMES, statuses, notes, arrows=arrows, dark=is_dark())
    path = list(range(crashed))          # edges ATM 1 -> ... -> crashed ATM
    return network_svg(NAMES, statuses, notes, ring_edges=True, ring_path=path,
                       token={"kind": "lost", "node": crashed}, dark=is_dark())


def recovery_diagram(res, crashed):
    """Picture of the final state of one recovery experiment."""
    kind, recovered = res["kind"], res["recovered"]
    unfinished = res["stuck"] if kind == "ra" else res["starved"]
    statuses, notes = [], []
    for n in res["nodes"]:
        if n["crashed"]:
            statuses.append("Crashed")
            notes.append("not responding")
        elif n["name"] in unfinished:
            statuses.append("Waiting")
            notes.append(f"stuck after {n['withdrawals']} withdrawal(s)")
        else:
            statuses.append("Idle")
            notes.append(f"withdrew {n['withdrawals']}×")
    if kind == "ra":
        arrows = []
        if not recovered:             # waiting ATMs keep asking the dead one
            arrows = [{"frm": i, "to": crashed, "label": "REQUEST, no reply",
                       "color": MSG_COLORS["REQUEST"], "dashed": True}
                      for i in range(3) if statuses[i] == "Waiting"]
        return network_svg(NAMES, statuses, notes, arrows=arrows, dark=is_dark())
    if recovered:                     # the repaired ring skips the dead ATM
        maker = [e["by"] for e in res["events"] if e["kind"] == "regenerated"]
        token = {"kind": "at", "node": NAMES.index(maker[0])} if maker else None
        return network_svg(NAMES, statuses, notes, ring_edges=True, skip=crashed,
                           token=token, dark=is_dark())
    return network_svg(NAMES, statuses, notes, ring_edges=True, ring_path=list(range(crashed)),
                       token={"kind": "lost", "node": crashed}, dark=is_dark())


def recovery_panel(res, crashed, title):
    """One panel: diagram, verdict, balance check, detection events and log."""
    kind, recovered = res["kind"], res["recovered"]
    st.subheader(title)
    components.html(recovery_diagram(res, crashed), height=430)

    done = f"{res['completed']} of {res['wanted']} withdrawals completed"
    detected = [e for e in res["events"] if e["kind"] == "detected"]
    if kind == "ra" and recovered:
        who = "; ".join(f"{e['by']} noticed at +{e['at']} s" for e in detected)
        st.success(f"RECOVERED: {NAMES[crashed]} was marked failed and removed ({who}). {done}.")
    elif kind == "ra":
        st.error(f"STUCK: {', '.join(res['stuck'])} wait forever for a REPLY from "
                 f"crashed {NAMES[crashed]}. {done}.")
    elif recovered:
        made = [e for e in res["events"] if e["kind"] == "regenerated"][0]
        st.success(f"RECOVERED: {made['by']} (lowest-id alive ATM) made a new token at "
                   f"+{made['at']} s. Exactly {res['tokens_created']} new token. "
                   f"The ring skips {NAMES[crashed]}. {done}.")
    else:
        st.error(f"TOKEN LOST: it vanished at crashed {NAMES[crashed]}. {done}.")

    ok = res["balance"] == res["expected_balance"] and res["max_active"] <= 1
    st.markdown(f"**Final balance: {res['balance']}** "
                f"(1000 − 100 × {res['completed']} withdrawals = {res['expected_balance']}) "
                + ("✅ correct" if ok else "❌ WRONG"))
    if res["events"]:
        st.table([{"Event": "Failure detected" if e["kind"] == "detected" else "Token regenerated",
                   "By": e["by"], "About": e.get("failed", "new token"),
                   "When (s)": f"{e['at']:.2f}"} for e in res["events"]])
    components.html(log_html(res["log"], show_token=kind == "ring", height=300, follow=False,
                             dark=is_dark(), recovery=True), height=300)


def show_recovery(crashed_name):
    """The 'With recovery' view: no recovery and recovery side by side."""
    if st.button("💥 Crash it and compare with / without recovery"):
        crashed_id = NAMES.index(crashed_name)
        with st.spinner("Watching 4 runs for 6.5 seconds..."):
            with ThreadPoolExecutor(max_workers=4) as pool:      # side by side to save time
                futures = {(kind, rec): pool.submit(run, crashed_id, rec)
                           for kind, run in (("ra", run_ra_scenario), ("ring", run_ring_scenario))
                           for rec in (False, True)}
                st.session_state["crash_rec"] = {
                    "id": crashed_id, **{k: f.result() for k, f in futures.items()}}

    rec = st.session_state.get("crash_rec")
    if not rec:
        return
    for kind, heading in (("ra", "Ricart-Agrawala"), ("ring", "Token Ring")):
        st.header(heading)
        left, right = st.columns(2)
        with left.container(border=True):
            recovery_panel(rec[(kind, False)], rec["id"], "❌ Without recovery")
        with right.container(border=True):
            recovery_panel(rec[(kind, True)], rec["id"], "✅ With recovery")

    st.warning(
        "**Limitation:** a failure detector can only see silence. A *slow* ATM that is "
        "still alive can be wrongly treated as crashed. The others then carry on without it, "
        "and it may enter the critical section at the same time as someone else, which breaks "
        "mutual exclusion. A longer timeout means fewer false alarms but slower recovery. "
        "(`test_recovery.py` shows this happening.)")


with tab_crash:
    st.header("Crash an ATM")
    with_recovery = st.toggle("🛟 With recovery", key="recovery", value=False)
    if with_recovery:
        st.write("One ATM crashes. Each algorithm is run twice, **without** and **with** recovery, "
                 "and every surviving ATM withdraws twice (once at the start, once at +3.5 s). "
                 "**Ricart-Agrawala:** an ATM that gets no REPLY or ACK from a peer within 1 s "
                 "marks it failed, removes it from the group and carries on. "
                 "**Token Ring:** ATMs send heartbeats, the ring skips the dead ATM, and if the "
                 "token is not seen for 1.5 s the lowest-id alive ATM makes a new one.")
    else:
        st.write("One ATM crashes (its thread never runs, so it never answers). "
                 "The other two ATMs try to withdraw. Each algorithm is watched for 2 seconds.")

    crashed_name = st.selectbox("Which ATM crashes?", NAMES, index=2)

    if with_recovery:
        show_recovery(crashed_name)
    else:

        if st.button("💥 Crash it and run both algorithms"):
            crashed_id = NAMES.index(crashed_name)
            with st.spinner("Watching both algorithms for 2 seconds each..."):
                st.session_state["crash"] = {
                    "who": crashed_name,
                    "id": crashed_id,
                    "ra": run_crash_ricart_agrawala(crashed_id),
                    "ring": run_crash_token_ring(crashed_id),
                }

        crash = st.session_state.get("crash")
        if crash:
            ra, ring_r = crash["ra"], crash["ring"]
            left, right = st.columns(2)

            with left.container(border=True):
                st.subheader("Ricart-Agrawala")
                components.html(crash_diagram(ra, "ra", crash["id"]), height=430)
                if ra["starved"]:
                    st.error(f"STUCK: {', '.join(ra['starved'])} wait forever for a REPLY "
                             f"from crashed {crash['who']}. Nobody can withdraw.")
                else:
                    st.success("Everyone finished")
                st.write(f"Balance: **{ra['balance']}**")
                components.html(log_html(ra["log"], height=300, follow=False, dark=is_dark()), height=300)

            with right.container(border=True):
                st.subheader("Token Ring")
                components.html(crash_diagram(ring_r, "ring", crash["id"]), height=430)
                if ring_r["token_lost"]:
                    st.error(f"TOKEN LOST: it was passed to crashed {ring_r['lost_at']} and "
                             "never came back. Nobody can withdraw any more.")
                else:
                    st.success("Token still circulating")
                st.write(f"Balance: **{ring_r['balance']}**")
                components.html(log_html(ring_r["log"], show_token=True, height=300,
                                      follow=False, dark=is_dark()), height=300)

            st.caption("Neither algorithm survives a crash as written. Real systems add "
                       "failure detection (timeouts) and, for Token Ring, token regeneration.")
