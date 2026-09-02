"""Scenario data model and shared synthetic entities for the ClinicOps family.

Everything here is clean-room synthetic: Northlake Health is not a real
organisation and no patient, clinician, or supplier corresponds to a real one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option

AS_OF = "2026-03-09"
ORGANIZATION = {
    "id": "northlake-infusion-v1",
    "name": "Northlake Health — Infusion Services",
    "organization_id": "ORG-NORTHLAKE",
    "primary_site": "LOC-INF",
    "systems": ["ehr", "pharmacy", "scheduling", "supplier", "approvals", "messages", "chat", "drive", "notes"],
}
LOCATIONS = (
    {"location_id": "LOC-INF", "name": "Northlake Infusion Center", "type": "infusion_center"},
    {"location_id": "LOC-PHARM", "name": "Northlake Infusion Pharmacy", "type": "infusion_pharmacy"},
    {"location_id": "LOC-SAT", "name": "Eastgate Satellite Pharmacy", "type": "satellite_pharmacy"},
)
PRACTITIONERS = (
    {"practitioner_id": "DR-OKAFOR", "name": "Dr. Chidi Okafor", "role": "attending", "specialty": "Gastroenterology"},
    {"practitioner_id": "DR-LINDQVIST", "name": "Dr. Maja Lindqvist", "role": "attending", "specialty": "Neurology"},
    {"practitioner_id": "DR-MBEKI", "name": "Dr. Thandiwe Mbeki", "role": "attending", "specialty": "Rheumatology"},
    {"practitioner_id": "DR-SATO", "name": "Dr. Kenji Sato", "role": "attending", "specialty": "Medical Oncology"},
    {"practitioner_id": "DR-HALE", "name": "Dr. Miriam Hale", "role": "medical_director", "specialty": "Infusion Services"},
)
USERS = (
    {"user_id": "U-COORD", "display_name": "Infusion Operations Coordinator (you)", "role": "infusion_operations_coordinator", "approval_limit_usd": 0},
    {"user_id": "U-RAMAN", "display_name": "Priya Raman", "role": "pharmacy_manager", "approval_limit_usd": 35000},
    {"user_id": "U-DUBOIS", "display_name": "Léa Dubois", "role": "pharmacy_director", "approval_limit_usd": 150000},
    {"user_id": "U-WHITFIELD", "display_name": "Dana Whitfield", "role": "nursing_director", "approval_limit_usd": 25000},
    {"user_id": "U-HALE", "display_name": "Dr. Miriam Hale", "role": "medical_director", "approval_limit_usd": 0},
)
SUPPLIERS = (
    {"supplier_id": "SUP-CASCADIA", "name": "Cascadia Specialty Distribution", "account_number": "NL-2201"},
    {"supplier_id": "SUP-MERIDIAN", "name": "Meridian Biologics Supply", "account_number": "NL-0877"},
)
SESSION_TIMES = {"AM": ("08:00:00", "12:00:00"), "PM": ("12:30:00", "16:30:00")}
SESSION_HOURS = 4


def clinic_days(start: str = AS_OF, weeks: int = 3) -> list[str]:
    first = date.fromisoformat(start)
    days = []
    for offset in range(weeks * 7):
        day = first + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day.isoformat())
    return days


def next_clinic_day(after: str) -> str:
    """First clinic day strictly after ``after`` (received stock releases next clinic day)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def slot_id(chair: str, day: str, session: str) -> str:
    return f"SLOT-{chair.split('-')[1]}-{day.replace('-', '')}-{session}"


def session_interval(day: str, session: str) -> tuple[str, str]:
    start, end = SESSION_TIMES[session]
    return f"{day}T{start}", f"{day}T{end}"


@dataclass(frozen=True)
class Patient:
    patient_id: str
    mrn: str
    family: str
    given: str
    birth_date: str
    sex: str
    weight_kg: float
    weight_date: str
    height_cm: float
    practitioner_id: str

    @property
    def weight_observation_id(self) -> str:
        return f"OBS-WT-{self.patient_id.split('-')[1]}"

    @property
    def height_observation_id(self) -> str:
        return f"OBS-HT-{self.patient_id.split('-')[1]}"

    @property
    def display(self) -> str:
        return f"{self.given} {self.family}"


@dataclass(frozen=True)
class Medication:
    code: str
    display: str
    vial_strength: float
    vial_unit: str
    route: str = "intravenous"
    storage: str = "2-8 °C refrigerated"
    min_dating_days: int = 14
    interchangeable_with: str | None = None


@dataclass(frozen=True)
class Order:
    request_id: str
    patient_id: str
    medication_code: str
    dose_value: float
    dose_unit: str
    regimen: str
    doses_in_scope: int
    infusion_minutes: int
    observation_minutes: int
    requester_id: str
    authored_on: str
    note: str = ""
    status: str = "active"
    priority: str = "routine"
    intent: str = "order"


@dataclass(frozen=True)
class Lot:
    lot_id: str
    lot_number: str
    medication_code: str
    location_id: str
    quantity: int
    expiry: str
    status: str = "AVAILABLE"
    reason: str | None = None
    reserved_for: str | None = None
    register_excluded: bool = False
    register_note: str = ""


@dataclass(frozen=True)
class Session:
    day: str
    chair: str
    session: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class Chair:
    chair_id: str
    name: str
    status: str = "ACTIVE"
    first_dose_capable: bool = True
    note: str | None = None


@dataclass(frozen=True)
class Appt:
    appointment_id: str
    patient_id: str
    request_id: str | None
    chair_id: str | None
    start: str | None
    end: str | None
    status: str
    description: str


@dataclass(frozen=True)
class Confirmation:
    confirmation_id: str
    supplier_id: str
    medication_code: str
    reference: str
    quantity_available: int
    standard_date: str
    expedited_date: str
    fee: int
    unit_price: float
    valid_until: str
    status: str = "OPEN"
    note: str = ""


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
    labels: str = "infusion"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#infusion-ops"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Infusion Services"


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
    patient: Patient
    other_patients: tuple[Patient, ...]
    medications: tuple[Medication, ...]
    orders: tuple[Order, ...]
    lots: tuple[Lot, ...]
    sessions: tuple[Session, ...]
    chairs: tuple[Chair, ...]
    appointments: tuple[Appt, ...]
    confirmation: Confirmation
    other_confirmations: tuple[Confirmation, ...]
    approval: Approval
    business_need: str
    business_need_reason: str
    item: str
    labels: Labels
    numbers: dict[str, int | str]
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
    slots_query: dict[str, str]
    selected_slot_id: str
    revision: str = "v1"
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"clinicops-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"CLIN-{self.ordinal:04d}"

    @property
    def primary_order(self) -> Order:
        return self.orders[0]

    @property
    def primary_medication(self) -> Medication:
        return next(item for item in self.medications if item.code == self.primary_order.medication_code)


def vials_for_dose(dose_amount: float, vial_strength: float) -> int:
    whole, remainder = divmod(dose_amount, vial_strength)
    return int(whole) + (1 if remainder > 1e-9 else 0)


__all__ = [
    "AS_OF",
    "Appt",
    "Approval",
    "Chair",
    "Chat",
    "Confirmation",
    "Doc",
    "Email",
    "LOCATIONS",
    "Labels",
    "Lot",
    "Medication",
    "ORGANIZATION",
    "Option",
    "Order",
    "PRACTITIONERS",
    "Patient",
    "PrimaryWrite",
    "SESSION_HOURS",
    "SESSION_TIMES",
    "SUPPLIERS",
    "Scenario",
    "Session",
    "USERS",
    "clinic_days",
    "next_clinic_day",
    "session_interval",
    "slot_id",
    "vials_for_dose",
]
