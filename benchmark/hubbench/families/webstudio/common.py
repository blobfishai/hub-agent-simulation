"""Shared synthetic entities used by several WebStudio scenarios (clean-room)."""

from __future__ import annotations

from .specs import Lane, Page, Token, TokenSet, TokenVersion, Window

OPS_EMAIL = "web-releases@larkspur.example"

DEFAULT_LANES = (
    Lane("LANE-WEB-1", "Web deploy lane 1 (blue)"),
    Lane("LANE-WEB-2", "Web deploy lane 2 (green)"),
    Lane("LANE-EDGE-3", "Edge deploy lane 3 (regional)"),
)

COLOR_SET = TokenSet("SET-COLOR-CORE", "Orchid colour core", "v3.2")
TYPE_SET = TokenSet("SET-TYPE-SCALE", "Orchid type scale", "v2.1")
SPACE_SET = TokenSet("SET-SPACING", "Orchid spacing", "v2.0")

BRAND_600 = Token(
    "TOK-COLOR-BRAND-600",
    "SET-COLOR-CORE",
    "color.brand.600",
    "color",
    (
        TokenVersion("v3.2", "#2F4FD8", "CURRENT", False, "2026-01-12", "current brand blue"),
        TokenVersion("v4.0", "#2440C9", "PROPOSED", True, "2026-05-04", "contrast ramp: every consumer must re-verify AA on light surfaces"),
    ),
)
ACCENT_500 = Token(
    "TOK-COLOR-ACCENT-500",
    "SET-COLOR-CORE",
    "color.accent.500",
    "color",
    (
        TokenVersion("v2.4", "#F2A93B", "CURRENT", False, "2025-11-03", "current accent amber"),
        TokenVersion("v3.0", "#E9962A", "PROPOSED", True, "2026-05-04", "hue shift alters the contrast pairs; consumers must re-verify"),
    ),
)
SPACE_SECTION = Token(
    "TOK-SPACE-SECTION",
    "SET-SPACING",
    "space.section",
    "spacing",
    (TokenVersion("v2.0", "64px", "CURRENT", False, "2025-09-15", "section rhythm"),),
)
TYPE_BODY_CJK = Token(
    "TOK-TYPE-BODY-CJK",
    "SET-TYPE-SCALE",
    "type.body.cjk",
    "typography",
    (TokenVersion("v1.0", "Larkspur Sans CJK 16/28", "CURRENT", False, "2026-04-20", "additive token for CJK locales"),),
)
TYPE_LEGAL_SMALL = Token(
    "TOK-TYPE-LEGAL-SMALL",
    "SET-TYPE-SCALE",
    "type.legal.small",
    "typography",
    (TokenVersion("v2.1", "Larkspur Sans 12/18", "CURRENT", False, "2026-02-02", "legal small print"),),
)
PARTNER_700 = Token(
    "TOK-COLOR-PARTNER-700",
    "SET-COLOR-CORE",
    "color.partner.700",
    "color",
    (TokenVersion("v1.2", "#1F6F5B", "CURRENT", False, "2026-03-09", "partner programme green"),),
)

PAGES = {
    "pricing": Page("PAGE-3101", "pricing", "Pricing", "Growth", "PER-OSEI", ("GB", "DE", "FR", "US", "CA", "JP", "AU")),
    "pricing-enterprise": Page("PAGE-3188", "pricing-enterprise", "Enterprise pricing", "Growth", "PER-OSEI", ("GB", "US")),
    "checkout": Page("PAGE-3220", "checkout", "Checkout", "Commerce", "PER-CHAUDHRY", ("GB", "DE", "FR", "US", "CA", "JP", "AU")),
    "product-tour": Page("PAGE-3305", "product-tour", "Product Tour", "Product Marketing", "PER-LINDQVIST", ("GB", "DE", "FR", "US")),
    "help-center": Page("PAGE-3410", "help-center", "Help Center", "Support", "PER-HAVILAND", ("GB", "US", "CA", "AU", "JP", "KR", "TW", "SG", "HK", "NZ")),
    "careers": Page("PAGE-3450", "careers", "Careers", "People", "PER-HAVILAND", ("GB", "JP")),
    "homepage": Page("PAGE-3520", "homepage", "Homepage", "Marketing", "PER-LINDQVIST", ("GB", "DE", "FR", "US", "CA", "JP", "AU")),
    "partner-portal": Page("PAGE-3610", "partner-portal", "Partner Portal", "Partnerships", "PER-MORAES", ("GB", "DE", "FR")),
    "partner-directory": Page("PAGE-3620", "partner-directory", "Partner Directory", "Partnerships", "PER-MORAES", ("GB", "DE", "FR")),
    "plans-compare": Page("PAGE-3720", "plans-compare", "Plans comparison", "Growth", "PER-OSEI", ("GB", "DE", "FR", "US", "CA")),
    "summer-teaser": Page("PAGE-3901", "summer-teaser", "Summer teaser microsite", "Marketing", "PER-LINDQVIST", ("GB", "JP")),
}


def protected(day: str, lane: str, session: str, reason: str = "campaign blackout — summer teaser (protected)") -> Window:
    return Window(day, lane, session, "protected", reason)


def free(day: str, lane: str, session: str) -> Window:
    return Window(day, lane, session, "free", "")


def held(day: str, lane: str, session: str, release_id: str) -> Window:
    return Window(day, lane, session, "busy", release_id)


def blocked(day: str, lane: str, session: str, reason: str = "edge provider maintenance (blocked)") -> Window:
    return Window(day, lane, session, "blocked", reason)


__all__ = [
    "ACCENT_500",
    "BRAND_600",
    "COLOR_SET",
    "DEFAULT_LANES",
    "OPS_EMAIL",
    "PAGES",
    "PARTNER_700",
    "SPACE_SECTION",
    "SPACE_SET",
    "TYPE_BODY_CJK",
    "TYPE_LEGAL_SMALL",
    "TYPE_SET",
    "blocked",
    "free",
    "held",
    "protected",
]
