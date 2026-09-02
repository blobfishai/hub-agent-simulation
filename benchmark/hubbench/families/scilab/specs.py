"""Scenario data model and shared synthetic entities for the SciLab family.

Everything here is clean-room synthetic: the Corvane Institute is not a real
organisation and no scientist, supplier, instrument, reagent lot, or assay
corresponds to a real one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option

AS_OF = "2026-05-11"
ORGANIZATION = {
    "id": "corvane-assay-ops-v1",
    "name": "Corvane Institute — Assay Operations Core",
    "organization_id": "ORG-CORVANE",
    "primary_site": "SITE-MAIN",
    "systems": ["lims", "instruments", "inventory", "supplier", "eln", "approvals", "messages", "chat", "drive", "notes"],
}
SITES = (
    {"site_id": "SITE-MAIN", "name": "Main assay laboratory (building C)", "type": "assay_lab"},
    {"site_id": "SITE-ANNEX", "name": "Cold-store annex (building D)", "type": "cold_store"},
    {"site_id": "SITE-SAT", "name": "Ridgecombe satellite laboratory", "type": "satellite_lab"},
)
SCIENTISTS = (
    {"scientist_id": "SCI-HALVARD", "name": "Ingrid Halvard", "role": "principal_investigator", "focus": "Cytokine immunoassays"},
    {"scientist_id": "SCI-NAKAMURA", "name": "Kenta Nakamura", "role": "study_director", "focus": "Lipid and metabolic panels"},
    {"scientist_id": "SCI-ADEYEMI", "name": "Folake Adeyemi", "role": "method_validation_lead", "focus": "Reference method validation"},
    {"scientist_id": "SCI-BRENNAN", "name": "Siobhan Brennan", "role": "quality_assurance_scientist", "focus": "Stability and release testing"},
    {"scientist_id": "SCI-OYELOWO", "name": "Tunde Oyelowo", "role": "instrument_specialist", "focus": "Analyser calibration and service"},
)
USERS = (
    {"user_id": "U-OPS", "display_name": "Assay Operations Coordinator (you)", "role": "assay_operations_coordinator", "approval_limit_usd": 0},
    {"user_id": "U-VARGA", "display_name": "Réka Varga", "role": "qa_manager", "approval_limit_usd": 20000},
    {"user_id": "U-DESROSIERS", "display_name": "Camille Desrosiers", "role": "qa_director", "approval_limit_usd": 120000},
    {"user_id": "U-LINDGREN", "display_name": "Petter Lindgren", "role": "laboratory_manager", "approval_limit_usd": 15000},
    {"user_id": "U-MWANGI", "display_name": "Wanjiru Mwangi", "role": "study_steering_chair", "approval_limit_usd": 0},
)
SUPPLIERS = (
    {"supplier_id": "SUP-OSTRANDER", "name": "Ostrander Bioreagents", "account_number": "CV-1104"},
    {"supplier_id": "SUP-CALDER", "name": "Calder Reference Materials", "account_number": "CV-0339"},
)
WINDOW_TIMES = {"AM": ("08:00:00", "12:00:00"), "PM": ("12:30:00", "16:30:00")}
WINDOW_HOURS = 4
SAMPLE_UNIT = "SAMPLE"
VIAL_UNIT = "VIAL"


def lab_days(start: str = AS_OF, weeks: int = 3) -> list[str]:
    first = date.fromisoformat(start)
    days = []
    for offset in range(weeks * 7):
        day = first + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day.isoformat())
    return days


def next_lab_day(after: str) -> str:
    """First laboratory day strictly after ``after`` (received lots release after incoming QC the next lab day)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def window_id(instrument: str, day: str, session: str) -> str:
    return f"WIN-{instrument.split('-')[1]}-{day.replace('-', '')}-{session}"


def window_interval(day: str, session: str) -> tuple[str, str]:
    start, end = WINDOW_TIMES[session]
    return f"{day}T{start}", f"{day}T{end}"


@dataclass(frozen=True)
class Assay:
    assay_id: str
    code: str
    name: str
    category: str
    owner_lab: str
    scientist_id: str
    meter_metric: str
    meter_value: int
    meter_date: str
    stale_value: int = 0
    stale_date: str = "2026-02-13"

    @property
    def batch_id(self) -> str:
        return f"BAT-{self.assay_id.split('-')[1]}"

    @property
    def stale_batch_id(self) -> str:
        return f"BAT-{self.assay_id.split('-')[1]}-2602"


@dataclass(frozen=True)
class Protocol:
    protocol_id: str
    code: str
    version: str
    samples_per_plate: int
    control_vials_per_plate: int
    status: str = "current"
    effective_from: str = "2026-02-02"
    control_rule: str = "single-use control vials from one released lot per plate; open vials are never carried across runs"
    superseded_by: str | None = None


@dataclass(frozen=True)
class Reagent:
    code: str
    display: str
    vial_format: str = "2 mL single-use lyophilised control vial"
    storage: str = "2-8 °C refrigerated"
    min_dating_days: int = 14
    validated: bool = True
    interchangeable_with: str | None = None


@dataclass(frozen=True)
class RunRequest:
    request_id: str
    assay_id: str
    reagent_code: str
    protocol_id: str
    unit_kind: str  # "run" | "timepoint"
    unit_basis: str  # "fixed" | "metered"
    samples: int | None
    units_in_scope: int
    scope_note: str
    run_minutes: int
    read_minutes: int
    requested_by: str
    opened_at: str
    note: str = ""
    status: str = "open"
    priority: str = "routine"
    kind: str = "rerun"


@dataclass(frozen=True)
class Lot:
    lot_id: str
    lot_number: str
    reagent_code: str
    site_id: str
    vials: int
    expiry: str
    status: str = "AVAILABLE"
    reason: str | None = None
    reserved_for: str | None = None
    register_excluded: bool = False
    register_note: str = ""


@dataclass(frozen=True)
class Run:
    run_id: str
    assay_id: str | None
    protocol_id: str | None
    instrument_id: str
    kind: str
    started_at: str
    finished_at: str
    status: str
    plates: int
    summary: str


@dataclass(frozen=True)
class QCResult:
    result_id: str
    run_id: str
    control_level: str
    lot_id: str | None
    value: float
    unit: str
    low_limit: float
    high_limit: float
    valid: bool
    note: str = ""


@dataclass(frozen=True)
class Window:
    day: str
    instrument: str
    session: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    name: str
    model: str = "microplate analyser"
    status: str = "ACTIVE"
    validation_capable: bool = True
    cert_id: str = ""
    cert_valid_until: str = "2026-12-31"
    cert_issued_on: str = "2026-01-05"
    cert_status: str = "VALID"
    note: str | None = None

    @property
    def certificate_id(self) -> str:
        return self.cert_id or f"CAL-{self.instrument_id.split('-')[1]}-2026"


@dataclass(frozen=True)
class Certificate:
    cert_id: str
    instrument_id: str
    issued_on: str
    expires_on: str
    status: str
    issuer: str = "Corvane metrology service"
    note: str = ""


@dataclass(frozen=True)
class Booking:
    booking_id: str
    assay_id: str
    request_id: str | None
    instrument_id: str | None
    start: str | None
    end: str | None
    status: str
    description: str


@dataclass(frozen=True)
class Confirmation:
    confirmation_id: str
    supplier_id: str
    reagent_code: str
    reference: str
    vials_available: int
    standard_date: str
    expedited_date: str
    fee: int
    unit_price: float
    valid_until: str
    status: str = "OPEN"
    note: str = ""


@dataclass(frozen=True)
class MethodNote:
    note_id: str
    protocol_code: str
    version: str
    title: str
    status: str
    content: str
    updated_at: str = "2026-04-28T10:00:00"


@dataclass(frozen=True)
class Approval:
    approval_id: str
    subject: str
    approver_id: str
    approver_role: str
    granted_on: str
    scope: dict[str, Any]


@dataclass(frozen=True)
class Email:
    message_id: str
    thread_id: str
    sender: str
    recipients: str
    subject: str
    sent_at: str
    body: str
    attachments: tuple[str, ...] = ()
    labels: str = "assay-ops"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#assay-ops"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Assay Operations"


@dataclass(frozen=True)
class PrimaryWrite:
    tool: str
    arguments: dict[str, Any]
    table: str
    record_id: str
    status: str
    domain_values: dict[str, Any]
    allowed_paths: tuple[str, ...]
    readback_tool: str
    readback_arguments: dict[str, Any]
    readback_expected: dict[str, Any]
    outcome_label: str
    extra_tables: tuple[str, ...] = ()
    extra_assertions: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Scenario:
    ordinal: int
    title: str
    mode: str
    role: str
    instruction: str
    assay: Assay
    other_assays: tuple[Assay, ...]
    protocols: tuple[Protocol, ...]
    reagents: tuple[Reagent, ...]
    requests: tuple[RunRequest, ...]
    lots: tuple[Lot, ...]
    runs: tuple[Run, ...]
    results: tuple[QCResult, ...]
    windows: tuple[Window, ...]
    instruments: tuple[Instrument, ...]
    bookings: tuple[Booking, ...]
    confirmation: Confirmation
    other_confirmations: tuple[Confirmation, ...]
    method_notes: tuple[MethodNote, ...]
    approval: Approval
    business_need: str
    business_need_reason: str
    item: str
    labels: Labels
    numbers: dict[str, Any]
    options: tuple[Option, Option, Option]
    standard_readiness: str
    expedited_readiness: str
    extra_answer: dict[str, Any]
    extra_descriptions: dict[str, str]
    extra_calculations: tuple[dict[str, Any], ...]
    fact_notes: dict[str, str]
    primary_write: PrimaryWrite
    collaboration: dict[str, str]
    unauthorized_write: dict[str, Any]
    decoy_doc: Doc
    email: Email
    chat: Chat
    docs: tuple[Doc, ...]
    windows_query: dict[str, str]
    selected_window_id: str
    run_query: dict[str, Any]
    run_expected: dict[str, Any]
    results_run_id: str
    stale_certificates: tuple[Certificate, ...] = ()
    revision: str = "v1"
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"scilab-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"LAB-{self.ordinal:04d}"

    @property
    def primary_request(self) -> RunRequest:
        return self.requests[0]

    @property
    def primary_reagent(self) -> Reagent:
        return next(item for item in self.reagents if item.code == self.primary_request.reagent_code)

    @property
    def primary_protocol(self) -> Protocol:
        return next(item for item in self.protocols if item.protocol_id == self.primary_request.protocol_id)

    @property
    def current_note(self) -> MethodNote:
        return next(item for item in self.method_notes if item.status == "current")


def plates_for_samples(samples: int, samples_per_plate: int) -> int:
    whole, remainder = divmod(samples, samples_per_plate)
    return int(whole) + (1 if remainder > 0 else 0)


def request_samples(request: RunRequest, assay_by_id: dict[str, Assay]) -> int:
    if request.unit_basis == "fixed":
        if request.samples is None:
            raise ValueError(f"{request.request_id}: fixed requests need a sample count")
        return request.samples
    return assay_by_id[request.assay_id].meter_value


__all__ = [
    "AS_OF",
    "Approval",
    "Assay",
    "Booking",
    "Certificate",
    "Chat",
    "Confirmation",
    "Doc",
    "Email",
    "Instrument",
    "Labels",
    "Lot",
    "MethodNote",
    "ORGANIZATION",
    "Option",
    "PrimaryWrite",
    "Protocol",
    "QCResult",
    "Reagent",
    "Run",
    "RunRequest",
    "SAMPLE_UNIT",
    "SCIENTISTS",
    "SITES",
    "SUPPLIERS",
    "Scenario",
    "USERS",
    "VIAL_UNIT",
    "WINDOW_HOURS",
    "WINDOW_TIMES",
    "Window",
    "lab_days",
    "next_lab_day",
    "plates_for_samples",
    "request_samples",
    "window_id",
    "window_interval",
]
