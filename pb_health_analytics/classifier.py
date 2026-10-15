"""
Turn-by-turn evaluator for PB Health pitch adherence and customer objections.

* Agent turns (`speakerId == 'agent'`) are scored against the PB Story pillars.
* Customer turns (`speakerId == 'customer'`) are scanned for objections,
  skepticism and the customer's home region (to judge whether the agent
  named the *nearest* hub).

Matching is regex-based over Roman-script Hinglish, English and Devanagari,
with proximity rules for the fuzzier concepts (e.g. "doctor" + "salary" in the
same turn = ethical-care pillar; "far/door" + a city = distance objection).
Each detection keeps the verbatim snippet so a human can audit it.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Iterable

import config

FLAGS = re.IGNORECASE | re.UNICODE


def _rx(patterns: Iterable[str]) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), FLAGS)


# --------------------------------------------------------------------------- #
# Hospital mention (is the agent pitching PB Health at all?)
# --------------------------------------------------------------------------- #
HOSPITAL_WORD = r"(?:hospital|hospitals|aspatal|haspatal|hospitel|हॉस्पिटल|अस्पताल|होस्पिटल)"
BRAND_RX = _rx([
    r"\bp\.?\s?b\.?\s*health\b", r"\bpb\s*hospital\b", r"policy\s*bazaa?r\s*(?:ka|ke|ki)?\s*" + HOSPITAL_WORD,
    r"पीबी\s*हेल्थ", r"पॉलिसी\s*बाजार\s*(?:का|के|की)?\s*" + HOSPITAL_WORD,
])
HINGLISH_OWN_RX = _rx([
    r"\b(?:khud|khudh)\s*(?:ka|ke|ki)\s*" + HOSPITAL_WORD,
    r"\b(?:apna|apne|apni|humara|hamara|humare|hamare|hamari|humari)\s*(?:khud\s*(?:ka|ke)\s*)?(?:ek\s*)?" + HOSPITAL_WORD,
    r"\bour\s*(?:own\s*)?" + HOSPITAL_WORD,
    r"(?:खुद|ख़ुद)\s*(?:का|के|की)\s*" + HOSPITAL_WORD,
    r"(?:अपना|अपने|हमारा|हमारे)\s*" + HOSPITAL_WORD,
])

# --------------------------------------------------------------------------- #
# Story pillars (agent side)
# --------------------------------------------------------------------------- #
PILLAR_RX: dict[str, re.Pattern] = {
    "multispeciality": _rx([
        r"multi\s*-?\s*speciality", r"multi\s*-?\s*specialty", r"multi\s*-?\s*speciali?ty",
        r"\bicu\b", r"\boperation\s*theat(?:er|re)\b", r"\bo\.?t\.?s?\b(?=.*(?:icu|surgery|operation))",
        r"\bday\s*care\b", r"\bdaycare\b", r"full\s*(?:fledged|fleged)\s*" + HOSPITAL_WORD,
        r"\bsurger(?:y|ies)\s*(?:bhi|bhee|also)\b", r"मल्टी\s*स्पेशलिटी", r"आईसीयू",
        r"(?:sirf|only)\s*(?:clinic|clinik)\s*nahi", r"clinic\s*nahi\s*(?:hai|h)\b",
    ]),
    "ethical": _rx([
        r"salary\s*-?\s*based", r"fixed\s*salary", r"(?:on|par)\s*salary", r"salaried",
        r"no\s*(?:revenue\s*)?targets?", r"(?:koi|koyi)\s*target\s*nahi", r"no\s*commission",
        r"(?:koi\s*)?commission\s*nahi", r"over\s*-?\s*charg", r"unnecessary\s*(?:test|surger|operation)",
        r"(?:faltu|fuzool|fizool|bina\s*matlab)\s*(?:ke\s*)?(?:test|operation|surgery|charges?)",
        r"\bethical\b", r"zyada\s*(?:paisa|charge|bill)\s*nahi", r"extra\s*(?:test|charges?)\s*nahi",
        r"सैलरी", r"ओवरचार्ज",
    ]),
    "zero_wait": _rx([
        r"waiting\s*time", r"no\s*wait", r"zero\s*wait", r"(?:wait|intezaar|intzaar)\s*(?:nahi|nhi)\s*(?:karna|krna)",
        r"(?:line|queue|q)\s*(?:me|mein|main)\s*(?:nahi|nhi|khade)", r"no\s*queue", r"pre\s*-?\s*book",
        r"online\s*(?:appointment|booking)", r"digital\s*(?:check\s*-?\s*in|records?|emr)", r"\bemr\b",
        r"appointment\s*(?:book|le)", r"वेटिंग", r"इंतज़ार|इंतजार",
    ]),
    "app": _rx([
        r"pb\s*health\s*(?:ka\s*)?app", r"(?:app|application)\s*(?:download|install)",
        r"(?:download|install)\s*(?:kar|karo|kariye|karna|kijiye|the)?\s*(?:pb\s*health\s*)?(?:app|application)",
        r"play\s*store", r"app\s*store", r"ऐप|एप्लीकेशन",
    ]),
    "family_discount": _rx([
        r"family\s*discount", r"exclusive\s*discount", r"(?:special|flat|extra)\s*discount",
        r"discount\s*(?:milega|milta|milegi|hai|dete|on)", r"(?:parivaar|parivar|family)\s*(?:ko|ke\s*liye|walon|members?)\b.*(?:discount|chhoot|chhut|offer|benefit)",
        r"(?:discount|chhoot|chhut).*(?:family|parivaar|parivar|ghar\s*walon)",
        r"डिस्काउंट", r"छूट",
    ]),
    "top_doctors": _rx([
        r"(?:top|senior|best|experienced|achhe|ache|bade)\s*(?:se\s*achhe\s*)?doctors?", r"specialists?",
        r"cardiolog|orthop|gyna?e?colog|pediatric|paediatric|neurolog|general\s*surg", r"डॉक्टर",
    ]),
    "cashless": _rx([
        r"cash\s*-?\s*less", r"zero\s*deduction", r"no\s*deduction", r"कैशलेस",
    ]),
}

SECTOR2_RX = re.compile(r"\bsec(?:tor)?\s*-?\s*2\b", FLAGS)
HUB_RX = {hub: _rx(pats) for hub, pats in config.HUB_PATTERNS.items()}
REGION_RX = [(re.compile(p, FLAGS), label, hub) for p, label, hub in config.REGION_TO_HUB]

# --------------------------------------------------------------------------- #
# Objections (customer side)
# --------------------------------------------------------------------------- #
DISTANCE = r"(?:far|door|dur|duur|distance|kitna\s*(?:door|dur)|bahut\s*(?:door|dur)|travel|kaise\s*aaun|aana\s*mushkil|nearby|nazdeek|paas\s*(?:me|mein)|दूर|नज़दीक|पास)"
PLACE = r"(?:gurgaon|gurugram|noida|delhi|rohini|faridabad|ghaziabad|location|branch|hospital|wahan|waha|vahan|गुड़गांव|नोएडा|दिल्ली)"
OBJECTION_RX: dict[str, list[re.Pattern]] = {
    "location_distance": [
        re.compile(DISTANCE + r".{0,60}" + PLACE + "|" + PLACE + r".{0,60}" + DISTANCE, FLAGS),
        _rx([r"(?:mere|hamare|humare)\s*(?:ghar\s*)?(?:paas|pass|nazdeek)\s*(?:koi|hai\s*kya|nahi)",
             r"(?:kahan|kaha)\s*(?:par|pe)?\s*hai\s*(?:ye|yeh)?\s*" + HOSPITAL_WORD,
             r"too\s*far", r"any\s*branch\s*near"]),
    ],
    "clinical_trust": [
        _rx([r"\bmax\b", r"\bfortis\b", r"\bapollo\b", r"\bmedanta\b", r"\bartemis\b", r"\bmanipal\b", r"\baiims\b",
             r"(?:kaun|kon)\s*(?:se|si)?\s*doctors?", r"doctors?\s*(?:kaise|kese|kaun|kon|achhe|ache)\b",
             r"(?:achha|acha|accha)\s*hai\s*kya", r"(?:bharosa|bharosaa|trust|bharosemand)",
             r"quality\s*(?:kaisi|kya|ka)", r"(?:review|reviews|rating)", r"naya\s*" + HOSPITAL_WORD,
             r"new\s*hospital", r"मैक्स|फोर्टिस|अपोलो|मेदांता"]),
    ],
    "insurance_validity": [
        _rx([r"(?:meri|mera|my|existing|purani|current)\s*(?:wali\s*)?(?:policy|insurance|mediclaim)\s*.{0,40}(?:chalegi|chalega|valid|work|kaam|accept|lagegi|cover)",
             r"(?:star|hdfc|ergo|care|niva|bupa|icici|lombard|bajaj|sbi|tata\s*aig|aditya\s*birla|new\s*india|national|oriental|united)\s*.{0,30}(?:chalegi|chalega|valid|accept|cashless|work)",
             r"cashless\s*(?:hoga|hogi|milega|chalega|available|hai\s*kya)",
             r"(?:network|empanel)\w*\s*(?:me|mein|hospital)?\s*(?:hai|hain)\s*(?:kya)?",
             r"कैशलेस\s*(?:होगा|मिलेगा)"]),
    ],
    "facility_scope": [
        _rx([r"(?:sirf|only|bas|just)\s*(?:clinic|opd|consultation|checkup)", r"clinic\s*(?:hai|h)\s*(?:kya|ya)",
             r"(?:surgery|operation|icu|admit|bharti|emergency)\s*(?:bhi\s*)?(?:hoti|hota|hogi|hoga|hai|ho\s*sakti|possible|available)\s*(?:kya|hai\s*kya)?\s*\?",
             r"(?:kya|kia)\s*(?:wahan|waha|udhar)?\s*(?:surgery|operation|icu|admit|emergency)",
             r"real\s*hospital", r"full\s*hospital\s*hai", r"(?:kitne|kitna)\s*(?:bed|beds)",
             r"सर्जरी|ऑपरेशन"]),
    ],
    "discount_confusion": [
        _rx([r"discount\s*(?:kaise|kese|kaisa|kab|kitna|kitni|kya)", r"(?:kaise|kese)\s*(?:milega|milegi|lena|le)\s*.{0,20}discount",
             r"how\s*(?:do|will|to)\s*(?:i|we)?\s*(?:get|avail|claim)\s*(?:the\s*)?discount",
             r"discount\s*.{0,30}(?:family|parivaar|ghar\s*walon)\s*(?:ko|ke)\s*(?:bhi|bhee)",
             r"(?:card|code|coupon)\s*(?:milega|chahiye|kaise)", r"डिस्काउंट\s*कैसे"]),
    ],
    "general_skepticism": [
        _rx([r"(?:interest|interested)\s*(?:nahi|nhi|not)", r"not\s*interested", r"(?:zarurat|zaroorat|need)\s*(?:nahi|nhi)",
             r"(?:sure|confirm)\s*(?:nahi|nhi)\s*(?:hu|hoon|hun)", r"(?:fraud|scam|fake|dhokha)", r"(?:sochunga|soch\s*ke\s*batata|sochenge)",
             r"(?:already|pehle\s*se)\s*(?:family\s*)?doctor", r"(?:kyun|kyu|why)\s*(?:jaun|jau|jaaun|jaana)",
             r"insurance\s*company\s*(?:ka|ke)\s*" + HOSPITAL_WORD]),
    ],
}


@dataclass
class CallResult:
    call_id: str
    pitched: bool = False                       # agent mentioned PB hospital (brand or "apna hospital")
    any_mention: bool = False                   # either speaker mentioned it
    pillars: dict[str, bool] = field(default_factory=dict)
    hubs_mentioned: list[str] = field(default_factory=list)
    customer_region: str | None = None
    nearest_hub: str | None = None
    region_matched: bool = False
    adherence_score: float = 0.0
    objections: list[str] = field(default_factory=list)
    has_objection: bool = False
    snippets: dict[str, list[str]] = field(default_factory=dict)
    agent_turns: int = 0
    customer_turns: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _snip(text: str, m: re.Match, width: int = 90) -> str:
    s, e = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("…" if s else "") + text[s:e].strip() + ("…" if e < len(text) else "")


def _add_snip(res: CallResult, key: str, text: str, m: re.Match, limit: int = 3) -> None:
    lst = res.snippets.setdefault(key, [])
    s = _snip(text, m)
    if s not in lst and len(lst) < limit:
        lst.append(s)


def detect_region(text: str) -> tuple[str | None, str | None]:
    for rx, label, hub in REGION_RX:
        if rx.search(text):
            return label, hub
    return None, None


def find_hubs(text: str) -> list[tuple[str, re.Match]]:
    found = []
    for hub, rx in HUB_RX.items():
        m = rx.search(text)
        if m:
            found.append((hub, m))
    if "Faridabad" not in {h for h, _ in found}:
        m = SECTOR2_RX.search(text)
        if m and re.search(r"faridabad|फरीदाबाद", text, FLAGS):
            found.append(("Faridabad", m))
    return found


def classify_call(call_id: str, transcripts: list[list[dict]] | list[dict],
                  metadata_city: str | None = None) -> CallResult:
    """Classify one call.

    `transcripts` may be a single turn list or several (e.g. [english, hindi]);
    flags are OR-ed across them and snippets de-duplicated."""
    if transcripts and isinstance(transcripts[0], dict):
        transcripts = [transcripts]  # type: ignore[list-item]
    res = CallResult(call_id=str(call_id), pillars={p: False for p in config.TRACKED_PILLARS})
    hubs: dict[str, None] = {}
    region_votes: list[tuple[str, str]] = []

    for turns in transcripts:  # type: ignore[union-attr]
        n_agent = n_cust = 0
        for turn in turns or []:
            text = str(turn.get("text") or "")
            if not text.strip():
                continue
            speaker = str(turn.get("speakerId") or "").lower()
            is_agent = speaker.startswith("agent")
            is_customer = speaker.startswith("cust")
            n_agent += is_agent
            n_cust += is_customer

            mention = BRAND_RX.search(text) or HINGLISH_OWN_RX.search(text)
            if mention:
                res.any_mention = True
                if is_agent:
                    res.pitched = True
                    _add_snip(res, "pitch", text, mention)

            if is_agent:
                for pillar, rx in PILLAR_RX.items():
                    m = rx.search(text)
                    if m:
                        res.pillars[pillar] = True
                        _add_snip(res, pillar, text, m)
                for hub, m in find_hubs(text):
                    hubs[hub] = None
                    res.pillars["location"] = True
                    _add_snip(res, "location", text, m)

            if is_customer:
                label, hub = detect_region(text)
                if label:
                    region_votes.append((label, hub))
                for obj, rxs in OBJECTION_RX.items():
                    for rx in rxs:
                        m = rx.search(text)
                        if m:
                            if obj not in res.objections:
                                res.objections.append(obj)
                            _add_snip(res, f"objection:{obj}", text, m)
                            break
        res.agent_turns = max(res.agent_turns, n_agent)
        res.customer_turns = max(res.customer_turns, n_cust)

    # A Max/Fortis mention etc. only counts as an objection on calls where the
    # hospital actually came up; otherwise it is just generic insurance chatter.
    if not res.any_mention:
        res.objections = [o for o in res.objections if o in ("insurance_validity",)]
        res.snippets = {k: v for k, v in res.snippets.items()
                        if not k.startswith("objection:") or k.split(":", 1)[1] in res.objections}

    res.hubs_mentioned = [h for h in config.HUB_ORDER if h in hubs]
    if region_votes:
        res.customer_region, res.nearest_hub = region_votes[0]
    elif metadata_city:
        hub = config.CITY_TO_HUB.get(metadata_city.strip().lower())
        if hub:
            res.customer_region, res.nearest_hub = metadata_city.title(), hub
    res.region_matched = bool(res.nearest_hub and res.nearest_hub in res.hubs_mentioned)
    res.has_objection = bool(res.objections)
    res.adherence_score = score(res)
    return res


def score(res: CallResult) -> float:
    """Story Adherence Score 0-100 (only meaningful for pitched calls)."""
    if not res.pitched:
        return 0.0
    w = config.PILLAR_WEIGHTS
    pts = 0.0
    for pillar in config.SCORED_PILLARS:
        if pillar == "location":
            if res.pillars.get("location"):
                pts += config.LOCATION_BASE_POINTS + (config.LOCATION_MATCH_BONUS if res.region_matched else 0)
        elif res.pillars.get(pillar):
            pts += w[pillar]
    return round(pts, 1)


# Keywords highlighted in the dashboard transcript viewer.
HIGHLIGHT_RX = [BRAND_RX, HINGLISH_OWN_RX, *PILLAR_RX.values(), *HUB_RX.values()]
