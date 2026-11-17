"""Presentation mode: the dashboard as a pitch to a prospective customer.

Turned on from the sidebar (admins only) or with a link such as `?present=1&customer=Acme%20Aero`. It
- brands the app with the customer's name, tagline, logo and accent colour (the Customize panel),
- gives assets plain names ("Engine 07" instead of "FD001-test-071"),
- hides the developer panels (MQTT, auto-refresh, model internals in the tables) and the Streamlit chrome,
- runs a guided tour: Next / Back moves the app itself to the view, asset, tab and replay position of each step.

Everything lives in the viewer's session, so one presenter never changes what other users see. The data is the
recorded replay, which works with nothing else running.
"""
import html
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

import data_source as ds

VIEWS = ["Fleet", "Asset detail", "Technician view", "Next steps"]
ALL_TYPES = "All types"          # the fleet view's "no type filter" value

DEFAULTS = {
    "customer": "Your Company",
    "tagline": "Predictive maintenance: fix it before it fails",
    "accent": "#2a78d6",
    "logo": "",
    "site": "",
    "cta": "Suggested next step: a pilot on a handful of your assets.",
}
# plain nouns for the asset types; any other registered type falls back to its registry name
TYPE_NOUNS = {"turbofan_engine": "Engine", "brushed_dc_motor": "Drive motor", "li_ion_battery": "Battery pack"}
PROFILE_FIELDS = ["customer", "tagline", "accent", "logo", "site", "cta"]
NEW_PROFILE = "➕ New customer"
QUERY_KEYS = {"customer": "customer", "tagline": "tagline", "accent": "accent", "logo": "logo", "site": "site"}


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
    Step("Every machine on one screen",
         "Each asset's sensors are turned into one health score from 0 to 100 and a status anyone can read. "
         "This is the fleet early in its life: everything is healthy.",
         "Fleet", fleet_pct=15, tab=FLEET_TABS[0]),
    Step("Watch problems appear before they become failures",
         "The replay compresses months of operation into seconds. Watch assets drift from healthy to warning to "
         "critical, while there is still time to act.",
         "Fleet", fleet_pct=15, fleet_play=True, tab=FLEET_TABS[0]),
    Step("Know what to fix first",
         "Assets are ranked by urgency: worst status first, then the shortest remaining life, each with an 80% "
         "range. Your planners get one list instead of a wall of sensor charts.",
         "Fleet", fleet_pct=100, tab=FLEET_TABS[0]),
    Step("Every open alert, fleet-wide",
         "Each alert says what was detected and what to do about it, so nothing waits for someone to read raw data.",
         "Fleet", fleet_pct=100, tab=FLEET_TABS[1]),
    Step("Drill into the asset most at risk",
         "One click opens any asset: its health falling as it wears, and how long it has left, so the repair fits "
         "the next planned stop instead of following a breakdown.",
         "Asset detail", asset_play=True, tab=ASSET_TABS[0]),
    Step("From alert to work order in one click",
         "Open the newest alert and press Dispatch Work Order. It goes to the maintenance team, or straight into the "
         "maintenance system you already use.",
         "Asset detail", tab=ASSET_TABS[2]),
    Step("What the technician sees",
         "Technicians log in to their own simple page: open work orders, most urgent first. Press Start work or "
         "Complete, as a technician would.",
         "Technician view"),
    Step("The loop closes",
         "Back in the office, the alert shows the technician's update the moment it is made. Every step from sensor "
         "to finished repair is on record.",
         "Asset detail", tab=ASSET_TABS[2]),
    Step("Your equipment, next",
         "Any sensor that can send data connects the same way, and new kinds of equipment are added without "
         "changing the dashboard.",
         "Next steps"),
]


# ---------------------------------------------------------------- state
def init() -> None:
    """Reads the presentation settings from the link once per session, and keeps them while the panel is hidden."""
    ss = st.session_state
    for key in [k for k in ss if (k.startswith("brand_") or k.startswith("noun_")) and k != "brand_logo_file"]:
        ss[key] = ss[key]               # a widget's value would otherwise be dropped on a run that does not draw it
    if ss.get("_present_init"):
        return
    ss["_present_init"] = True
    params = st.query_params
    ss.setdefault("present", params.get("present", "").lower() in ("1", "true", "yes"))
    for field, query in QUERY_KEYS.items():
        ss.setdefault(f"brand_{field}", params.get(query) or DEFAULTS[field])
    ss.setdefault("brand_cta", DEFAULTS["cta"])
    accent = "#" + ss["brand_accent"].lstrip("#")         # a link may leave out the "#" (it must be escaped there)
    ss["brand_accent"] = accent if _valid_color(accent) else DEFAULTS["accent"]


def active() -> bool:
    return bool(st.session_state.get("present"))


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


# ---------------------------------------------------------------- customer profiles
def _profiles() -> dict:
    """{customer name: settings} saved in this session; switch between them during a meeting day."""
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
    """The on/off switch and, while on, the Customize panel and the tour button."""
    st.sidebar.toggle("🎤 Presentation mode", key="present", on_change=_sync_link,
                      help="A clean, branded layout and a guided tour for showing the product to a customer.")
    if not active():
        return
    if st.session_state.get("tour_step") is None:
        st.sidebar.button("▶ Start guided tour", key="tour_start", type="primary", width="stretch",
                          on_click=go_to, args=(0, fleet))
    if not _profiles():                   # the customer the link opened with is the first profile
        _profiles()[brand("customer")] = _current_profile()
    names = [*_profiles(), NEW_PROFILE]
    if st.session_state.get("profile_pick") not in names:
        st.session_state["profile_pick"] = names[0]
    st.sidebar.selectbox("Customer", names, key="profile_pick", on_change=load_profile,
                         help="Switch between the customers you saved; the whole app follows.")
    with st.sidebar.expander("🎨 Customize for this customer", expanded=False):
        st.caption("Changes show immediately. Save to switch back to this customer later.")
        st.text_input("Customer name", key="brand_customer", on_change=_sync_link)
        st.text_input("Tagline", key="brand_tagline", on_change=_sync_link)
        st.text_input("Site name (optional)", key="brand_site", on_change=_sync_link,
                      placeholder="e.g. Hamburg hangar 2")
        st.color_picker("Accent colour", key="brand_accent", on_change=_sync_link)
        st.text_input("Logo URL (optional)", key="brand_logo", on_change=_sync_link,
                      placeholder="https://.../logo.png")
        st.file_uploader("...or upload a logo", type=["png", "jpg", "jpeg", "svg", "webp"], key="brand_logo_file",
                         on_change=_logo_uploaded)
        st.markdown("**Asset names**")
        for type_id in sorted(fleet.assets["type_id"].unique()):
            st.session_state.setdefault(f"noun_{type_id}", type_noun(type_id))
            st.text_input(ds.registry.get_type(type_id).name, key=f"noun_{type_id}")
        st.text_area("Closing call to action", key="brand_cta", height=90)
        st.button("💾 Save customer profile", key="profile_save", width="stretch", type="primary",
                  on_click=save_profile)
        if "_profile_saved" in st.session_state:
            st.caption(f"Saved: {st.session_state.pop('_profile_saved')}")
        st.markdown("**All profiles**")
        st.caption("Profiles last while this browser tab is open. Download them to reuse in another session.")
        st.download_button("⬇ Download profiles", export_profiles(), file_name="customer_profiles.json",
                           mime="application/json", key="profiles_download", width="stretch",
                           disabled=not _profiles())
        st.file_uploader("Load profiles", type=["json"], key="profiles_file", on_change=import_profiles)
        base = getattr(st.context, "url", "") or ""
        st.caption("Link that opens this presentation (an uploaded logo is not part of it):")
        st.code(base.split("?")[0] + "?" + urlencode({"present": 1, **{q: brand(f) for f, q in QUERY_KEYS.items()
                                                                          if brand(f) != DEFAULTS[f]}}),
                language=None, wrap_lines=True)


# ---------------------------------------------------------------- look
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
    """The customer's logo, name and tagline at the top of every page."""
    logo = st.session_state.get("brand_logo_bytes") or brand("logo")
    site = f" · {html.escape(brand('site'))}" if brand("site") else ""
    text = (f'<div class="pm-banner"><h1>{html.escape(brand("customer"))}</h1>'
            f'<p>{html.escape(brand("tagline"))}{site}</p></div>')
    if logo:
        left, right = st.columns([1, 9], vertical_alignment="center")
        try:
            left.image(logo, width="stretch")
        except Exception:                 # an unreachable or broken logo must never break the pitch
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
    step = TOUR[i]
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
    if i is None:
        return
    step = TOUR[i]
    with st.container(border=True):
        st.html(f'<div class="pm-step">Step {i + 1} of {len(TOUR)}</div>')
        st.markdown(f"#### {step.title}\n{step.text}")
        back, nxt, end, _ = st.columns([1, 1, 1, 4])
        back.button("◀ Back", key="tour_back", width="stretch", disabled=i == 0, on_click=go_to, args=(i - 1, fleet))
        if i + 1 < len(TOUR):
            nxt.button("Next ▶", key="tour_next", type="primary", width="stretch", on_click=go_to, args=(i + 1, fleet))
        end.button("End tour", key="tour_end", width="stretch", on_click=end_tour)


# ---------------------------------------------------------------- closing page
def closing_page(fleet: ds.Fleet) -> None:
    st.title(f"Next steps for {brand('customer')}")
    n_types = fleet.assets["type_id"].nunique()
    cards = [
        ("🔌 Connect", "Sensors or a gateway send readings over MQTT, the standard IoT protocol, with encryption and "
                      "one login per device. Existing data logs can be imported as CSV."),
        ("🧩 Fit your equipment", f"{n_types} kinds of equipment are configured in this demo. A new kind is a short "
                                 "description of its sensors and limits; the dashboard needs no changes."),
        ("🔧 Fit your workflow", "Work orders go to the built-in technician page, or as a web request to the maintenance "
                                "system you already use, which reports progress back."),
    ]
    for col, (title, text) in zip(st.columns(len(cards)), cards):
        with col:
            st.html(f'<div class="pm-card"><h4>{html.escape(title)}</h4><p>{html.escape(text)}</p></div>')
    st.markdown("---")
    st.markdown(f"### {brand('cta')}")


def display_names(snap: pd.DataFrame, fleet: ds.Fleet) -> pd.DataFrame:
    """The snapshot with plain asset names in place of the ids, for charts and tables."""
    return snap.assign(asset_id=snap["asset_id"].map(labels(fleet)).fillna(snap["asset_id"]))
