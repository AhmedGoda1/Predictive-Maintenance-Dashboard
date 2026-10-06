"""Asset types and their sensor channels.

A new kind of equipment is added by registering an `AssetType`: which channels
it reports, which of them describe operating conditions rather than health,
which ones feed the health index, and the limits / RUL thresholds used for
status. Everything else (database, health index, RUL models, dashboard) works
from this description instead of from hard-coded column names.
"""
from dataclasses import dataclass, field
from typing import Optional

SENSOR, CONDITION = "sensor", "condition"
# How a channel contributes to the health index:
LOG_RATIO_UP = "log_ratio_up"   # positive amplitude that grows when degrading (vibration)
Z_ABS = "z_abs"                 # either direction, in baseline standard deviations


@dataclass(frozen=True)
class ChannelDef:
    name: str
    unit: str = ""
    kind: str = SENSOR
    description: str = ""
    health: Optional[str] = None      # LOG_RATIO_UP, Z_ABS or None (not used for health)
    issue: str = ""                   # alert text when this channel drives the deviation
    action: str = ""                  # suggested maintenance action for that alert


@dataclass(frozen=True)
class AssetType:
    type_id: str
    name: str
    age_unit: str                                  # unit of an asset's age and RUL: "s", "cycle", ...
    channels: tuple
    regime_channel: Optional[str] = None           # categorical condition used to group baselines
    limits: tuple = ()                             # ((channel, warning, critical), ...) hard limits
    drift_scale: float = 1.0                       # health = 100 * exp(-drift / drift_scale)
    healthy_min: float = 70.0                      # health >= this -> Healthy
    warning_min: float = 40.0                      # health >= this -> Warning, else Critical
    rul_warning: Optional[float] = None            # predicted RUL below this -> Warning (age units)
    rul_critical: Optional[float] = None           # predicted RUL below this -> Critical
    rul_cap: Optional[float] = None                # piecewise-linear RUL target cap used in training
    baseline_readings: int = 20                    # first N readings of a regime = healthy reference
    smooth_window: int = 7                         # rolling median over readings
    extra: dict = field(default_factory=dict, hash=False, compare=False)

    def channel(self, name: str) -> ChannelDef:
        for c in self.channels:
            if c.name == name:
                return c
        raise KeyError(f"{self.type_id} has no channel {name!r}")

    @property
    def sensor_names(self) -> list:
        return [c.name for c in self.channels if c.kind == SENSOR]

    @property
    def condition_names(self) -> list:
        return [c.name for c in self.channels if c.kind == CONDITION]

    @property
    def health_channels(self) -> list:
        return [c for c in self.channels if c.health]


_TYPES: dict = {}


def register_type(asset_type: AssetType) -> AssetType:
    _TYPES[asset_type.type_id] = asset_type
    return asset_type


def get_type(type_id: str) -> AssetType:
    try:
        return _TYPES[type_id]
    except KeyError:
        raise KeyError(f"Unknown asset type {type_id!r}; registered: {sorted(_TYPES)}") from None


def all_types() -> list:
    return list(_TYPES.values())


# ---------------------------------------------------------------------------
# Brushed DC motor (Zenodo 4314249): vibration spectrum, current, voltage, temperature
# ---------------------------------------------------------------------------
MOTOR = register_type(AssetType(
    type_id="brushed_dc_motor",
    name="Brushed DC motor",
    age_unit="s",
    regime_channel="voltage_regime",
    limits=(("temp_motor", 60.0, 70.0),),
    channels=(
        ChannelDef("voltage_regime", "V", CONDITION, "Nominal supply voltage of the test phase (3 = nominal, 5 = overstress)"),
        ChannelDef("speed_rpm", "rpm", SENSOR, "Shaft speed"),
        ChannelDef("current", "A", SENSOR, "Supply current"),
        ChannelDef("voltage", "V", SENSOR, "Measured supply voltage"),
        ChannelDef("temp_motor", "degC", SENSOR, "Motor surface temperature",
                   issue="Motor surface temperature above limit",
                   action="Reduce supply voltage / load and check cooling and ventilation"),
        ChannelDef("temp_ambient", "degC", SENSOR, "Ambient temperature"),
        ChannelDef("vib_1x", "g", SENSOR, "Vibration amplitude at the shaft speed", LOG_RATIO_UP,
                   "Elevated 1x vibration (imbalance, misalignment or commutator wear)",
                   "Inspect shaft balance, alignment and the commutator surface"),
        ChannelDef("vib_5x", "g", SENSOR, "Vibration amplitude at 5x shaft speed"),
        ChannelDef("vib_7x", "g", SENSOR, "Vibration amplitude at 7x shaft speed"),
        ChannelDef("vib_band_0_4k", "", SENSOR, "Vibration spectrum energy 0-4 kHz", LOG_RATIO_UP,
                   "Broadband vibration rising (brush / commutator wear)",
                   "Inspect brushes and commutator for wear and plan a replacement"),
        ChannelDef("vib_band_4_8k", "", SENSOR, "Vibration spectrum energy 4-8 kHz", LOG_RATIO_UP,
                   "High-frequency vibration rising (bearing wear or brush arcing)",
                   "Check bearings and brush contact, look for arcing marks"),
        ChannelDef("vib_band_8_16k", "", SENSOR, "Vibration spectrum energy 8-16 kHz"),
        ChannelDef("vib_band_16_26k", "", SENSOR, "Vibration spectrum energy 16-26 kHz"),
    ),
))

# ---------------------------------------------------------------------------
# Turbofan engine (NASA C-MAPSS): 3 operating settings + 21 gas-path sensors
# ---------------------------------------------------------------------------
_TURBOFAN_SENSORS = [
    # (channel, unit, description, used for the health index)
    ("s1", "degR", "Total temperature at fan inlet", False),
    ("s2", "degR", "Total temperature at LPC outlet", True),
    ("s3", "degR", "Total temperature at HPC outlet", True),
    ("s4", "degR", "Total temperature at LPT outlet", True),
    ("s5", "psia", "Pressure at fan inlet", False),
    ("s6", "psia", "Total pressure in bypass duct", False),
    ("s7", "psia", "Total pressure at HPC outlet", True),
    ("s8", "rpm", "Physical fan speed", True),
    ("s9", "rpm", "Physical core speed", True),
    ("s10", "", "Engine pressure ratio (P50/P2)", False),
    ("s11", "psia", "Static pressure at HPC outlet", True),
    ("s12", "pps/psi", "Ratio of fuel flow to Ps30", True),
    ("s13", "rpm", "Corrected fan speed", True),
    ("s14", "rpm", "Corrected core speed", True),
    ("s15", "", "Bypass ratio", True),
    ("s16", "", "Burner fuel-air ratio", False),
    ("s17", "", "Bleed enthalpy", True),
    ("s18", "rpm", "Demanded fan speed", False),
    ("s19", "rpm", "Demanded corrected fan speed", False),
    ("s20", "lbm/s", "HPT coolant bleed", True),
    ("s21", "lbm/s", "LPT coolant bleed", True),
]

TURBOFAN = register_type(AssetType(
    type_id="turbofan_engine",
    name="Turbofan engine",
    age_unit="cycle",
    regime_channel=None,
    drift_scale=3.0,
    rul_warning=60.0,
    rul_critical=30.0,
    rul_cap=125.0,
    baseline_readings=20,
    channels=(
        ChannelDef("op1", "", CONDITION, "Operational setting 1 (altitude)"),
        ChannelDef("op2", "", CONDITION, "Operational setting 2 (Mach number)"),
        ChannelDef("op3", "", CONDITION, "Operational setting 3 (throttle resolver angle)"),
        *[
            ChannelDef(n, u, SENSOR, d, Z_ABS if h else None,
                       f"{d} drifting away from its healthy level" if h else "",
                       "Schedule a gas-path inspection of the engine core" if h else "")
            for n, u, d, h in _TURBOFAN_SENSORS
        ],
    ),
))
