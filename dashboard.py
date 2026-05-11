"""
Gap-Time Dashboard
==================
Drop in an Excel file (same schema as the existing pick/stage report) and the
dashboard surfaces every pick→pick, pick→stage and stage→pick gap that is
longer than 5 minutes, with scheduled breaks subtracted out.

Scheduled (unpaid) breaks — subtracted from any gap that overlaps them:
    • 5:20 PM – 5:50 PM   (30 min)
    • 8:40 PM – 9:35 PM   (55 min)
    • 11:55 PM – 12:50 AM (55 min, crosses midnight)

Run:
    pip install streamlit pandas openpyxl
    streamlit run dashboard.py
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st


# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────
GAP_THRESHOLD_MIN = 5.0

# Each break is (start_time, end_time). The 11:55 PM break crosses midnight,
# which is handled by splitting it into two same-day windows.
BREAKS: list[tuple[time, time]] = [
    (time(17, 20), time(17, 50)),
    (time(20, 40), time(21, 35)),
    (time(23, 55), time(23, 59, 59)),
    (time(0,  0),  time(0, 50)),
]

# Two supported workbook layouts:
#
# 1) Wide "report" layout — one row per order, separate pick/stage columns:
WIDE_COLS = {
    "pick_time":  "Pick Completed At",
    "pick_user":  "Picked By",
    "stage_time": "Stage Completed At",
    "stage_user": "Staged By",
}
#
# 2) Long "transaction log" layout — one row per event:
LONG_COLS = {
    "time":   "Transaction Time",
    "type":   "Transaction",        # values like "Order Pick", "Order Stage"
    "user":   "Created By",
}
LONG_PICK_VALUES  = {"order pick", "pick"}
LONG_STAGE_VALUES = {"order stage", "stage"}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _break_windows_for_day(day: datetime) -> list[tuple[datetime, datetime]]:
    """Return concrete datetime windows for the breaks that touch `day`."""
    base = datetime(day.year, day.month, day.day)
    return [(datetime.combine(base, s), datetime.combine(base, e)) for s, e in BREAKS]


def break_overlap_minutes(start: datetime, end: datetime) -> float:
    """Total minutes of [start, end] that fall inside any scheduled break."""
    if end <= start:
        return 0.0
    total = 0.0
    # Build break windows for every day the gap touches (plus the day before
    # to capture a 23:55 break that started the previous calendar day).
    days = set()
    cur = start.date()
    while cur <= end.date():
        days.add(cur)
        cur = cur + timedelta(days=1)
    days.add(start.date() - timedelta(days=1))

    for d in days:
        for b_start, b_end in _break_windows_for_day(datetime(d.year, d.month, d.day)):
            lo = max(start, b_start)
            hi = min(end, b_end)
            if hi > lo:
                total += (hi - lo).total_seconds() / 60.0
    return total


def adjusted_minutes(start: datetime, end: datetime) -> tuple[float, float, float]:
    """Return (raw_min, break_min, adjusted_min) for the interval."""
    raw = (end - start).total_seconds() / 60.0
    brk = break_overlap_minutes(start, end)
    return raw, brk, max(0.0, raw - brk)


def _parse_ts(series: pd.Series) -> pd.Series:
    """Coerce a column of mixed date strings / Excel datetimes to datetime."""
    return pd.to_datetime(series, errors="coerce")


# ──────────────────────────────────────────────────────────────────────────────
# Core analysis
# ──────────────────────────────────────────────────────────────────────────────
def load_events(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pull pick + stage events out of the raw report DataFrame.

    Auto-detects the wide pick/stage report layout vs. the long transaction-log
    layout (one row per event with a `Transaction` column).
    """
    cols = set(df.columns)

    # ── Long / transaction-log layout ────────────────────────────────────────
    if {LONG_COLS["time"], LONG_COLS["type"], LONG_COLS["user"]}.issubset(cols):
        t = df[LONG_COLS["type"]].astype(str).str.strip().str.lower()
        base = pd.DataFrame({
            "time": _parse_ts(df[LONG_COLS["time"]]),
            "user": df[LONG_COLS["user"]].astype(str).str.strip(),
            "type": t,
        }).dropna(subset=["time"])
        base = base[base["user"].ne("") & base["user"].str.lower().ne("nan")]

        picks = base[base["type"].isin(LONG_PICK_VALUES)][["time", "user"]]
        stages = base[base["type"].isin(LONG_STAGE_VALUES)][["time", "user"]]
        return picks.sort_values("time"), stages.sort_values("time")

    # ── Wide pick/stage report layout ────────────────────────────────────────
    if {WIDE_COLS["pick_time"], WIDE_COLS["pick_user"],
        WIDE_COLS["stage_time"], WIDE_COLS["stage_user"]}.issubset(cols):
        picks = pd.DataFrame({
            "time": _parse_ts(df[WIDE_COLS["pick_time"]]),
            "user": df[WIDE_COLS["pick_user"]].astype(str).str.strip(),
        }).dropna(subset=["time"])
        picks = picks[picks["user"].ne("") & picks["user"].str.lower().ne("nan")]

        stages = pd.DataFrame({
            "time": _parse_ts(df[WIDE_COLS["stage_time"]]),
            "user": df[WIDE_COLS["stage_user"]].astype(str).str.strip(),
        }).dropna(subset=["time"])
        stages = stages[stages["user"].ne("") & stages["user"].str.lower().ne("nan")]
        return picks.sort_values("time"), stages.sort_values("time")

    raise ValueError(
        "Couldn't detect a supported layout. Expected either:\n"
        f"  • Long format columns: {list(LONG_COLS.values())}\n"
        f"  • Wide format columns: {list(WIDE_COLS.values())}"
    )


def compute_gaps(picks: pd.DataFrame, stages: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build pick→pick, pick→stage and stage→pick gap tables (>5 min, break-adjusted)."""
    pp_rows: list[dict] = []   # pick → pick
    ps_rows: list[dict] = []   # pick → stage
    sp_rows: list[dict] = []   # stage → pick

    # Pick → Pick (per user)
    for user, grp in picks.groupby("user"):
        times = grp["time"].sort_values().tolist()
        for a, b in zip(times, times[1:]):
            raw, brk, adj = adjusted_minutes(a, b)
            if adj > GAP_THRESHOLD_MIN:
                pp_rows.append({
                    "User": user, "From": a, "To": b,
                    "Raw Min": round(raw, 1),
                    "Break Min": round(brk, 1),
                    "Adj Min": round(adj, 1),
                })

    # Pick → Stage and Stage → Pick (per user, by interleaved timeline)
    events_by_user: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for _, r in picks.iterrows():
        events_by_user[r["user"]].append((r["time"], "pick"))
    for _, r in stages.iterrows():
        events_by_user[r["user"]].append((r["time"], "stage"))

    for user, evs in events_by_user.items():
        evs.sort(key=lambda x: x[0])
        last_pick: datetime | None = None
        last_stage: datetime | None = None
        for ts, kind in evs:
            if kind == "stage" and last_pick is not None:
                raw, brk, adj = adjusted_minutes(last_pick, ts)
                if adj > GAP_THRESHOLD_MIN:
                    ps_rows.append({
                        "User": user, "Pick Time": last_pick, "Stage Time": ts,
                        "Raw Min": round(raw, 1),
                        "Break Min": round(brk, 1),
                        "Adj Min": round(adj, 1),
                    })
            elif kind == "pick" and last_stage is not None:
                raw, brk, adj = adjusted_minutes(last_stage, ts)
                if adj > GAP_THRESHOLD_MIN:
                    sp_rows.append({
                        "User": user, "Stage Time": last_stage, "Pick Time": ts,
                        "Raw Min": round(raw, 1),
                        "Break Min": round(brk, 1),
                        "Adj Min": round(adj, 1),
                    })
            if kind == "pick":
                last_pick = ts
            else:
                last_stage = ts

    return {
        "pick_to_pick":  pd.DataFrame(pp_rows),
        "pick_to_stage": pd.DataFrame(ps_rows),
        "stage_to_pick": pd.DataFrame(sp_rows),
    }


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["User", "Gaps", "Total Adj Min", "Avg Adj Min", "Max Adj Min"])
    g = df.groupby("User")["Adj Min"]
    return (
        pd.DataFrame({
            "Gaps": g.size(),
            "Total Adj Min": g.sum().round(1),
            "Avg Adj Min": g.mean().round(1),
            "Max Adj Min": g.max().round(1),
        })
        .reset_index()
        .sort_values("Total Adj Min", ascending=False)
    )


# ──────────────────────────────────────────────────────────────────────────────
# Streamlit UI
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gap-Time Dashboard", layout="wide")
st.title("Pick / Stage Gap-Time Dashboard")
st.caption(
    "Drop an Excel report below. Gaps over 5 minutes are listed for "
    "pick→pick, pick→stage and stage→pick transitions. "
    "Scheduled breaks (5:20–5:50 PM, 8:40–9:35 PM, 11:55 PM–12:50 AM) are subtracted automatically."
)

uploaded = st.file_uploader("Drop an Excel file here", type=["xlsx", "xlsm", "xls"])

if not uploaded:
    st.info("Awaiting an Excel upload…")
    st.stop()

try:
    raw = pd.read_excel(uploaded)
except Exception as e:  # noqa: BLE001
    st.error(f"Could not read workbook: {e}")
    st.stop()

try:
    picks, stages = load_events(raw)
except ValueError as e:
    st.error(str(e))
    st.write("Columns found:", list(raw.columns))
    st.stop()

if picks.empty and stages.empty:
    st.warning("No pick or stage events found in the workbook.")
    st.stop()

gaps = compute_gaps(picks, stages)

# ── Top-line metrics ─────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Picks parsed", f"{len(picks):,}")
c2.metric("Stages parsed", f"{len(stages):,}")
c3.metric("Users", f"{picks['user'].nunique():,}")
total_gaps = sum(len(v) for v in gaps.values())
c4.metric("Gaps > 5 min", f"{total_gaps:,}")

# ── Optional user filter ─────────────────────────────────────────────────────
all_users = sorted(set(picks["user"]).union(stages["user"]))
selected = st.multiselect("Filter by user (optional)", all_users)

def _apply_filter(df: pd.DataFrame) -> pd.DataFrame:
    if not selected or df.empty:
        return df
    return df[df["User"].isin(selected)]

pp = _apply_filter(gaps["pick_to_pick"])
ps = _apply_filter(gaps["pick_to_stage"])
sp = _apply_filter(gaps["stage_to_pick"])

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["Pick → Pick", "Pick → Stage", "Stage → Pick", "Summary by User"]
)

def _render(df: pd.DataFrame, label: str) -> None:
    if df.empty:
        st.success(f"No {label} gaps over {GAP_THRESHOLD_MIN:.0f} minutes.")
        return
    st.write(f"**{len(df):,} gaps** over {GAP_THRESHOLD_MIN:.0f} minutes (after breaks).")
    st.dataframe(
        df.sort_values("Adj Min", ascending=False).reset_index(drop=True),
        use_container_width=True,
        height=500,
    )
    st.download_button(
        f"Download {label} CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"{label.replace(' ', '_').lower()}_gaps.csv",
        mime="text/csv",
    )

with tab1:
    _render(pp, "Pick to Pick")
with tab2:
    _render(ps, "Pick to Stage")
with tab3:
    _render(sp, "Stage to Pick")

with tab4:
    st.subheader("Pick → Pick")
    st.dataframe(summarize(pp), use_container_width=True)
    st.subheader("Pick → Stage")
    st.dataframe(summarize(ps), use_container_width=True)
    st.subheader("Stage → Pick")
    st.dataframe(summarize(sp), use_container_width=True)
