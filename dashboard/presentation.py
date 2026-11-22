"""Presentation mode: the dashboard as a course project presentation.

Turned on from the sidebar (admins only) or with a link such as `?present=1&team=Joni%2C%20Ahmed`. It
- brands the app with the project title, subtitle, team, logo and accent colour (the Customize panel, which is
  hidden while the guided tour runs),
- gives assets plain names ("Engine 07" instead of "FD001-test-071"),
- hides the developer panels (MQTT, auto-refresh, model internals in the tables) and the Streamlit chrome,
- runs a guided tour: Next / Back moves the app itself to the view, asset, tab and replay position of each step,
  from the problem and the users through the architecture, the live demo, testing and results to lessons learned.

Everything lives in the viewer's session, so one presenter never changes what other users see. The data is the
recorded replay, which works with nothing else running.
"""
import html
import json
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

import data_source as ds

VIEWS = ["Problem", "Users", "Requirements", "Architecture", "Fleet", "Asset detail", "Technician view",
         "Mobile app", "Testing", "Results", "Lessons learned"]
TESTS_DIR = ds.ROOT / "tests"
METRICS_FILE = ds.ROOT / "models" / "cmapss_metrics.json"
# the XIOS3 technician app on CloudBackend (xios3/) and its Android test wrapper (mobile/)
MOBILE_APP_URL = "https://jodu-2-pdm-technician.cloudbackend.cloud"
ALL_TYPES = "All types"          # the fleet view's "no type filter" value

DEFAULT_LESSONS = {
    "went_well": "Separating ingestion from the transport: the same code scores MQTT, CSV and recorded data.\n"
                 "Testing against a real MQTT broker found problems that mocks would have hidden.\n"
                 "Comparing the model with simple baselines kept the results honest.",
    "improve": "Get real sensor data early: recorded datasets hide the messiness of real equipment.\n"
               "Calibrate the uncertainty range: the 80% interval covers 73–80% of cases.\n"
               "Collect more than one run-to-failure for the motor, so its estimate can be validated.\n"
               "Plan the database for scale: one SQLite file is fine for a demo, not for a large fleet.",
}
DEFAULTS = {
    "customer": "Predictive Maintenance for IoT",
    "tagline": "Course project: from sensor data to a finished repair",
    "accent": "#2a78d6",
    "logo": "",
    "site": "",
    "cta": "Thank you. Questions?",
    "team": "",
    **DEFAULT_LESSONS,
}
# plain nouns for the asset types; any other registered type falls back to its registry name
TYPE_NOUNS = {"turbofan_engine": "Engine", "brushed_dc_motor": "Drive motor", "li_ion_battery": "Battery pack"}
PROFILE_FIELDS = ["customer", "tagline", "team", "accent", "logo", "site", "cta", "went_well", "improve"]
NEW_PROFILE = "➕ New profile"
QUERY_KEYS = {"customer": "customer", "tagline": "tagline", "team": "team",
              "accent": "accent", "logo": "logo", "site": "site"}


@dataclass(frozen=True)
class Step:
    title: str
    text: str
    view: str
    fleet_pct: Optional[int] = None       # fleet snapshot to show (percent of each asset's life)
    fleet_play: bool = False              # replay the fleet from fleet_pct
    asset_play: bool = False              # replay the focus asset from its first reading
    tab: Optional[str] = None             # which tab of the view opens


FLEET_TABS = ["📋 Maintenance priority", "🚨 Open alerts", "🧠 Models & data"]
ASSET_TABS = ["📊 Health Overview", "🔍 Sensor Inspector", "🚨 Alerts & Actions", "🧠 Model & Data"]

TOUR = [
    # 1. the problem
    Step("The problem",
         "Machines fail without warning, and fixed maintenance intervals replace parts that still had life left. "
         "Our goal: predict failures from sensor data early enough to plan the repair.",
         "Problem"),
    # 2. the users
    Step("Who benefits",
         "Maintenance planners, technicians and operations managers each get what they need from the same data.",
         "Users"),
    # 3. the solution
    Step("Requirements and what we built",
         "What the system had to do, and where in this demo you will see each requirement met.",
         "Requirements"),
    # 4. the technical architecture
    Step("How the system works",
         "Sensors publish readings over MQTT. An ingestion service validates, stores and scores them, the dashboard "
         "shows the result, and a work order closes the loop to the technician.",
         "Architecture"),
    # 5. the demonstration
    Step("Demo: from sensor readings to one health score",
         "Each asset's health channels are compared with a baseline from its own first, healthy readings. The "
         "deviations become a health index from 0 to 100 and a status. This is the fleet early in its life.",
         "Fleet", fleet_pct=15, tab=FLEET_TABS[0]),
    Step("Demo: replaying recorded run-to-failure data",
         "No real machines are connected, so we replay recorded data: NASA C-MAPSS turbofan engines and a brushed "
         "DC motor, scored as if they were live. Watch the assets degrade.",
         "Fleet", fleet_pct=15, fleet_play=True, tab=FLEET_TABS[0]),
    Step("Demo: ranking by urgency",
         "A learned model estimates each engine's remaining useful life with an 80% prediction interval. Assets are "
         "ranked by status, then by the shortest remaining life.",
         "Fleet", fleet_pct=100, tab=FLEET_TABS[0]),
    Step("Demo: alerts with a suggested action",
         "Each status change raises an alert that says what was detected and what to do about it.",
         "Fleet", fleet_pct=100, tab=FLEET_TABS[1]),
    Step("Demo: one engine, from new to failure",
         "The health index falls as the engine wears. The remaining-life estimate and its interval follow the "
         "actual remaining life, which we know because the data was recorded to failure.",
         "Asset detail", asset_play=True, tab=ASSET_TABS[0]),
    Step("Demo: from alert to work order",
         "An alert becomes a work order with one click. It goes to the technician page, or as a web request to an "
         "external maintenance system (we used Node-RED). Dispatching is a real write to the shared database.",
         "Asset detail", tab=ASSET_TABS[2]),
    Step("Demo: the technician's page",
         "A maintenance login sees only the open work orders, most urgent first, and marks them started, completed "
         "or rejected.",
         "Technician view"),
    Step("Demo: closing the loop",
         "The technician's update comes back to the alert, so every step from sensor reading to finished repair is "
         "on record.",
         "Asset detail", tab=ASSET_TABS[2]),
    Step("Demo: the same data as a mobile app",
         "We ported the technician workflow to XIOS/3 on CloudBackend: an exporter turns our database into XML, the "
         "app keeps each user's work orders in their own CloudBackend storage, adapts to phone screens, and runs on "
         "Android inside a Capacitor wrapper.",
         "Mobile app"),
    # 6. testing
    Step("Testing: how we validated the system",
         "Automated tests for every part of the pipeline, including a real MQTT broker and its security setup.",
         "Testing"),
    Step("Testing: how accurate is the model?",
         "Tested on engines the model never saw, and compared with two simple baselines.",
         "Results"),
    # 7. lessons learned
    Step("Lessons learned",
         "What worked, what we would do differently, and what we would build next.",
         "Lessons learned"),
]


# ---------------------------------------------------------------- state
def init() -> None:
    """Reads the presentation settings from the link once per session, and keeps them while the panel is hidden."""
    ss = st.session_state
    for key in [k for k in ss if (k.startswith("brand_") or k.startswith("noun_") or k == "profile_pick")
                and k != "brand_logo_file"]:
        ss[key] = ss[key]               # a widget's value would otherwise be dropped on a run that does not draw it
    if ss.get("_present_init"):
        return
    ss["_present_init"] = True
    params = st.query_params
    ss.setdefault("present", params.get("present", "").lower() in ("1", "true", "yes"))
    for field, query in QUERY_KEYS.items():
        ss.setdefault(f"brand_{field}", params.get(query) or DEFAULTS[field])
    for field in ("cta", "went_well", "improve"):
        ss.setdefault(f"brand_{field}", DEFAULTS[field])
    accent = "#" + ss["brand_accent"].lstrip("#")         # a link may leave out the "#" (it must be escaped there)
    ss["brand_accent"] = accent if _valid_color(accent) else DEFAULTS["accent"]


def active() -> bool:
    return bool(st.session_state.get("present"))


def views() -> list:
    return VIEWS


def tour() -> list:
    return TOUR


def brand(field: str) -> str:
    return st.session_state.get(f"brand_{field}") or DEFAULTS.get(field, "")


def _valid_color(value: str) -> bool:
    v = (value or "").lstrip("#")
    return len(v) == 6 and all(c in "0123456789abcdefABCDEF" for c in v)


def type_noun(type_id: str) -> str:
    return st.session_state.get(f"noun_{type_id}") or TYPE_NOUNS.get(type_id) or ds.registry.get_type(type_id).name


def labels(fleet: ds.Fleet) -> dict:
    """{asset_id: plain name}: the asset type's noun and a number, in the order of the ids within each type."""
    out = {}
    for type_id, part in fleet.assets.sort_values("asset_id").groupby("type_id", sort=True):
        noun = type_noun(type_id)
        ids = list(part["asset_id"])
        for i, asset_id in enumerate(ids, start=1):
            out[asset_id] = noun if len(ids) == 1 else f"{noun} {i:02d}"
    return out


def label(fleet: ds.Fleet, asset_id: str) -> str:
    return labels(fleet).get(asset_id, asset_id)


# ---------------------------------------------------------------- presentation profiles
def _profiles() -> dict:
    """{project title: settings} saved in this session; switch between them, e.g. one per course or audience."""
    return st.session_state.setdefault("profiles", {})


def _current_profile() -> dict:
    ss = st.session_state
    return {**{f: brand(f) for f in PROFILE_FIELDS},
            "nouns": {k[len("noun_"):]: v for k, v in ss.items() if k.startswith("noun_") and v},
            "logo_bytes": ss.get("brand_logo_bytes")}


def save_profile() -> None:
    name = brand("customer").strip() or DEFAULTS["customer"]
    _profiles()[name] = _current_profile()
    st.session_state["profile_pick"] = name
    st.session_state["_profile_saved"] = name


def load_profile() -> None:
    """Applies the profile picked in the switcher (a callback, so it runs before the fields are drawn)."""
    ss = st.session_state
    pick = ss.get("profile_pick")
    profile = _profiles().get(pick) if pick != NEW_PROFILE else {
        **DEFAULTS, "customer": "", "nouns": {}, "logo_bytes": None}
    if profile is None:
        return
    for f in PROFILE_FIELDS:
        ss[f"brand_{f}"] = profile.get(f, DEFAULTS[f])
    ss["brand_logo_bytes"] = profile.get("logo_bytes")
    for key in [k for k in ss if k.startswith("noun_")]:
        del ss[key]
    for type_id, noun in (profile.get("nouns") or {}).items():
        ss[f"noun_{type_id}"] = noun
    _sync_link()


def _logo_uploaded() -> None:
    f = st.session_state.get("brand_logo_file")
    st.session_state["brand_logo_bytes"] = f.getvalue() if f is not None else None


def export_profiles() -> str:
    import base64
    import json
    out = {}
    for name, p in _profiles().items():
        p = dict(p)
        p["logo_bytes"] = base64.b64encode(p["logo_bytes"]).decode() if p.get("logo_bytes") else None
        out[name] = p
    return json.dumps(out, indent=2)


def import_profiles() -> None:
    """Adds the profiles of an uploaded file (from Download profiles) to this session."""
    import base64
    import json
    f = st.session_state.get("profiles_file")
    if f is None:
        return
    try:
        data = json.loads(f.getvalue())
        for name, p in data.items():
            if not isinstance(p, dict):
                continue
            p = {k: p[k] for k in [*PROFILE_FIELDS, "nouns", "logo_bytes"] if k in p}
            if p.get("logo_bytes"):
                p["logo_bytes"] = base64.b64decode(p["logo_bytes"])
            if p.get("accent") and not _valid_color(p["accent"]):
                p["accent"] = DEFAULTS["accent"]
            _profiles()[str(name)] = p
        st.session_state["_profile_saved"] = f"{len(data)} profile(s) loaded"
    except (ValueError, TypeError, AttributeError):
        st.session_state["_profile_saved"] = "That file is not a profiles file."


# ---------------------------------------------------------------- sidebar
def _sync_link() -> None:
    """Keeps the address bar a shareable link to this presentation."""
    if active():
        st.query_params.update({"present": "1", **{q: brand(f) for f, q in QUERY_KEYS.items()
                                                   if brand(f) and brand(f) != DEFAULTS[f]}})
    else:
        for key in ["present", *QUERY_KEYS.values()]:
            st.query_params.pop(key, None)
        st.session_state.pop("tour_step", None)


def sidebar(fleet: ds.Fleet) -> None:
    """The on/off switch and, while on, the tour button, or the profile switcher and Customize panel between tours."""
    st.sidebar.toggle("🎤 Presentation mode", key="present", on_change=_sync_link,
                      help="A clean, branded layout and a guided tour for the course presentation.")
    if not active():
        return
    if st.session_state.get("tour_step") is not None:
        return                            # nothing to customize while presenting: the tour card has the controls
    st.sidebar.button("▶ Start guided tour", key="tour_start", type="primary", width="stretch",
                      on_click=go_to, args=(0, fleet))
    if not _profiles():                   # the settings the link opened with are the first profile
        _profiles()[brand("customer")] = _current_profile()
    names = [*_profiles(), NEW_PROFILE]
    if st.session_state.get("profile_pick") not in names:
        st.session_state["profile_pick"] = names[0]
    st.sidebar.selectbox("Profile", names, key="profile_pick", on_change=load_profile,
                         help="Switch between the profiles you saved; the whole app follows.")
    with st.sidebar.expander("🎨 Customize this presentation", expanded=False):
        st.caption("Changes show immediately. Save to switch back to this profile later. "
                   "This panel is hidden while the guided tour runs.")
        st.text_input("Project title", key="brand_customer", on_change=_sync_link)
        st.text_input("Subtitle", key="brand_tagline", on_change=_sync_link)
        st.text_input("Team members", key="brand_team", on_change=_sync_link, placeholder="e.g. Joni, Ahmed, ...")
        st.text_input("Course and university (optional)", key="brand_site", on_change=_sync_link,
                      placeholder="e.g. IoT project course, University of ...")
        st.color_picker("Accent colour (e.g. your university's)", key="brand_accent", on_change=_sync_link)
        st.text_input("Logo URL (optional)", key="brand_logo", on_change=_sync_link,
                      placeholder="https://.../logo.png")
        st.file_uploader("...or upload a logo", type=["png", "jpg", "jpeg", "svg", "webp"], key="brand_logo_file",
                         on_change=_logo_uploaded)
        st.markdown("**Asset names**")
        for type_id in sorted(fleet.assets["type_id"].unique()):
            st.session_state.setdefault(f"noun_{type_id}", type_noun(type_id))
            st.text_input(ds.registry.get_type(type_id).name, key=f"noun_{type_id}")
        st.text_area("Closing line", key="brand_cta", height=90)
        st.text_area("Lessons learned: what went well (one per line)", key="brand_went_well", height=120)
        st.text_area("Lessons learned: what we would improve (one per line)", key="brand_improve", height=140)
        st.button("💾 Save profile", key="profile_save", width="stretch", type="primary", on_click=save_profile)
        if "_profile_saved" in st.session_state:
            st.caption(f"Saved: {st.session_state.pop('_profile_saved')}")
        st.markdown("**All profiles**")
        st.caption("Profiles last while this browser tab is open. Download them to reuse in another session.")
        st.download_button("⬇ Download profiles", export_profiles(), file_name="presentation_profiles.json",
                           mime="application/json", key="profiles_download", width="stretch",
                           disabled=not _profiles())
        st.file_uploader("Load profiles", type=["json"], key="profiles_file", on_change=import_profiles)
        base = getattr(st.context, "url", "") or ""
        st.caption("Link that opens this presentation (an uploaded logo is not part of it):")
        st.code(base.split("?")[0] + "?" + urlencode({"present": 1, **{q: brand(f) for f, q in QUERY_KEYS.items()
                                                                          if brand(f) != DEFAULTS[f]}}),
                language=None, wrap_lines=True)


def apply_styles() -> None:
    """Hides the Streamlit toolbar and footer, uses the accent colour, enlarges the headline numbers."""
    accent = brand("accent") if _valid_color(brand("accent")) else DEFAULTS["accent"]
    st.html(f"""<style>
    [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stAppDeployButton"],
    [data-testid="stMainMenu"], footer {{ display: none !important; }}
    header[data-testid="stHeader"] {{ background: transparent; }}
    [data-testid="stMetricValue"] {{ font-size: 2.3rem; font-weight: 700; }}
    [data-testid="stMetricLabel"] p {{ font-size: 1rem; }}
    .stButton button[kind="primary"] {{ background: {accent}; border-color: {accent}; }}
    .pm-banner {{ border-left: 6px solid {accent}; padding: 0.2rem 0 0.2rem 1rem; margin-bottom: 0.6rem; }}
    .pm-banner h1 {{ margin: 0; padding: 0; font-size: 2.1rem; }}
    .pm-banner p {{ margin: 0; opacity: 0.75; font-size: 1.1rem; }}
    .pm-step {{ color: {accent}; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
                font-size: 0.8rem; }}
    .pm-card {{ border-top: 4px solid {accent}; padding-top: 0.6rem; }}
    </style>""")


def banner() -> None:
    """The logo, project title, subtitle and team at the top of every page."""
    logo = st.session_state.get("brand_logo_bytes") or brand("logo")
    site = f" · {html.escape(brand('site'))}" if brand("site") else ""
    team = f'<p>{html.escape(brand("team"))}</p>' if brand("team") else ""
    text = (f'<div class="pm-banner"><h1>{html.escape(brand("customer"))}</h1>'
            f'<p>{html.escape(brand("tagline"))}{site}</p>{team}</div>')
    if logo:
        left, right = st.columns([1, 9], vertical_alignment="center")
        try:
            left.image(logo, width="stretch")
        except Exception:                 # an unreachable or broken logo must never break the talk
            pass
        right.html(text)
    else:
        st.html(text)


# ---------------------------------------------------------------- tour
def focus_asset(fleet: ds.Fleet) -> str:
    """The asset the tour opens: the most urgent one that has a remaining-life estimate with a range."""
    snap = ds.snapshot(fleet, 1.0)
    snap = snap[snap["status"] != "Learning"]
    with_range = snap[snap["rul_low"].notna() & snap["rul_high"].notna() & (snap["status"] != "Failed")]
    pick = with_range if len(with_range) else snap
    return pick["asset_id"].iloc[0] if len(pick) else fleet.assets["asset_id"].iloc[0]


def go_to(i: int, fleet: ds.Fleet) -> None:
    """Moves the app to tour step i (a button callback, so it runs before any widget is drawn)."""
    ss = st.session_state
    step = tour()[i]
    ss["tour_step"] = i
    ss["view"] = step.view
    ss["fleet_type"] = ss["_fleet_type"] = ALL_TYPES
    ss["fleet_playing"] = step.fleet_play
    if step.fleet_play:
        ss["fleet_step"] = ss["_fleet_step"] = 5
    if step.fleet_pct is not None:
        ss["fleet_pct"] = ss["_fleet_pct"] = step.fleet_pct
    if step.view == "Asset detail":
        asset_id = ss.get("_tour_asset") or focus_asset(fleet)
        ss["_tour_asset"] = asset_id
        ss["selected_asset"] = asset_id
        ss[f"playing_{asset_id}"] = step.asset_play
        if step.asset_play:
            ss[f"pos_{asset_id}"] = 1
            ss["replay_step"] = 5
        else:
            ss.pop(f"pos_{asset_id}", None)        # the asset view then opens at its latest reading
    ss["tour_tab"] = step.tab
    ss["_tour_visit"] = ss.get("_tour_visit", 0) + 1


def end_tour() -> None:
    st.session_state.pop("tour_step", None)
    st.session_state.pop("tour_tab", None)


def tab() -> tuple:
    """(the tab the current tour step opens, a widget key unique to that visit), or (None, None) outside the tour.

    A tab bar keeps the tab the viewer clicked; a new key per step makes it open on the step's tab again.
    """
    if st.session_state.get("tour_step") is None:
        return None, None
    return st.session_state.get("tour_tab"), f"tour{st.session_state.get('_tour_visit', 0)}"


def tour_card(fleet: ds.Fleet) -> None:
    """The current step's talking point and the Back / Next buttons, above the page it explains."""
    i = st.session_state.get("tour_step")
    if i is None or i >= len(tour()):
        return
    step = tour()[i]
    with st.container(border=True):
        st.html(f'<div class="pm-step">Step {i + 1} of {len(tour())}</div>')
        st.markdown(f"#### {step.title}\n{step.text}")
        back, nxt, end, _ = st.columns([1, 1, 1, 4])
        back.button("◀ Back", key="tour_back", width="stretch", disabled=i == 0, on_click=go_to, args=(i - 1, fleet))
        if i + 1 < len(tour()):
            nxt.button("Next ▶", key="tour_next", type="primary", width="stretch", on_click=go_to, args=(i + 1, fleet))
        end.button("End tour", key="tour_end", width="stretch", on_click=end_tour)


# ---------------------------------------------------------------- course presentation pages
def page(view: str, fleet: ds.Fleet) -> None:
    """Draws one of presentation mode's own pages (the views that are not the dashboard itself)."""
    {"Problem": intro_page, "Users": users_page, "Requirements": requirements_page,
     "Architecture": architecture_page, "Mobile app": mobile_page, "Testing": testing_page, "Results": results_page,
     "Lessons learned": lessons_page}[view](fleet)


def _cards(cards: list) -> None:
    for col, (title, text) in zip(st.columns(len(cards)), cards):
        with col:
            st.html(f'<div class="pm-card"><h4>{html.escape(title)}</h4><p>{html.escape(text)}</p></div>')


def intro_page(fleet: ds.Fleet) -> None:
    st.title("The problem")
    _cards([
        ("💥 Unplanned failures", "A machine that breaks during operation stops production, and the repair is "
                                 "rushed and expensive."),
        ("📅 Fixed intervals waste life", "Maintaining on a fixed schedule replaces many parts that still had a "
                                         "long life left, and still misses some failures."),
        ("📈 The data is already there", "Machines carry sensors. Their readings drift as a part wears, long "
                                        "before it fails."),
    ])
    st.markdown("---")
    st.markdown("### Our goal")
    st.markdown(
        "Turn sensor data from any kind of equipment into:\n"
        "1. a **health score** and a status anyone can read,\n"
        "2. an estimate of the **remaining useful life**, with an honest uncertainty range,\n"
        "3. **alerts** with a suggested action, and\n"
        "4. a **work order** that reaches the technician and reports back when the repair is done.")
    n = fleet.assets.groupby("type_id").size()
    st.caption("Demo fleet: " + ", ".join(f"{count} × {type_noun(t).lower()}" for t, count in n.items())
               + ", from public run-to-failure datasets.")


def architecture_page(fleet: ds.Fleet) -> None:
    st.title("How the system works")
    accent = brand("accent") if _valid_color(brand("accent")) else DEFAULTS["accent"]
    st.graphviz_chart(f"""digraph {{
        rankdir=LR; bgcolor="transparent"; nodesep=0.35; ranksep=0.45;
        node [shape=box, style="rounded,filled", fillcolor="#ffffff", color="{accent}", penwidth=2,
              fontname="Helvetica", fontsize=12, margin="0.18,0.1"];
        edge [color="#888888", fontname="Helvetica", fontsize=10, fontcolor="#666666"];
        dev [label="Sensors / gateway\n(simulated from\nrecorded runs)"];
        broker [label="MQTT broker\n(TLS, one login\nper device)"];
        ingest [label="Ingestion service\nvalidate · store ·\nscore · alert"];
        db [label="Database\n(asset-agnostic)", shape=cylinder];
        dash [label="Dashboard\nfleet · asset ·\nwork orders"];
        tech [label="Technician page\nor external CMMS\n(Node-RED)"];
        dev -> broker [label="readings"]; broker -> ingest; ingest -> db; db -> dash;
        dash -> tech [label="work order"]; tech -> db [label="status", style=dashed];
    }}""", width="stretch")
    _cards([
        ("🩺 Health index", "Each health channel is compared with the asset's own healthy baseline from its first "
                           "readings. The deviations become a 0–100 score; a status changes only after it holds for "
                           "a few readings."),
        ("⏳ Remaining useful life", "A gradient-boosted model trained on run-to-failure engines, using only past "
                                    "readings, gives a point estimate and an 80% prediction interval."),
        ("🧩 Any equipment", "Channels, units, limits and thresholds of each asset type live in one registry. A new "
                            "type needs no dashboard changes."),
    ])


def mobile_page(fleet: ds.Fleet) -> None:
    """The technician workflow ported to a XIOS/3 app on CloudBackend, and wrapped as an Android app."""
    st.title("The mobile technician app")
    st.markdown("The fleet, alerts and work orders also run as a **XIOS/3** application on the **CloudBackend** "
                "platform: XML views and processes, hosted and served by CloudBackend, with its own sign-in and "
                "per-user storage. It works in any browser and, wrapped with Capacitor, as an Android app.")
    accent = brand("accent") if _valid_color(brand("accent")) else DEFAULTS["accent"]
    st.graphviz_chart(f"""digraph {{
        rankdir=LR; bgcolor="transparent"; nodesep=0.35; ranksep=0.45;
        node [shape=box, style="rounded,filled", fillcolor="#ffffff", color="{accent}", penwidth=2,
              fontname="Helvetica", fontsize=12, margin="0.18,0.1"];
        edge [color="#888888", fontname="Helvetica", fontsize=10, fontcolor="#666666"];
        db [label="maintenance.db\n(this pipeline)", shape=cylinder];
        exp [label="Exporter\nexport_xios3.py"];
        xml [label="XML documents\nfleet · alerts ·\nhealth history"];
        cbe [label="CloudBackend\nXIOS/3 app\n+ sign-in"];
        home [label="Each user's\nwork orders\n(home://)", shape=cylinder];
        phone [label="Browser or\nAndroid app\n(Capacitor)"];
        db -> exp -> xml; xml -> cbe [label="upload"]; cbe -> home [label="save", dir=both];
        cbe -> phone [label="HTTPS"];
    }}""", width="stretch")
    _cards([
        ("📄 Data as XML", "The exporter writes the fleet in priority order, every alert and each asset's health "
                          "history as small XML documents. The app binds its grids and its health chart straight "
                          "to them."),
        ("🔐 Sign-in and storage", "CloudBackend's own login comes first. Work orders are dispatched from an alert, "
                                  "started, completed or rejected, and saved in the signed-in user's storage."),
        ("📱 Phone ready", "One view adapts to the screen: on a phone each tab shows its list first and the "
                          "detail after a tap, with fewer columns. A Capacitor wrapper turns it into an Android app."),
    ])
    st.markdown("---")
    st.markdown(f"**Try it:** [{MOBILE_APP_URL}]({MOBILE_APP_URL}) (needs a CloudBackend account). "
                "The code is in `xios3/` and `mobile/` of this repository.")
    st.caption("Built with the CloudBackend developer docs and plugin: every component and operation was checked "
               "against the documentation, and the package against the plugin's linter, before each deploy.")


def _metrics() -> dict:
    try:
        return json.loads(METRICS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def results_page(fleet: ds.Fleet) -> None:
    import plotly.graph_objects as go
    st.title("Results: how accurate is the model?")
    results = _metrics()
    if not results:
        st.info("No evaluation results found. Run `python -m pdm.train` to create them.")
        return
    main = results.get("FD001") or next(iter(results.values()))
    t, age = main["test"], main["baselines"]["age_only"]
    st.markdown(f"**Remaining useful life of {main['n_test_engines']} test engines the model never saw** "
                f"(NASA C-MAPSS {main['subset']}, in operating cycles)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Average error (MAE)", f"{t['mae']:.1f} cycles",
              delta=f"{t['mae'] - age['mae']:.1f} vs. age-only guess", delta_color="inverse")
    c2.metric("RMSE", f"{t['rmse']:.1f} cycles",
              delta=f"{t['rmse'] - age['rmse']:.1f} vs. age-only guess", delta_color="inverse")
    c3.metric("80% interval contains the truth", f"{t['coverage']:.0%}",
              delta=f"{(t['coverage'] - 0.8) * 100:+.0f} points vs. the 80% target", delta_color="normal")

    subsets = sorted(results)
    fig = go.Figure()
    for name, label, color in [("model", "Our model", brand("accent") if _valid_color(brand("accent")) else
                                DEFAULTS["accent"]),
                               ("age_only", "Age-only guess", "#9aa5b1"),
                               ("constant", "Constant guess", "#cfd6dd")]:
        ys = [results[s]["test"]["rmse"] if name == "model" else results[s]["baselines"][name]["rmse"]
              for s in subsets]
        fig.add_bar(x=subsets, y=ys, name=label, marker_color=color, text=[f"{y:.0f}" for y in ys],
                    textposition="outside")
    fig.update_layout(barmode="group", height=330, margin=dict(l=10, r=10, t=40, b=10),
                      title="RMSE in cycles on held-out engines (lower is better)",
                      legend=dict(orientation="h", y=-0.15), yaxis_title="RMSE (cycles)")
    left, right = st.columns([3, 2])
    left.plotly_chart(fig, width="stretch")
    regimes = {"FD001": "1 condition, 1 fault", "FD002": "6 conditions, 1 fault", "FD003": "1 condition, 2 faults",
               "FD004": "6 conditions, 2 faults"}
    right.dataframe(pd.DataFrame([{
        "Subset": s, "Setting": regimes.get(s, ""), "Test engines": results[s]["n_test_engines"],
        "RMSE": round(results[s]["test"]["rmse"], 1), "Coverage": f"{results[s]['test']['coverage']:.0%}",
    } for s in subsets]), hide_index=True, width="stretch")
    worst = min(results[s]["test"]["coverage"] for s in subsets)
    best = max(results[s]["test"]["coverage"] for s in subsets)
    right.caption(f"The model beats both baselines on every subset. Its 80% interval contains the true value "
                  f"{worst:.0%}–{best:.0%} of the time, so it is somewhat overconfident. Six operating conditions "
                  f"(FD002, FD004) are harder.")


def users_page(fleet: ds.Fleet) -> None:
    st.title("Who benefits")
    _cards([
        ("🗂️ Maintenance planner", "Sees the whole fleet ranked by urgency, with how long each asset has left, and "
                                  "plans repairs into the next scheduled stop."),
        ("🔧 Technician", "Logs in to a simple page with only the open work orders, most urgent first, and reports "
                         "progress with one click."),
        ("📊 Operations manager", "Fewer unplanned breakdowns, less downtime, and parts replaced when they are worn "
                                 "rather than on a fixed schedule."),
    ])
    st.markdown("---")
    _cards([
        ("🔌 System integrator", "Connects new sensors over MQTT, or existing logs as CSV, and adds new kinds of "
                                "equipment with one registry entry."),
        ("🏭 Existing maintenance system", "Receives work orders as web requests and reports their status back, so "
                                          "the dashboard fits the tools a company already uses."),
    ])


REQUIREMENTS = [
    ("Collect sensor data from any kind of equipment", "MQTT ingestion, CSV import, asset-type registry",
     "Architecture"),
    ("Show each asset's condition so anyone can read it", "Health index 0–100 and a status", "Demo: health score"),
    ("Predict the remaining useful life, with its uncertainty", "Learned model with an 80% interval",
     "Demo: ranking"),
    ("Tell the team what to fix first", "Fleet ranked by status and remaining life", "Demo: ranking"),
    ("Raise alerts with a suggested action", "Alerts per asset and fleet-wide", "Demo: alerts"),
    ("Turn an alert into a work order and track it", "Work orders, technician page, web hook to a CMMS",
     "Demo: work order"),
    ("Separate admin and technician access", "Logins with two roles", "Demo: technician"),
    ("Secure device communication", "TLS, a password per device, topic ACLs", "Testing"),
    ("Work without real equipment for development and demos", "Simulator and recorded replay", "Demo: replay"),
    ("Use the maintenance data on a phone", "XIOS/3 app on CloudBackend with a phone layout, Android wrapper",
     "Demo: mobile app"),
]


def requirements_page(fleet: ds.Fleet) -> None:
    st.title("Requirements and what we built")
    st.dataframe(pd.DataFrame(REQUIREMENTS, columns=["Requirement", "How we met it", "Shown in"]),
                 hide_index=True, width="stretch")
    st.caption("The result: one pipeline from sensor reading to finished repair, made of ingestion, scoring, "
               "prediction, a dashboard and work orders.")


TEST_AREAS = {
    "MQTT ingestion and security": ["test_mqtt.py", "test_mqtt_security.py", "test_simulator.py"],
    "Data intake and storage": ["test_ingest.py", "test_db.py", "test_publish_csv.py", "test_datasets.py",
                                "test_pipeline.py"],
    "Remaining-life model": ["test_rul.py"],
    "Work orders and logins": ["test_work_orders.py", "test_login.py"],
    "Dashboard": ["test_app.py", "test_dashboard_data.py", "test_presentation.py"],
}


def test_counts() -> dict:
    """{area: number of automated tests}, counted from the test files (empty when they are not deployed)."""
    import re
    out = {}
    for area, files in TEST_AREAS.items():
        n = 0
        for f in files:
            try:
                n += len(re.findall(r"^def test_", (TESTS_DIR / f).read_text(), flags=re.M))
            except OSError:
                pass
        if n:
            out[area] = n
    return out


test_counts.__test__ = False      # not a pytest test, despite its name


def testing_page(fleet: ds.Fleet) -> None:
    import plotly.graph_objects as go
    st.title("Testing: how we validated the system")
    counts = test_counts()
    left, right = st.columns([2, 3])
    with left:
        if counts:
            st.metric("Automated tests (pytest)", sum(counts.values()))
            fig = go.Figure(go.Bar(x=list(counts.values()), y=list(counts), orientation="h",
                                   text=list(counts.values()), textposition="outside",
                                   marker_color=brand("accent") if _valid_color(brand("accent"))
                                   else DEFAULTS["accent"]))
            fig.update_traces(cliponaxis=False)
            fig.update_layout(height=280, margin=dict(l=10, r=40, t=10, b=10), yaxis=dict(autorange="reversed"),
                              xaxis=dict(visible=False, range=[0, max(counts.values()) * 1.15]))
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("The test files are not part of this deployment.")
    with right:
        st.markdown(
            "- **End to end over a real MQTT broker:** a simulated device streams readings, the service stores and "
            "scores them, and messages sent while the service was down are processed when it returns.\n"
            "- **Security:** TLS, a password per device, and ACLs that keep each device on its own topics, "
            "tested against Mosquitto.\n"
            "- **Bad data is refused, not fatal:** invalid, duplicate, out-of-order and future readings, with the "
            "reason reported back to the device.\n"
            "- **Model:** features use only past readings (no peeking at the future), and the model must beat a "
            "constant baseline on engines it never saw.\n"
            "- **Work orders:** an alert dispatched from the dashboard reaches an external service, and its status "
            "comes back.\n"
            "- **Dashboard:** every view and both tours are clicked through automatically.")
    st.caption("Run them with `python -m pytest`. The broker tests need Mosquitto or amqtt installed.")


def _lines(field: str) -> str:
    return "\n".join(f"- {line.strip()}" for line in brand(field).splitlines() if line.strip())


def lessons_page(fleet: ds.Fleet) -> None:
    st.title("Lessons learned")
    left, right = st.columns(2)
    with left:
        st.markdown("### What went well")
        st.markdown(_lines("went_well"))
    with right:
        st.markdown("### What we would improve")
        st.markdown(_lines("improve"))
    st.markdown("---")
    st.markdown(f"### {brand('cta')}")
    if brand("team"):
        st.caption(brand("team"))


def display_names(snap: pd.DataFrame, fleet: ds.Fleet) -> pd.DataFrame:
    """The snapshot with plain asset names in place of the ids, for charts and tables."""
    return snap.assign(asset_id=snap["asset_id"].map(labels(fleet)).fillna(snap["asset_id"]))
