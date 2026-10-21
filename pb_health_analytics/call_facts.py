"""
Plain per-call facts from real transcripts (no scores, no weights).

1. Harmonise   - drop empty turns, normalise Hinglish spellings ("policy bazar",
                 "khud ke hospital", "sec 62", "sector baasath" ...), and merge
                 consecutive same-speaker turns into AGENT / CUSTOMER blocks.
                 One-word back-channels ("haan", "ji", "achcha") from the other
                 speaker do not split a block.
2. Pitch       - an AGENT block that names PB Health / Policybazaar's own
                 hospital ("pb health", "policybazaar ka hospital", "khud ka
                 hospital", "hamara hospital" + PB context) = pitched.
3. Windows     - everything else is only looked for *close to a hospital
                 mention*: agent story elements in the 4 blocks after it,
                 customer doubts in the direct reaction (2 blocks) or, up to
                 8 blocks later, in lines that point at PB's hospital. A
                 customer asking "cashless hoga?" twenty minutes later about the
                 insurance plan is not a hospital doubt.
4. Facts       - hubs named, story elements, customer doubt buckets, and the
                 verbatim customer line + the agent's next reply.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

F = re.IGNORECASE | re.UNICODE


# --------------------------------------------------------------------------- #
# 1. Harmonisation
# --------------------------------------------------------------------------- #
NORMALISE: list[tuple[re.Pattern, str]] = [(re.compile(p, F), r) for p, r in [
    (r"\bpolic(?:y|i)\s*-?\s*ba(?:z|j)aa?r(?:\s*dot\s*com)?\b|\bpolicyba(?:z|j)aa?r\b", "policybazaar"),
    (r"\bp\s*\.?\s*b\s*\.?\s+(?=health|hospital|helth)", "pb "),
    (r"\bpb\s*helth\b|\bpbhealth\b|\bbaby health(?= hospital)", "pb health"),
    (r"\b(?:hospitel|haspatal|aspatal|hospitall?)\b", "hospital"),
    (r"\bkhud\s*(?:ka|ke|ki|kaa)\b|\bkhud(?:ka|ke|ki)\b", "khud ka"),
    (r"\bgurugram\b|\bgudgaon\b|\bgurgao\b", "gurgaon"),
    (r"\bmulti\s*-?\s*special(?:i)?t(?:y|ies)\b|\bmulti\s*-?\s*speciali?t(?:y|ies)\b|\bmultispecial(?:i)?ty\b", "multispeciality"),
    (r"\b(?:i\s*f\s*f\s*c\s*o|ifco|iffko|ifko|iphco)\b", "iffco"),
    (r"\bsec\b\.?", "sector"),
    (r"\bsector\s*-?\s*(?:sixty\s*-?\s*two|ba+s(?:a|h)+th?|bashath)\b", "sector 62"),
    (r"\bsector\s*-?\s*(?:fifty|pach(?:a|aa)s)\b", "sector 50"),
    (r"\bsector\s*-?\s*(?:two|do)\b", "sector 2"),
    (r"\bsector\s*-?\s*(\d+)\b", r"sector \1"),
    (r"\bopd\b|\bo\s*p\s*d\b", "opd"),
    (r"\s+", " "),
]]

BACKCHANNEL = set("""haan han haa ha haanji hanji ji jee jii achcha accha acha achha theek thik hai hain h hmm hm
    hmmm ok okay okk sahi right yes yeah ya acchha bilkul ho haa ji""".split())


def normalise(text: str) -> str:
    t = " " + str(text or "").lower() + " "
    for rx, rep in NORMALISE:
        t = rx.sub(rep, t)
    return t.strip()


def _is_backchannel(text: str) -> bool:
    words = re.findall(r"\w+", text.lower())
    return 0 < len(words) <= 3 and all(w in BACKCHANNEL for w in words)


@dataclass
class Block:
    speaker: str          # AGENT | CUSTOMER
    text: str             # verbatim, joined
    norm: str             # normalised
    start: str = ""       # mm:ss of first turn


def harmonise(turns: list[dict]) -> list[Block]:
    """Merge raw diarised turns into speaker blocks."""
    blocks: list[Block] = []
    for t in turns or []:
        raw = str(t.get("text") or "").strip()
        if not raw:
            continue
        spk = str(t.get("speakerId") or "").lower()
        spk = "AGENT" if spk.startswith("agent") else "CUSTOMER" if spk.startswith("cust") else None
        if spk is None:
            continue
        # back-channel from the other speaker inside a running block: absorb it
        if blocks and blocks[-1].speaker != spk and _is_backchannel(raw):
            continue
        if blocks and blocks[-1].speaker == spk:
            blocks[-1].text += " " + raw
        else:
            blocks.append(Block(spk, raw, "", str(t.get("time") or "")))
    for b in blocks:
        b.norm = normalise(b.text)
    return blocks


def choose_transcript(hindi: list[dict], english: list[dict]) -> list[dict]:
    """The portal's 'hindi' track is romanised Hinglish and is the complete one;
    fall back to 'english' only when it is empty."""
    return hindi if hindi else english


# --------------------------------------------------------------------------- #
# 2. Pitch tags
# --------------------------------------------------------------------------- #
# "PB Health" on its own is NOT a hospital pitch - on real calls agents use it for
# the PB Health app, "PB Health wellness", platinum membership, gym passes. A pitch
# needs the hospital itself to be named as Policybazaar's.
HOSP = r"hospitals?\b"
OWN = r"(?:khud ka|apna|apne|apni|own)"
# words agents slip in before "hospital": "khud ka BHI hospital", "khud ka APNA ON hospital" (ASR writes own as on)
GAP = r"(?:(?:bhi|bhee|ek|apna|apne|naya|on|own|multispeciality)\s+){0,3}"
# Strong phrasings are a pitch on their own.
STRONG_TAGS: dict[str, re.Pattern] = {
    "PB Health Hospital / PB Hospital": re.compile(r"\bpb\s*(?:health\s*)?(?:ka\s*)?" + HOSP, F),
    "Policybazaar ka khud ka/apna hospital": re.compile(
        r"\bpolicybazaar\s*(?:ka|ke|ki|kaa|ne)?\s*(?:sir\s*)?(?:bhi\s*|bhee\s*)?(?:ek\s*)?" + OWN + r"\s*" + GAP + HOSP, F),
    "khud ka hospital": re.compile(r"\bkhud ka\s*" + GAP + HOSP, F),
}
# Weak phrasings are also how agents describe the *network* ("policybazaar ke
# listed hospitals", "aap apna hospital mein ja sakte ho", "Apna Hospital" is even a
# real hospital name in Ujjain), so they only count with an own-hospital signal
# within 80 characters and no network wording right next to the match.
WEAK_TAGS: dict[str, re.Pattern] = {
    "Policybazaar hospital": re.compile(r"\bpolicybazaar\s*(?:ka|ke|ki|kaa)?\s*(?:bhi\s*|bhee\s*)?(?:ek\s*)?(?:naya\s*)?" + HOSP, F),
    "apna/hamara hospital": re.compile(
        r"\b(?:apna|apne|apni|humara|hamara|humare|hamare|hamari|humari|our|our own)\s*(?:khud ka\s*)?" + GAP + HOSP, F),
    "PB Health ... hospital": re.compile(
        r"\bpb health\b(?:(?!\bapp\b|wellness|membership|platinum|plus|card|claim).){0,50}?\b" + HOSP
        + r"|\b" + HOSP + r"(?:(?!\bapp\b|wellness|membership|platinum|plus|card|claim).){0,50}?\bpb health\b", F),
}
OWN_NEAR = re.compile(
    r"khud ka|\bown\b|\bopen|\bkhul|\bkhol|launch|naam se|name se|first hospital|pehla hospital|nay[ae] hospital"
    r"|iffco|golf course|mg road|m g road|\bpb health\b", F)
NETWORK_NEAR = re.compile(
    r"listed|tie\s*-?\s*up|\btie\b|\btype kar|network|empanel|partner|\blist\b|\bkayi\b|\bkai\b|\bsaare\b|\bsabhi\b"
    r"|board|samne|\bdesk\b|choose|select", F)
TIE_UP_NEAR = re.compile(r"listed|tie\s*-?\s*up|\btie\b|\btype kar|empanel|partner|network", F)
PB_HEALTH_ONLY = re.compile(r"\bpb health\b", F)


def pitch_tags(norm: str) -> list[str]:
    tags = []
    for tag, rx in STRONG_TAGS.items():
        if any(not TIE_UP_NEAR.search(norm[max(0, m.start() - 40): m.end() + 40]) for m in rx.finditer(norm)):
            tags.append(tag)
    for tag, rx in WEAK_TAGS.items():
        for m in rx.finditer(norm):
            wide = norm[max(0, m.start() - 80): m.start()] + " | " + norm[m.end(): m.end() + 80]
            close = norm[max(0, m.start() - 40): m.start()] + " | " + norm[m.end(): m.end() + 40]
            if OWN_NEAR.search(wide) and not NETWORK_NEAR.search(close) and not TIE_UP_NEAR.search(m.group(0)):
                tags.append(tag)
                break
    return tags


# --------------------------------------------------------------------------- #
# 4. Locations and story elements (agent side, inside hospital windows)
# --------------------------------------------------------------------------- #
# On real calls agents almost never say "IFFCO Chowk" - they describe the open
# hospital as "MG Road, Gurgaon (near MG Road metro)". That is kept as its own
# bucket rather than silently credited to IFFCO Chowk.
HUB_RX: dict[str, re.Pattern] = {
    "IFFCO Chowk": re.compile(r"\biffco\b", F),
    "Sector 62 / Golf Course": re.compile(r"\bsector 62\b|\bgolf\s*course\b", F),
    "Faridabad Sec 2": re.compile(r"\bfaridabad\b", F),
    "Noida Sec 50": re.compile(r"\bnoida\b|\bsector 50\b", F),
    "Rohini": re.compile(r"\brohini\b|\brohni\b", F),
}
MG_ROAD_RX = re.compile(r"\bm\s*g road\b|\bmg road\b|\bm (?:zero|z|b) road\b|\bmehrauli gurgaon\b", F)
GURGAON_RX = re.compile(r"\bgurgaon\b", F)
FIVE_HUBS = list(HUB_RX)
LOCATION_ORDER = FIVE_HUBS + ["MG Road, Gurgaon (address only)", "Gurgaon (generic)"]

ELEMENT_RX: dict[str, re.Pattern] = {
    "multispeciality": re.compile(
        r"multispeciality|super\s*speciality|full\s*(?:fledged|fleged|hospital)|\bicu\b|operation\s*theat|\bo t\b"
        r"|surger(?:y|ies)\s*(?:bhi|bhee|also|hoti|hota|hogi)|admit\s*(?:bhi|hota|hoga)|\bipd\b|day\s*care|clinic nahi"
        r"|har (?:tarah|type) ka (?:ilaaj|treatment)|saari (?:speciality|specialities)", F),
    "clinic_opd": re.compile(r"\bclinic\b|\bopd\b|consultation|\bconsult\b", F),
    "ethical": re.compile(
        r"salary|salaried|commission|\btarget\b|over\s*-?\s*charg|unnecessary|faltu|fizool|fuzool|bina\s*matlab|ethical"
        r"|zyada\s*(?:bill|paisa|charge)\s*nahi|extra\s*(?:test|charge)|\bloot|transparent", F),
    "zero_wait": re.compile(
        r"waiting(?!\s*period)|\bwait\s*(?:nahi|nhi|karna nahi)|intezaar|intzaar|intezar|\bline\s*(?:me|mein|main)\s*(?:nahi|khade)"
        r"|\bqueue\b|pre\s*-?\s*book|digital\s*(?:check|record|report|prescription)|online\s*(?:appointment|booking|consult|report)"
        r"|doctor\s*(?:ka|ki|se)?\s*appointment|appointment\s*(?:app|online)|\bemr\b|check\s*-?\s*in", F),
    "app": re.compile(
        r"\b(?:app|application)\b.{0,60}(?:download|install)|(?:download|install).{0,60}\b(?:app|application)\b"
        r"|play\s*store|app\s*store|\bpb health\s*(?:ka|ki|wala|wali)?\s*(?:app|application)\b", F),
    "family_discount": re.compile(
        r"(?:discount|chhoot|chhut|\boff\b|percent|pratishat).{0,80}(?:family|parivaar|parivar|ghar\s*walon|mummy|papa|mother|father|wife|bachch|parents|members)"
        r"|(?:family|parivaar|parivar|ghar\s*walon|mummy|papa|mother|father|wife|bachch|parents|members).{0,80}(?:discount|chhoot|chhut|percent|pratishat)", F),
    "cashless": re.compile(r"cash\s*-?\s*less|zero\s*deduction|no\s*deduction|direct\s*settle|deposit\s*(?:nahi|jama nahi)|pay\s*nahi\s*karna", F),
}
# What agents say about the hospital beyond the story (plain counts, Tab 3).
CLAIM_RX: dict[str, re.Pattern] = {
    "Quotes a % discount (e.g. '50% off consultation')": re.compile(
        r"(?:\d+|ten|twenty|thirty|forty|fifty|sixty|seventy|hundred|pachaas|pachas|bees|tees|dus)\s*(?:five\s*)?(?:percent|%|pratishat)", F),
    "Says 'free' consultation / treatment / revisit": re.compile(r"free\s*(?:of\s*cost|consultation|ilaaj|treatment|mein|revisit)|muft", F),
    "Says '100% claim guarantee'": re.compile(r"(?:hundred|100|sau)\s*(?:percent|%)?\s*(?:claim|guarantee)|claim\s*guarantee", F),
    "Calls it the 'first' hospital": re.compile(r"\bfirst\b|pehla|pehli", F),
    "Says other cities/hubs are 'coming soon'": re.compile(
        r"khulne\s*wal|open\s*hone\s*wal|khulega|khulenge|khulegi|coming soon|dheere dheere|aane wale time|upcoming"
        r"|one forty cities|140 cities|aur (?:bhi )?hospitals? (?:bhi )?(?:khul|open)", F),
    "Mentions doctors (top / senior / AIIMS / specialists)": re.compile(
        r"top doctors?|senior doctors?|achhe doctors?|achche doctors?|best doctors?|specialist|aiims|experienced doctor", F),
}

# --------------------------------------------------------------------------- #
# Customer doubt buckets (customer side, close to a hospital mention)
# --------------------------------------------------------------------------- #
DOUBT_REACTION_BLOCKS = 2  # the customer's direct reaction: up to 2 blocks after a hospital mention ...
DOUBT_WINDOW_FAR = 8       # ... later lines (up to 8 blocks) only when they point at PB's hospital
DOUBT_LABELS: dict[str, str] = {
    "scope": "Scope doubt",
    "trust": "Doctor/Trust doubt",
    "location": "Location friction",
    "cashless": "Cashless/Insurance doubt",
    "discount": "Discount confusion",
    "skeptic": "Skepticism/Rushing past",
}
DOUBT_DESC: dict[str, str] = {
    "scope": "Is it a real hospital for surgeries/ICU or just an OPD clinic?",
    "trust": "Who are the doctors? Are they as good as Max/Fortis?",
    "location": "Where exactly is it? It's too far from where I live.",
    "cashless": "Will my existing policy work cashless there?",
    "discount": "How do I and my family get the discount?",
    "skeptic": "Not interested / aage chalo",
}
HOSPITAL_REF = (r"(?:\bwahan|\bwaha\b|\bvahan|\budhar|(?:us|uss|is|ye|yeh|wo|woh|aapke|aapka|apke|apka)\s*hospital|\bpb\b"
                r"|policybazaar|khud ka|m\s*g road|mg road)")
PB_EXPLICIT = (r"(?:(?:us|uss|is|ye|yeh|aapke|aapka|apke|apka)\s*hospital|\bpb\b|policybazaar\s*(?:ka|ke|ki)?\s*(?:khud ka\s*)?hospital"
               r"|khud ka|m\s*g road|mg road)")
PB_REF = re.compile(HOSPITAL_REF + r"|chota\s*(?:sa\s*)?hospital|naya hospital|hospital\s*kaisa|kaisa hospital", F)
# Customer lines about the insurer's network / coverage are not hospital doubts.
NETWORK_TALK = re.compile(
    r"cashless hospital|network|kitne hospital|kaun (?:kaun )?se hospital|kaun sa hospital cover|hospitals? cover|\blist\b|tie\s*up"
    r"|cover (?:hai|hota|hoga|karega|karti)|\bbupa\b|cigna|tele\s*consult|\boffice\b|bhej|\bmail\b|\blink\b|whatsapp|\bsms\b", F)
WHERE_Q = re.compile(r"(?:kahan|kaha|kidhar|kis jagah|where)\s*(?:par|pe|pr)?\s*(?:hai|h|hain|is|located|open|khula|khul)\b|^(?:to\s*|toh\s*)?(?:kahan|kaha|kidhar)\b", F)
WHERE_CONTEXT = re.compile(r"hospital|wahan|branch|location|sector|road|delhi|noida|gurgaon|faridabad|rohini|ghaziabad|dwarka|ncr|khula|open", F)


def _is_where_question(norm: str) -> bool:
    m = WHERE_Q.search(norm)
    if not m:
        return False
    if NETWORK_TALK.search(norm):
        return False
    short = len(norm.split()) <= 8
    if m.group(0).strip().startswith(("kahan", "kaha", "kidhar", "to", "toh")) and m.start() == 0 and not re.search(r"\b(?:hai|h|hain|par|pe)\b", m.group(0)):
        return len(norm.split()) <= 6
    return short or bool(WHERE_CONTEXT.search(norm))


DOUBT_RX: dict[str, re.Pattern] = {
    "scope": re.compile(
        r"\b(?:sirf|only|bas|just)\s*(?:opd|clinic|consultation|check\s*up|checkup|test)|clinic\s*(?:hai|h|hi|hee|type|jaisa)\b|ya\s*clinic|walk\s*-?\s*in"
        r"|chota\s*(?:sa\s*)?hospital|bada\s*hospital\s*(?:hai|nahi)|kitna bada|kitne bed|real hospital|full hospital"
        r"|proper hospital|kaisa hospital|hospital kaisa|kis (?:type|tarah) ka hospital"
        r"|(?:surgery|operation|icu|admit|admission|bharti|emergency|delivery|ipd)\s*bhi\s*(?:hoti|hota|hogi|hoga|hote|ho\s*(?:sakti|sakta|jayega|jayegi)|milega|milegi|karte|karenge)"
        r"|(?:surgery|operation|icu|admit|admission|bharti|emergency|delivery|ipd)\s*(?:hoti|hota|hogi|hoga|hote)\s*(?:hai\s*)?kya"
        r"|(?:wahan|waha|udhar|us hospital|is hospital)\s*.{0,20}(?:surgery|operation|icu|admit|bharti|emergency)"
        r"|(?:wahan|waha|hospital)\s*.{0,30}kya kya (?:hota|milta|treatment|facility|ilaaj)|kya kya (?:hota|milta|treatment|facility|ilaaj).{0,30}(?:wahan|waha|hospital)"
        r"|kaun kaun (?:si|se) (?:facility|suvidha|treatment|bimari)", F),
    "trust": re.compile(
        r"\b(?:max|fortis|apollo|medanta|artemis|manipal|aiims|ganga ram|narayana|paras|blk)\b(?!\s*(?:bupa|life|cigna))"
        r"(?=.*(?:jaisa|jaise|compare|better|se achha|se accha|jaate|jata|jaati|paas|nazdeek|yahan|idhar))"
        r"(?!.*(?:le rakha|liya tha|policy|plan|claim|insurance|premium|\bcard\b|cover))"
        r"|(?:kaun|kon)\s*(?:se|si|sa)?\s*doctors?|doctors?\s*(?:kaise|kese|kaun|kon)|doctors?\s*(?:achhe|ache|achche)\s*(?:hai|hain)?\s*kya"
        r"|\bm\s*d\s*kaun|hospital\s*(?:achha|acha|accha|achcha)\s*(?:hai|h)\s*(?:kya|ki nahi)|(?:bharosa|trust)\s*(?:kaise|kyun|kyu|nahi hota|nahi hai|kar sakte|karein)|(?:hospital|\bpb\b).{0,30}(?:reliable|reputation|review|rating)"
        r"|(?:hospital|\bpb\b|policybazaar|iske|iska|isko).{0,30}(?:suna nahi|pehli baar sun)|(?:suna nahi|pehli baar sun).{0,30}(?:hospital|\bpb\b|policybazaar)", F),
    "location": re.compile(
        r"\b(?:door|dur|duur|far|distance)\b(?!\s*(?:nahi|nhi))|(?:ghar|area|yahan|idhar)\s*(?:ke\s*)?(?:paas|pass|nazdeek|najdeek)"
        r"|(?:mere|hamare|humare)\s*(?:ghar|area|location|city|sheher)\s*(?:ke\s*)?(?:paas|nazdeek)|\bnazdeek|\bnajdeek|nearby|near\s*me"
        r"|(?:delhi|noida|ghaziabad|faridabad|rohini|dwarka|gurgaon|east delhi|south delhi|west delhi|north delhi|karol bagh)\s*(?:mein|me|main)\s*(?:bhi\s*(?:hai|h|koi|khul)|koi|nahi\s*hai|kahan)"
        r"|location\s*(?:kya|bata|kahan)|kis location|address\s*(?:kya|bata|kahan|bhej)|sector kaun|kaun sa sector|kaun se sector|gurgaon se karna"
        r"|gurgaon (?:jana|jaana)|(?:jaana|jana|aana)\s*(?:padega|padta|mushkil)|^(?:to\s*|toh\s*)?(?:\w+\s*){0,2}(?:sab|har) jagah|kab (?:se )?(?:functional|khulega|khulegi|open hoga|chalu)", F),
    "cashless": re.compile(
        r"(?=.*" + PB_EXPLICIT + r")(?:cash\s*-?\s*less|(?:meri|mera|my|existing|purani|current)\s*(?:wali\s*)?(?:policy|insurance|mediclaim|plan)\s*.{0,40}(?:chalegi|chalega|valid|work|kaam|accept|lagegi|lagega|use)"
        r"|insurance\s*(?:se|mein|me)\s*(?:cover|chalega|hoga)|(?:pay|paisa|bill)\s*(?:karna|dena|bharna)\s*(?:padega|hoga|pade)|deposit)", F),
    "discount": re.compile(
        # premium haggling ("maximum discount do, quarterly payment kar deta hoon") is not a hospital-discount doubt
        r"(?!.*(?:premium|payment|quarterly|monthly|\bemi\b|approval|maximum|installment|\bkist))"
        r"(?:discount\s*(?:kaise|kese|kitna|kitni|kab|kya|kahan|milega|milegi|rahega|rahegi|hai kya|hoga|wala)|(?:kitna|kitne|kya|kaise)\s*(?:percent\s*)?discount"
        r"|(?:discount|chhoot|chhut).{0,40}(?:family|father|mother|wife|parents|mummy|papa|bachch\w*|ko bhi)"
        r"|(?:family|parivar|wife|mummy|papa|parents|bachch\w*|mother|father)\s*(?:ko|ke liye)\s*(?:bhi)?\s*(?:milega|milegi|hoga|chalega|applicable)"
        r"|(?:card|code|coupon)\s*(?:milega|chahiye|kaise|lena)|(?:consultation|opd|doctor)\s*(?:fees?|charges?)\s*(?:kitna|kitni|kya))", F),
    "skeptic": re.compile(
        r"(?:interest|interested)\s*(?:nahi|nhi|not)|not interested|(?:mujhe|hume|humein|humko|mereko|mere ko)\s*(?:abhi\s*)?(?:koi\s*)?(?:zarurat|zaroorat|jarurat|need)\s*(?:nahi|nhi)(?!\s*pad)"
        r"|(?:aage|aagey)\s*(?:chalo|chaliye)\b|(?:ye|yeh|wo|woh|hospital|ise|isko)\s*(?:sab\s*)?(?:chhodo|chodo)\s*(?:na|yaar|sir|mam|ji)?\s*$|^(?:\w+\s+){0,2}(?:rehne|rahne) do\s*(?:na|yaar|sir|mam|ji)?\s*$|(?:hospital|wahan).{0,20}(?:rehne|rahne) do|leave it"
        r"|(?:hospital|wahan)\s*(?:ka|ki)?\s*(?:kya karna|kya karenge|kya karunga)|nahi jaunga|nahi jayenge"
        r"|bas policy\b|sirf policy\b|point pe aao|mujhe nahi chahiye|ayurved|free (?:mein|me) (?:hota|ho jata)", F),
}


# Naming the PB Health app anywhere in the call counts as an app push, even
# outside the hospital conversation.
PB_HEALTH_APP_RX = re.compile(r"\bpb health\s*(?:ka|ki|wala|wali|ke)?\s*(?:app|application)\b", F)
ELEMENT_WINDOW_BLOCKS = 4  # agent blocks from a hospital mention up to 4 blocks later
CLAIM_TAGS = {
    "Quotes a % discount (e.g. '50% off consultation')": "% discount",
    "Says 'free' consultation / treatment / revisit": "Free consult/treatment",
    "Says '100% claim guarantee'": "100% claim guarantee",
    "Calls it the 'first' hospital": "'First' hospital",
    "Says other cities/hubs are 'coming soon'": "Other hubs 'coming soon'",
    "Mentions doctors (top / senior / AIIMS / specialists)": "Doctors (top/senior)",
}


@dataclass
class CallFacts:
    call_id: str
    n_turns: int = 0
    pb_health_said: bool = False                 # agent said "PB Health" anywhere (app / wellness / hospital)
    hospital_mentioned: bool = False
    mentioned_by: str = "-"                      # Agent / Customer / Both / -
    pitched: bool = False
    pitch_phrases: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    elements: dict[str, bool] = field(default_factory=dict)
    claims: list[str] = field(default_factory=list)
    doubts: list[str] = field(default_factory=list)
    doubt_quotes: dict[str, str] = field(default_factory=dict)      # bucket -> customer verbatim
    doubt_replies: dict[str, str] = field(default_factory=dict)     # bucket -> agent's next block, verbatim
    pitch_quote: str = ""


def _hits(blocks: list[Block]) -> list[int]:
    return [i for i, b in enumerate(blocks) if pitch_tags(b.norm)]


def _near(hits: list[int], n: int, before: int, after: int) -> list[int]:
    out: set[int] = set()
    for i in hits:
        out.update(range(max(0, i - before), min(n, i + after + 1)))
    return sorted(out)


def _clip(text: str, rx: re.Pattern | None = None, max_words: int = 45) -> str:
    """Verbatim excerpt of at most `max_words`, centred on the match when given."""
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    centre = 0
    m = rx.search(text) if rx is not None else None
    if m:
        centre = len(text[:m.start()].split())
    lo = max(0, min(centre - max_words // 3, len(words) - max_words))
    return ("… " if lo else "") + " ".join(words[lo:lo + max_words]) + (" …" if lo + max_words < len(words) else "")


def analyse_call(call_id: str, hindi: list[dict], english: list[dict]) -> CallFacts:
    turns = choose_transcript(hindi, english)
    blocks = harmonise(turns)
    res = CallFacts(call_id=str(call_id), n_turns=len(turns), elements={k: False for k in ELEMENT_RX})
    agent_blocks = [b for b in blocks if b.speaker == "AGENT"]
    res.pb_health_said = any(PB_HEALTH_ONLY.search(b.norm) for b in agent_blocks)
    res.elements["app"] = any(PB_HEALTH_APP_RX.search(b.norm) for b in agent_blocks)

    hits = _hits(blocks)
    if not hits:
        return res
    res.hospital_mentioned = True
    speakers = {blocks[i].speaker for i in hits}
    res.mentioned_by = "Both" if len(speakers) == 2 else next(iter(speakers)).title()
    agent_hits = [i for i in hits if blocks[i].speaker == "AGENT"]
    res.pitched = bool(agent_hits)
    if res.pitched:
        phrases: dict[str, None] = {}
        for i in agent_hits:
            phrases.update(dict.fromkeys(pitch_tags(blocks[i].norm)))
        res.pitch_phrases = list(phrases)
        first = blocks[agent_hits[0]]
        m = next((rx.search(first.text.lower()) for rx in (*STRONG_TAGS.values(), *WEAK_TAGS.values())
                  if rx.search(first.text.lower())), None)
        res.pitch_quote = _clip(first.text, re.compile(re.escape(m.group(0)), F) if m else None, max_words=60)

    # --- agent side: locations, story elements, claims (hospital conversation only)
    locs: dict[str, None] = {}
    claims: dict[str, None] = {}
    for i in _near(hits, len(blocks), 0, ELEMENT_WINDOW_BLOCKS):
        b = blocks[i]
        if b.speaker != "AGENT":
            continue
        for hub, rx in HUB_RX.items():
            if rx.search(b.norm):
                locs[hub] = None
        if MG_ROAD_RX.search(b.norm):
            locs["MG Road, Gurgaon (address only)"] = None
        elif GURGAON_RX.search(b.norm):
            locs["Gurgaon (generic)"] = None
        for el, rx in ELEMENT_RX.items():
            if rx.search(b.norm):
                res.elements[el] = True
        for label, rx in CLAIM_RX.items():
            if rx.search(b.norm):
                claims[CLAIM_TAGS[label]] = None
    if any(h in locs for h in ("IFFCO Chowk", "Sector 62 / Golf Course")):
        locs.pop("Gurgaon (generic)", None)
    if "MG Road, Gurgaon (address only)" in locs:
        locs.pop("Gurgaon (generic)", None)
    res.locations = [h for h in LOCATION_ORDER if h in locs]
    res.claims = list(claims)

    # --- customer side: doubts raised right around a hospital mention. Blocks 5-8
    # after a mention only count when the customer's own line refers to the hospital.
    # A line right after the mention (direct reaction) counts on its own; later
    # lines must point at PB's hospital ("wahan", "aapka hospital", "pb", ...).
    # Lines about the insurer's network / coverage never count.
    reaction = set(_near(hits, len(blocks), 1, DOUBT_REACTION_BLOCKS))
    for i in _near(hits, len(blocks), 1, DOUBT_WINDOW_FAR):
        b = blocks[i]
        if b.speaker != "CUSTOMER" or len(b.text.split()) < 2:
            continue
        if i not in reaction and not PB_REF.search(b.norm):
            continue
        if NETWORK_TALK.search(b.norm) and not PB_REF.search(b.norm):
            continue
        for bucket, rx in DOUBT_RX.items():
            if bucket in res.doubt_quotes:
                continue
            if not rx.search(b.norm) and not (bucket == "location" and _is_where_question(b.norm)):
                continue
            rx = rx if rx.search(b.norm) else WHERE_Q
            if bucket != "skeptic" and len(b.text.split()) < 3:
                continue
            res.doubt_quotes[bucket] = _clip(b.text, rx)
            reply = next((blocks[j] for j in range(i + 1, min(len(blocks), i + 4))
                          if blocks[j].speaker == "AGENT" and len(blocks[j].text.split()) >= 5), None)
            res.doubt_replies[bucket] = _clip(reply.text, max_words=60) if reply else ""
    res.doubts = [d for d in DOUBT_LABELS if d in res.doubt_quotes]
    return res


def dump_windows(blocks: list[Block]) -> list[tuple[str, str]]:
    """Debug helper: the (speaker, text) blocks around hospital mentions."""
    return [(blocks[i].speaker, blocks[i].text) for i in _near(_hits(blocks), len(blocks), 1, DOUBT_WINDOW_FAR)]
