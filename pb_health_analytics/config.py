"""
Central configuration for the PB Health Hospital pitch-analytics pipeline.

Everything that is "business knowledge" (keyword clusters, hub locations, pillar
weights, objection taxonomy) lives here so the classifier, analyzer, deck and
dashboard all stay in sync.

Credentials are NEVER hard-coded. Put them in a `.env` file next to this file
(see `.env.example`) or export them as environment variables:
    PB_PORTAL_USERNAME, PB_PORTAL_PASSWORD
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # optional, but nice for local runs
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover
    pass

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("PB_DB_PATH", BASE_DIR / "data" / "pb_health.db"))
OUTPUT_DIR = Path(os.getenv("PB_OUTPUT_DIR", BASE_DIR / "output"))
LOG_DIR = BASE_DIR / "logs"

# --------------------------------------------------------------------------- #
# Portal API
# --------------------------------------------------------------------------- #
PORTAL_URL = "https://datascience.policybazaar.com"
API_BASE_URL = os.getenv("PB_API_BASE_URL", "https://datascienceapi.policybazaar.com/api/v1")
LOGIN_URL = f"{API_BASE_URL}/login"
SEARCH_URL = f"{API_BASE_URL}/searchKeyword/search"
TRANSCRIPT_URL = f"{API_BASE_URL}/transcript"
AUTH_COOKIE_NAME = "ai_portal_cookie"

PORTAL_USERNAME = os.getenv("PB_PORTAL_USERNAME", "")
PORTAL_PASSWORD = os.getenv("PB_PORTAL_PASSWORD", "")

# Networking guards
REQUEST_TIMEOUT_SECS = int(os.getenv("PB_REQUEST_TIMEOUT", "90"))
MAX_RETRIES = int(os.getenv("PB_MAX_RETRIES", "4"))
BACKOFF_BASE_SECS = float(os.getenv("PB_BACKOFF_BASE", "2"))
MIN_SECONDS_BETWEEN_REQUESTS = float(os.getenv("PB_RATE_LIMIT_SECS", "0.5"))
SEARCH_CHUNK_DAYS = int(os.getenv("PB_SEARCH_CHUNK_DAYS", "2"))  # 1-3 days per spec
MIN_SPLIT_WINDOW_HOURS = 3  # never split a timed-out window below this
MAX_PAGES_PER_WINDOW = int(os.getenv("PB_MAX_PAGES", "200"))
TRANSCRIPT_WORKERS = int(os.getenv("PB_TRANSCRIPT_WORKERS", "4"))

# Search filters (fixed per spec)
PB_HEALTH_CATEGORY_ID = 10693  # pre-classified system tag "Pb Health Delhi"
PRODUCT_ID_HEALTH = "2"
SALES_AND_SERVICE_SALES = "1"
MIN_TALKTIME_SECS = 120

# NCR geography used for the PPR denominator query (qualified NCR sales calls).
NCR_STATES = ["Delhi", "Haryana", "Uttar Pradesh"]
NCR_CITIES = [
    "Delhi", "New Delhi", "Gurgaon", "Gurugram", "Noida", "Greater Noida",
    "Ghaziabad", "Faridabad",
]

# --------------------------------------------------------------------------- #
# Keyword clusters used to pull hospital-mention calls from the search API
# --------------------------------------------------------------------------- #
KEYWORD_CLUSTERS: dict[str, list[str]] = {
    "brand": ["pb health", "pb hospital", "policybazaar hospital", "pb health hospital"],
    "hinglish": ["khud ka hospital", "apna hospital", "khud ke hospital", "apne hospital", "humara hospital"],
    "locations": ["iffco chowk", "sector 62", "golf course", "faridabad", "sector 2",
                  "noida sector 50", "sector 50", "rohini"],
    "features": ["multispeciality", "salary based", "overcharge", "waiting time",
                 "pb health app", "exclusive discount", "family discount"],
}

# --------------------------------------------------------------------------- #
# The 5 NCR hubs (ground truth)
# --------------------------------------------------------------------------- #
HUBS: dict[str, dict] = {
    "IFFCO Chowk": {
        "label": "Gurgaon 1 - IFFCO Chowk",
        "city": "Gurgaon",
        "address": "IFFCO Chowk, Gurugram (flagship hub)",
        "serves": "Central & Old Gurgaon, MG Road, Cyber City, NH-48 corridor, South-West Delhi",
    },
    "Sector 62": {
        "label": "Gurgaon 2 - Sector 62, Golf Course Ext.",
        "city": "Gurgaon",
        "address": "Sector 62, Golf Course Extension Road, Gurugram",
        "serves": "Golf Course Rd / Extension, Sohna Road, New Gurgaon sectors",
    },
    "Faridabad": {
        "label": "Faridabad - Sector 2",
        "city": "Faridabad",
        "address": "Sector 2, Faridabad",
        "serves": "Faridabad, Ballabhgarh, Badarpur, South-East Delhi",
    },
    "Noida": {
        "label": "Noida - Sector 50",
        "city": "Noida",
        "address": "Sector 50, Noida",
        "serves": "Noida, Greater Noida, Ghaziabad, East Delhi",
    },
    "Rohini": {
        "label": "Delhi - Rohini",
        "city": "Delhi",
        "address": "Rohini, Delhi",
        "serves": "North & West Delhi, Pitampura, Dwarka side, Sonipat border",
    },
}
HUB_ORDER = list(HUBS.keys())

# Regex patterns (lower-cased, Roman + Devanagari) identifying each hub in speech.
HUB_PATTERNS: dict[str, list[str]] = {
    "IFFCO Chowk": [r"\biff?co\s*chowk\b", r"\biffco\b", r"इफको"],
    "Sector 62": [r"\bsec(tor)?\s*-?\s*62\b", r"\bgolf\s*course\b", r"सेक्टर\s*62", r"गोल्फ\s*कोर्स"],
    "Faridabad": [r"\bfaridabad\b", r"फरीदाबाद"],
    "Noida": [r"\bnoida\b", r"\bsec(tor)?\s*-?\s*50\b", r"नोएडा|नोयडा", r"सेक्टर\s*50"],
    "Rohini": [r"\brohini\b", r"रोहिणी|रोहिनी"],
}
# "Sector 2" alone is ambiguous (many cities have one) so it only counts for
# Faridabad when "faridabad" is in the same turn - handled in classifier.

# Customer-region detection -> nearest hub. Order matters (more specific first).
REGION_TO_HUB: list[tuple[str, str, str]] = [
    # (regex, region label, nearest hub)
    (r"\bgolf\s*course|sohna\s*road|new\s*gurgaon|sector\s*(5[0-9]|6[0-9]|7[0-9])\b.*gurgaon", "Gurgaon (South/New)", "Sector 62"),
    (r"\bgurgaon\b|\bgurugram\b|गुड़गांव|गुरुग्राम|cyber\s*city|mg\s*road|manesar", "Gurgaon", "IFFCO Chowk"),
    (r"\bdwarka\b|\bpalam\b|\bvasant\s*kunj\b|\bmahipalpur\b|द्वारका", "South-West Delhi", "IFFCO Chowk"),
    (r"\bnoida\b|\bgreater\s*noida\b|\bghaziabad\b|\bindirapuram\b|\bvaishali\b|नोएडा|गाजियाबाद", "Noida / Ghaziabad", "Noida"),
    (r"\blaxmi\s*nagar\b|\bmayur\s*vihar\b|\bpreet\s*vihar\b|\bshahdara\b|east\s*delhi", "East Delhi", "Noida"),
    (r"\bfaridabad\b|\bballabhgarh\b|\bbadarpur\b|\bpalwal\b|फरीदाबाद", "Faridabad", "Faridabad"),
    (r"\bsaket\b|\bkalkaji\b|\bgreater\s*kailash\b|\bokhla\b|\bsarita\s*vihar\b|south\s*delhi", "South Delhi", "Faridabad"),
    (r"\brohini\b|\bpitampura\b|\bshalimar\s*bagh\b|\bnarela\b|\bbawana\b|\bsonipat\b|\bmodel\s*town\b|north\s*delhi|रोहिणी", "North Delhi", "Rohini"),
    (r"\bjanakpuri\b|\bpaschim\s*vihar\b|\bpunjabi\s*bagh\b|\brajouri\b|\bvikaspuri\b|\buttam\s*nagar\b|west\s*delhi", "West Delhi", "Rohini"),
]

# Fallback when only portal metadata (city) is known.
CITY_TO_HUB = {
    "gurgaon": "IFFCO Chowk", "gurugram": "IFFCO Chowk",
    "noida": "Noida", "greater noida": "Noida", "ghaziabad": "Noida",
    "faridabad": "Faridabad",
}

# --------------------------------------------------------------------------- #
# Story Adherence Score weights (sum = 100)
# --------------------------------------------------------------------------- #
PILLAR_WEIGHTS: dict[str, int] = {
    "multispeciality": 15,
    "location": 25,
    "ethical": 20,
    "zero_wait": 15,
    "app": 15,
    "family_discount": 10,
}
# Location pillar: base points for naming any hub, bonus when the agent names
# the hub nearest to the customer's (detected) region.
LOCATION_BASE_POINTS = 18
LOCATION_MATCH_BONUS = PILLAR_WEIGHTS["location"] - LOCATION_BASE_POINTS

PILLAR_LABELS: dict[str, str] = {
    "multispeciality": "Multispeciality Hospital",
    "location": "Specific Hub Location",
    "ethical": "Ethical Care / No Overcharging",
    "zero_wait": "Zero Waiting / Digital Check-in",
    "app": "PB Health App Push",
    "family_discount": "Exclusive Family Discount",
    # tracked but not scored
    "top_doctors": "Top Doctors / Specialists",
    "cashless": "End-to-End Cashless",
}
SCORED_PILLARS = list(PILLAR_WEIGHTS.keys())
TRACKED_PILLARS = SCORED_PILLARS + ["top_doctors", "cashless"]

# --------------------------------------------------------------------------- #
# Objection taxonomy
# --------------------------------------------------------------------------- #
OBJECTION_LABELS: dict[str, str] = {
    "location_distance": "Location / Distance friction",
    "clinical_trust": "Clinical trust (vs Max/Fortis/Apollo)",
    "insurance_validity": "Insurance / Cashless validity",
    "facility_scope": "Facility scope (real hospital?)",
    "discount_confusion": "Discount confusion",
    "general_skepticism": "General skepticism / disinterest",
}
TOP5_OBJECTIONS = [k for k in OBJECTION_LABELS if k != "general_skepticism"]
