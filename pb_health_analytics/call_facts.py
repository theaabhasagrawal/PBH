"""
Harmonize call transcripts and pull concrete PB Health Hospital facts out of each call.

Step 1 - harmonize
    * every turn is labelled AGENT / CUSTOMER / UNKNOWN
    * text is normalized: Devanagari keywords and digits -> Roman, Hinglish
      spelling variants collapsed ("hamare"/"humara", "khudh ka", "p b health",
      "policy bazar", "sec-62" ...), then pitch phrases are replaced by standard tags:
          <pb_hospital>      pb health / pb hospital / policybazaar ka hospital /
                             khud ka hospital / humara (apna) hospital / apna hospital
          <hub:iffco_chowk>  <hub:sector_62>  <hub:faridabad_sec2>  <hub:noida_sec50>  <hub:rohini>
    The verbatim text is kept next to the normalized text, and quotes always come from it.

Step 2 - hospital window
    Insurance sales calls say "cashless", "discount" and "app download" about
    the *policy* all the time. So pitch elements and customer doubts are only
    counted inside the stretch of the call where PB Hospital is being discussed:
    from 1 turn before each <pb_hospital> mention to 6 turns after it. The
    window is extended by 3 turns whenever the talk stays on hospital topics,
    and is capped at 20 turns per mention.

Step 3 - facts (yes/no, no scores)
    * pitched         an AGENT turn contains <pb_hospital>
    * hubs            hub tags in AGENT turns inside the window; "Gurgaon (generic)"
                      when only Gurgaon is said
    * story elements  multispeciality (vs. calling it a clinic / OPD pass), ethical /
                      no overcharge, zero waiting / digital, app download, family
                      discount, cashless - AGENT turns inside the window
    * doubts          six buckets, CUSTOMER turns inside the window, each with the
                      verbatim customer line and the agent's next reply
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

FLAGS = re.IGNORECASE | re.UNICODE


def _rx(*patterns: str) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), FLAGS)


# --------------------------------------------------------------------------- #
# Labels (wording used in the workbook)
# --------------------------------------------------------------------------- #
HUBS: dict[str, str] = {
    "iffco_chowk": "IFFCO Chowk",
    "sector_62": "Sector 62 Golf Course",
    "faridabad_sec2": "Faridabad Sec 2",
    "noida_sec50": "Noida Sec 50",
    "rohini": "Rohini",
}
GENERIC_GURGAON = "Gurgaon (generic)"

ELEMENTS: dict[str, str] = {
    "multispeciality": "Real Multispeciality Hospital",
    "clinic_framing": 'Called it a "Clinic" / "OPD pass" (wrong framing)',
    "ethical": "Ethical Care / No Incentive to Overcharge",
    "zero_wait": "Zero Waiting Time / Digital First",
    "app": "PB Health App Download",
    "family_discount": "Exclusive Family Discount",
    "cashless": "Cashless Guarantee",
}

DOUBTS: dict[str, tuple[str, str]] = {
    # key: (bucket label, what it means)
    "scope": ("Scope doubt", "Is it a real hospital for surgeries/ICU or just an OPD clinic?"),
    "trust": ("Doctor/Trust doubt", "Who are the doctors? Are they as good as Max/Fortis?"),
    "location": ("Location friction", "It's too far from where I live / where is it?"),
    "cashless": ("Cashless/Insurance doubt", "Will my existing policy work cashless there?"),
    "discount": ("Discount confusion", "How do I and my family get the discount?"),
    "skeptic": ("Skepticism / Rushing past", "Not interested / aage chalo"),
}

# --------------------------------------------------------------------------- #
# 1. Harmonization
# --------------------------------------------------------------------------- #
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_DEVANAGARI_WORD = re.compile("[ऀ-ॣॱ-ॿ]+")  # Devanagari letters, without danda / digits

# Whole-word Devanagari -> Roman. Only words the detectors care about.
_DEV_WORDS_RAW: dict[str, str] = {
    "पीबी": "pb", "हेल्थ": "health", "पॉलिसी": "policy", "पालिसी": "policy", "बाजार": "bazaar", "बाज़ार": "bazaar",
    "पॉलिसीबाजार": "policybazaar", "पॉलिसीबाज़ार": "policybazaar",
    "हॉस्पिटल": "hospital", "होस्पिटल": "hospital", "हस्पताल": "hospital", "अस्पताल": "hospital",
    "हॉस्पिटल्स": "hospital", "खुद": "khud", "ख़ुद": "khud", "का": "ka", "के": "ke", "की": "ki", "एक": "ek",
    "अपना": "apna", "अपने": "apna", "अपनी": "apna", "हमारा": "humara", "हमारे": "humara", "हमारी": "humara",
    "इफको": "iffco", "इफ्को": "iffco", "चौक": "chowk", "सेक्टर": "sector", "गोल्फ": "golf", "कोर्स": "course",
    "फरीदाबाद": "faridabad", "फ़रीदाबाद": "faridabad", "नोएडा": "noida", "नोयडा": "noida", "नोईडा": "noida",
    "रोहिणी": "rohini", "रोहिनी": "rohini", "गुड़गांव": "gurgaon", "गुड़गाँव": "gurgaon", "गुडगांव": "gurgaon",
    "गुरुग्राम": "gurgaon", "गुरूग्राम": "gurgaon", "दिल्ली": "delhi",
    "मल्टीस्पेशलिटी": "multispeciality", "मल्टी": "multi", "स्पेशलिटी": "speciality", "स्पेशियलिटी": "speciality",
    "आईसीयू": "icu", "ऑपरेशन": "operation", "आपरेशन": "operation", "सर्जरी": "surgery", "एडमिट": "admit",
    "भर्ती": "bharti", "इमरजेंसी": "emergency", "क्लीनिक": "clinic", "क्लिनिक": "clinic", "ओपीडी": "opd",
    "सैलरी": "salary", "ओवरचार्ज": "overcharge", "कमीशन": "commission", "टारगेट": "target", "फालतू": "faltu",
    "टेस्ट": "test", "वेटिंग": "waiting", "इंतजार": "intezaar", "इंतज़ार": "intezaar", "लाइन": "line",
    "डिस्काउंट": "discount", "छूट": "chhoot", "फैमिली": "family", "परिवार": "parivaar",
    "ऐप": "app", "एप": "app", "एप्लीकेशन": "application", "डाउनलोड": "download", "लिंक": "link",
    "कैशलेस": "cashless", "क्लेम": "claim", "नेटवर्क": "network", "इंश्योरेंस": "insurance", "बीमा": "insurance",
    "डॉक्टर": "doctor", "डाक्टर": "doctor", "डॉक्टर्स": "doctors", "मैक्स": "max", "फोर्टिस": "fortis",
    "अपोलो": "apollo", "मेदांता": "medanta", "भरोसा": "bharosa",
    "दूर": "door", "पास": "paas", "नज़दीक": "nazdeek", "नजदीक": "nazdeek", "कहाँ": "kahan", "कहां": "kahan",
    "कैसे": "kaise", "कितना": "kitna", "कितनी": "kitni", "मिलेगा": "milega", "मिलेगी": "milegi",
    "चलेगी": "chalegi", "चलेगा": "chalega", "होगा": "hoga", "होगी": "hogi", "होती": "hoti", "होता": "hota",
    "क्या": "kya", "भी": "bhi", "सिर्फ": "sirf", "सिर्फ़": "sirf", "बस": "bas", "है": "hai", "हैं": "hain",
    "नहीं": "nahi", "ज़रूरत": "zarurat", "जरूरत": "zarurat", "इंटरेस्टेड": "interested", "इंटरेस्ट": "interest",
    "आगे": "aage", "चलो": "chalo", "चलिए": "chaliye", "बाद": "baad", "में": "mein", "सोचेंगे": "sochenge",
    "सोचूंगा": "sochunga", "कौन": "kaun", "से": "se", "मेरी": "meri", "मेरा": "mera", "मेरे": "mere",
    "को": "ko", "लिए": "liye", "घर": "ghar", "वालों": "walon",
}
DEV_WORDS = {unicodedata.normalize("NFC", k): v for k, v in _DEV_WORDS_RAW.items()}

# Roman spelling harmonization, applied in order on lower-cased text.
_ROMAN_RULES: list[tuple[re.Pattern, str]] = [(re.compile(p, FLAGS), r) for p, r in [
    (r"(\w)['’]s\b", r"\1"),                                   # policybazaar's -> policybazaar
    (r"['’`]", ""),
    (r"\bp\s*\.?\s*b\s*\.?\s*(?=(?:health|helth|healt|hospital)\b)", "pb "),
    (r"\b(?:helth|healt|heath)\b", "health"),
    (r"\b(?:hospitals|hospitel|hospitl|hospatal|haspatal|aspatal|hospitaal|hospittal|hopital|haspital|aspataal)\b",
     "hospital"),
    (r"\bpolicy\s*-?\s*(?:baa?zaa?r|bajaar|bajar)\b|\bpolicybaa?zaa?r\b", "policybazaar"),
    (r"\bkhudh\b", "khud"),
    (r"\bkhud(ka|ke|ki)\b", r"khud \1"),
    (r"\b(?:hamara|hamare|hamari|humare|humari|hamaara|humaara|hamra|hamaare)\b", "humara"),
    (r"\b(?:apne|apni|apana|apnaa|apanaa)\b", "apna"),
    (r"\bmulti\s*-?\s*speciali?t(?:y|ies)\b|\bmulti\s*-?\s*specialt(?:y|ies)\b|\bmultispecial\w*\b", "multispeciality"),
    (r"\bsuper\s*-?\s*speciali?t(?:y|ies)\b|\bsuper\s*-?\s*specialt(?:y|ies)\b", "superspeciality"),
    (r"\bcash\s*-?\s*less\b", "cashless"),
    (r"\biffco\s*-?\s*tokio\b|\biffco\s*-?\s*tokyo\b", "iffcotokio"),    # insurer, not the hub
    (r"\b(?:i\s*f\s*f\s*c\s*o|ifco|iffko|ifko|iffco)\b", "iffco"),
    (r"\b(?:chauk|chok|chowck)\b", "chowk"),
    (r"\bsec(?:tor)?\s*[-.]?\s*(\d{1,3})\b", r"sector \1"),
    (r"\bgolf\s*-?\s*course\b|\bgolfcourse\b", "golf course"),
    (r"\b(?:gurugram|gudgaon|gurgoan|gurgao|gurgram)\b", "gurgaon"),
    (r"\bfaridabaad\b", "faridabad"),
    (r"\b(?:noyda|noeda)\b", "noida"),
    (r"\b(?:rohni|rohinee)\b", "rohini"),
    (r"\bo\s*\.?\s*p\s*\.?\s*d\b", "opd"),
    (r"\bi\s*\.?\s*c\s*\.?\s*u\b", "icu"),
    (r"\b(?:clinik|clinics|klinik)\b", "clinic"),
    (r"\s+", " "),
]]

PB_TAG = "<pb_hospital>"

# Pitch phrases -> <pb_hospital>. "apna hospital" also means "your own choice of
# hospital" in insurance talk ("aap apna hospital choose kar sakte hain"), so it
# is only tagged when that reading is ruled out (see _own_hospital_ok).
# words that may sit between the owner phrase and "hospital": "khud ka (ek) multispeciality hospital"
_DESC = (r"(?:(?:ek|apna|own|multispeciality|superspeciality|bada|naya|nayi|full|proper|accha|achha|private|"
         r"world\s*class|khud\s*(?:ka|ke|ki))\s+){0,3}")
_PB_STRONG = _rx(
    r"\bpb\s*health(?:\s*hospital)?\b",
    r"\bpb\s*hospital\b",
    r"\bpb\s*(?:ka|ke|ki)\s*" + _DESC + r"hospital\b",
    r"\bpolicybazaar\s*(?:has|have)\s*(?:its|their)?\s*own\s*" + _DESC + r"hospital\b",
    r"\bpolicybazaar\s*(?:ka|ke|ki)?\s*" + _DESC + r"hospital\b",
    r"\bkhud\s*(?:ka|ke|ki)\s*" + _DESC + r"hospital\b",
    r"\bhumara\s*" + _DESC + r"hospital\b",
    r"\bour\s*own\s*" + _DESC + r"hospital\b",
)
# "Policybazaar ne Gurgaon mein hospital khola hai": tag it but keep the words in between
_PB_LAUNCH = _rx(r"\bpolicybazaar\s*(?:ne|has|have)?\s*(?:\w+\s+){0,4}?hospital\s*(?:khola|khole|open\w*|launch\w*|start\w*|shuru|bana\w*)\b")
_PB_WEAK = _rx(r"\bapna\s*" + _DESC + r"hospital\b")
_WEAK_BEFORE = _rx(r"\b(?:aap|aapka|aapke|aapki|ap|apka|apke|tum|tumhara|customer|marzi|pasand)\b")
_WEAK_AFTER = _rx(r"^\W*(?:\w+\W+){0,3}?(?:choose|chuz|select|chun|pasand|prefer|decide)")

_HUB_RULES: list[tuple[re.Pattern, str]] = [(re.compile(p, FLAGS), r) for p, r in [
    (r"\bnoida\s*sector\s*\d{1,3}\b", "<hub:noida_sec50>"),     # "noida sector 62" is Noida, not the Gurgaon hub
    (r"\biffco(?:\s*chowk)?\b", "<hub:iffco_chowk>"),
    (r"\b(?:gurgaon\s*)?sector\s*62\b", "<hub:sector_62>"),
    (r"\bgolf\s*course(?:\s*(?:extension|ext|road|rd))*\b", "<hub:sector_62>"),
    (r"\bfaridabad(?:\s*sector\s*2\b)?|\bsector\s*2\s*,?\s*faridabad\b", "<hub:faridabad_sec2>"),
    (r"\bnoida\b|\bsector\s*50\b", "<hub:noida_sec50>"),
    (r"\brohini\b", "<hub:rohini>"),
    (r"(<hub:\w+>)(?:\s*,?\s*\1)+", r"\1"),                    # "sector 62 golf course" -> one tag
]]
HUB_TAG_RX = re.compile(r"<hub:(\w+)>")


def _own_hospital_ok(text: str, m: re.Match) -> bool:
    before = text[max(0, m.start() - 15):m.start()]
    after = text[m.end():m.end() + 40]
    return not (_WEAK_BEFORE.search(before) or _WEAK_AFTER.search(after))


def normalize(text: str) -> str:
    """Lower-case, Devanagari -> Roman, harmonize spellings and insert standard tags."""
    t = unicodedata.normalize("NFC", str(text or "")).translate(_DEVANAGARI_DIGITS)
    t = _DEVANAGARI_WORD.sub(lambda m: DEV_WORDS.get(m.group(0), m.group(0)), t)
    t = t.lower()
    for rx, rep in _ROMAN_RULES:
        t = rx.sub(rep, t)
    t = _PB_STRONG.sub(PB_TAG, t)
    t = _PB_LAUNCH.sub(lambda m: f"{PB_TAG} {m.group(0)}", t)
    t = _PB_WEAK.sub(lambda m: PB_TAG if _own_hospital_ok(t, m) else m.group(0), t)
    for rx, rep in _HUB_RULES:
        t = rx.sub(rep, t)
    return t.strip()


@dataclass
class Turn:
    idx: int
    speaker: str        # AGENT | CUSTOMER | UNKNOWN
    text: str           # verbatim
    norm: str           # harmonized


def speaker_of(raw: str) -> str:
    s = str(raw or "").strip().lower()
    if s.startswith("agent") or s in ("a", "spk_0", "speaker_0", "executive", "advisor"):
        return "AGENT"
    if s.startswith("cust") or s in ("c", "spk_1", "speaker_1", "client", "caller"):
        return "CUSTOMER"
    return "UNKNOWN"


def harmonize(turns: list[dict]) -> list[Turn]:
    """Raw API turns -> AGENT/CUSTOMER turns with verbatim + normalized text. Empty turns are dropped."""
    out: list[Turn] = []
    for t in turns or []:
        text = " ".join(str(t.get("text") or "").split())
        if not text:
            continue
        out.append(Turn(len(out), speaker_of(t.get("speakerId") or t.get("speaker")), text, normalize(text)))
    return out


# --------------------------------------------------------------------------- #
# 2. Hospital window
# --------------------------------------------------------------------------- #
WINDOW_BEFORE, WINDOW_AFTER, WINDOW_EXTEND, WINDOW_MAX = 1, 6, 3, 20
_TOPIC = _rx(
    r"<pb_hospital>", r"<hub:", r"\bhospital\b", r"\bdoctors?\b", r"\bclinic\b", r"\bopd\b", r"\bsurger(?:y|ies)\b",
    r"\bicu\b", r"\bdiscount", r"\bapp\b", r"\bcent(?:re|er)\b", r"\bbranch\b", r"\blocation\b", r"\bconsult",
    r"\bcheck\s*-?\s*up\b", r"\btests?\b", r"\bgurgaon\b", r"\bmultispeciality\b",
)


def hospital_window(turns: list[Turn]) -> list[bool]:
    n = len(turns)
    inside = [False] * n
    for a, t in enumerate(turns):
        if PB_TAG not in t.norm:
            continue
        hi, cap = min(n - 1, a + WINDOW_AFTER), min(n - 1, a + WINDOW_MAX)
        j = max(0, a - WINDOW_BEFORE)
        while j <= hi:
            inside[j] = True
            if j > a and _TOPIC.search(turns[j].norm):
                hi = min(cap, max(hi, j + WINDOW_EXTEND))
            j += 1
    return inside


# --------------------------------------------------------------------------- #
# 3a. Agent-side story elements
# --------------------------------------------------------------------------- #
ELEMENT_RX: dict[str, re.Pattern] = {
    "multispeciality": _rx(
        r"\bmultispeciality\b", r"\bsuperspeciality\b", r"\bfull\s*(?:fledged|fledge|fleged)?\s*hospital\b",
        r"\b(?:proper|poora|pura|complete|bada)\s*hospital\b", r"\bicu\b", r"\boperation\s*theat(?:er|re)s?\b",
        r"\bday\s*-?\s*care\b", r"\b(?:ipd|inpatient|in\s*-?\s*patient)\b",
        r"\b(?:surgery|surgeries|operations?)\s*(?:bhi|bhee|also|sab|tak|ki\s*facility|hoti|hote|hota)\b",
        r"\b(?:admission|admit|bharti)\s*(?:bhi|bhee|also|hota|hoti|ho\s*sakte|kar\s*sakte|ki\s*facility)\b",
        r"\b(?:sirf|only|just)\s*(?:ek\s*)?(?:clinic|opd)\s*(?:nahi|nhi|nahin)\b", r"\bclinic\s*(?:nahi|nhi|nahin)\b",
        r"\bnot\s*(?:just|only)\s*(?:a\s*)?(?:clinic|opd)\b",
    ),
    "ethical": _rx(
        r"\bsalar(?:y|ies)\b", r"\bsalaried\b", r"\bno\s*(?:revenue\s*)?targets?\b",
        r"\b(?:koi|koyi)\s*(?:bhi\s*)?targets?\s*(?:nahi|nhi|nahin)\b", r"\btargets?\s*(?:nahi|nhi|nahin)\b",
        r"\bcommission\b", r"\bincentive\b", r"\bover\s*-?\s*charg\w*", r"\bunnecessary\b", r"\bethical\w*\b",
        r"\b(?:faltu|fuzool|fizool|bekar|bewajah|be\s*wajah|bina\s*matlab|bina\s*wajah|extra)\s*(?:ke\s*|ka\s*|ki\s*)?"
        r"(?:test|tests|operation|operations|surgery|surgeries|charges?|bill|billing|dawai|medicines?)\b",
        r"\b(?:zyada|jyada|jada|extra)\s*(?:paisa|paise|charge|charges|bill|billing)\s*(?:nahi|nhi|nahin)\b",
        r"\bloot\w*\b", r"\bhonest\w*\b", r"\btransparen\w*\b",
    ),
    "zero_wait": _rx(
        r"\b(?:no|zero|bina|koi|without)\s*(?:waiting|wait|queue|line)\b",
        r"\bwaiting\s*(?:time|nahi|nhi|nahin|zero|kam|nahi\s*hai)\b", r"\bwait\s*(?:nahi|nhi)\s*(?:karna|karni|karte|krna)\b",
        r"\b(?:intezaar|intzaar|intezar|intjar|intazar)\b",
        r"\b(?:line|queue|q|lain)\s*(?:me|mein|main|mai)?\s*(?:nahi|nhi|khade|khada|lagna|lagne|lagana)\b",
        r"\bpre\s*-?\s*book\w*\b", r"\b(?:online|app\s*se|app\s*par|app\s*pe)\s*(?:appointment|booking|book|slot)\b",
        r"\bslots?\s*book\w*\b", r"\bappointment\s*(?:book|le|fix)\w*\b", r"\bdigital\w*\b", r"\bemr\b",
        r"\bcheck\s*-?\s*in\b",
    ),
    "app": _rx(
        r"<pb_hospital>\s*(?:ka|ki|ke)?\s*(?:app|application)\b", r"\b(?:app|application)\s*(?:download|install)\w*",
        r"\b(?:download|install)\w*\s*(?:kar\w*\s*)?(?:<pb_hospital>\s*)?(?:ka\s*)?(?:app|application)\b",
        r"\bplay\s*store\b", r"\bapp\s*store\b", r"\blink\s*(?:bhej|send|share)\w*", r"\b(?:bhej|send|share)\w*\s*(?:\w+\s*){0,2}link\b",
    ),
    "family_discount": _rx(r"\bdiscount\w*\b", r"\b(?:chhoot|chhut|choot)\b"),
    "cashless": _rx(r"\bcashless\b", r"\b(?:zero|no|koi|bina)\s*deductions?\b", r"\bdeductions?\s*(?:nahi|nhi|nahin)\b"),
}
# a discount line only counts as the hospital family discount when it is about
# family / hospital services (not a premium discount for a 2-year policy)
_DISCOUNT_CONTEXT = _rx(
    r"\bfamily\b", r"\bparivaar\b", r"\bparivar\b", r"\bghar\s*(?:walon|wale|waalon)\b", r"\bexclusive\b",
    r"\bconsult\w*", r"\btests?\b", r"\bcheck\s*-?\s*ups?\b", r"<pb_hospital>", r"\bhospital\b", r"\bopd\b",
    r"\bdoctors?\b", r"\bmembers?\b", r"\bparents?\b", r"\bbach\w*\b", r"\bwife\b", r"\bhusband\b",
    r"\bmummy\b", r"\bpapa\b", r"\bmedicines?\b", r"\bpharmacy\b", r"\bdiagnostic\w*\b", r"\blab\b",
)
# Wrong framing: describing PB Hospital as a clinic / OPD pass / wellness card.
_CLINIC_FRAMING = _rx(
    r"\bopd\s*(?:pass|card|coupon|plan|membership|wallet|voucher|package|cover)\b",
    r"\bwellness\s*(?:pass|card|coupon|voucher|cent(?:re|er)|program\w*)\b",
    r"\b(?:sirf|only|bas|just|keval|kewal)\s*opd\b(?!\s*(?:nahi|nhi|nahin))",
)
_CLINIC_WORD = re.compile(r"\bclinic\b", FLAGS)
_NEG_AFTER = _rx(r"^\W*(?:(?:hi|bhi|to|toh|bilkul)\W+)?(?:nahi|nhi|nahin|na|not|se\s*(?:zyada|bada|badhkar|upar|behtar))\b")
_NEG_BEFORE = _rx(r"\b(?:not|nahi|nhi|no|koi)\W*(?:\w+\W+)?$")


def _clinic_framing(norm: str) -> re.Match | None:
    m = _CLINIC_FRAMING.search(norm)
    if m:
        return m
    for m in _CLINIC_WORD.finditer(norm):
        if not (_NEG_AFTER.search(norm[m.end():m.end() + 25]) or _NEG_BEFORE.search(norm[max(0, m.start() - 25):m.start()])):
            return m
    return None


# --------------------------------------------------------------------------- #
# 3b. Customer-side doubts
# --------------------------------------------------------------------------- #
_BIG_HOSPITALS = (r"\b(?:max\b(?!\s*(?:bupa|life|cover|limit|amount|sum|tak|kitna|\d))|fortis|apollo\b(?!\s*munich)|medanta|"
                  r"artemis|manipal\b(?!\s*cigna)|aiims|ganga\s*ram|paras|narayana|blk|moolchand|sarvodaya|yatharth|marengo)")
DOUBT_RX: dict[str, re.Pattern] = {
    "scope": _rx(
        r"\b(?:sirf|only|bas|just|keval|kewal)\s*(?:ek\s*)?(?:clinic|opd|consultation|checkup|check\s*up)\b",
        r"\bclinic\s*(?:hai|h|he)?\s*(?:kya|ya)\b", r"\bhospital\s*(?:hai\s*)?ya\s*clinic\b",
        r"\b(?:surgery|surgeries|operation|icu|admit|admission|bharti|emergency|delivery|ipd|dialysis)\b.{0,40}"
        r"\b(?:hoti|hota|hogi|hoga|hote|ho\s*(?:sakti|sakta|jayegi|jayega|jaati|jata)|milegi|milega|available|possible|facility|karte|karti|karenge)\b",
        r"\b(?:kya|kia)\b.{0,25}\b(?:surgery|operation|icu|admit|emergency|delivery)\b",
        r"\b(?:real|proper|pura|poora|full|bada)\s*hospital\b", r"\b(?:kitne|kitna)\s*(?:bed|beds|bistar)\b",
        r"\bis\s*it\s*(?:a\s*)?(?:clinic|real\s*hospital|proper\s*hospital)\b",
        r"\bdo\s*you\s*(?:do|have)\s*(?:surger(?:y|ies)|icu|operations?)\b",
    ),
    "trust": _rx(
        r"\b(?:kaun|kon|kaunse|konse|kaunsa|konsa)\s*(?:se|si|sa)?\s*doctors?\b",
        r"\bdoctors?\b.{0,25}\b(?:kaun|kon|kaise|kese|kaisa|achhe|ache|acche|senior|junior|experienced|qualified|qualification|degree)\b",
        # Max / Fortis only count when compared or named as "where we go", not "cashless at Max?"
        _BIG_HOSPITALS + r".{0,25}\b(?:jaisa|jaise|jaisi|se\s*(?:achha|acha|accha|better|behtar)|level|compare|better|behtar|"
        r"jaate|jate|jaata|jata|jaati|dikhate|dikhata|ilaaj|ilaj|treatment)\b",
        r"\b(?:jaisa|jaise|jaisi|compare\w*|better|behtar|versus|vs)\b.{0,15}" + _BIG_HOSPITALS,
        r"\b(?:bharosa|bharose|bharosemand|bhrosa|trust|reliable)\b",
        r"\b(?:naya|nayi|new)\s*(?:hai|hospital|<pb_hospital>)\b", r"\b(?:kabhi|pehle)\s*(?:naam\s*)?(?:nahi|nhi)\s*suna\b",
        r"\bnever\s*heard\b",
        r"\b(?:quality|treatment|ilaaj|ilaj)\s*(?:kaisi|kaisa|kaise|kya)\b", r"\b(?:reviews?|ratings?)\b",
        r"\b(?:hospital|<pb_hospital>|doctors?)\s*(?:achha|acha|accha|achchha|theek)\s*(?:hai|h|hoga|hain)\b",
    ),
    "location": _rx(
        r"\b(?:bahut|bohot|bahot|kaafi|kafi|itna|itni|zyada|jyada|too|very)\s*(?:door|dur|duur|far)\b",
        r"\b(?:door|dur|duur|far)\s*(?:hai|h|he|padega|padta|pdega|hoga|ho\s*jayega|away|from)\b",
        r"\b(?:kahan|kaha|kidhar)\s*(?:par|pe|pr)?\s*(?:hai|h|hain|he|padta|padega|located)\b", r"\bwhere\s*is\b",
        r"\b(?:kahan|kidhar|kis\s*jagah)\b.{0,25}(?:<pb_hospital>|<hub:|\bhospital\b|\bcent(?:re|er)\b|\bbranch\b)",
        r"\b(?:nazdeek|najdeek|nearby|near\s*me|near\s*my|closest|nearest)\b",
        r"\b(?:ghar|area|yahan|yaha|idhar)\s*(?:ke|se)?\s*(?:paas|pass)\b",
        r"(?:<hub:\w+>|\bgurgaon|\bdelhi)\s*(?:tak\s*)?(?:kaun|kon)\s*(?:jayega|jaayega|jaega|aayega)\b",
        r"\b(?:aana\s*jaana|aane\s*jaane|commute)\b",
        r"\b(?:koi\s*)?branch\b.{0,20}\b(?:hai\s*kya|nahi|kahan|kaha)\b",
    ),
    "cashless": _rx(
        r"\bcashless\b",
        r"\b(?:meri|mera|my|existing|purani|purana|current|already|pehle\s*se)\s*(?:wali\s*|wala\s*)?(?:policy|insurance|mediclaim|card|plan)\b"
        r".{0,50}\b(?:chalegi|chalega|chalti|valid|work|kaam|accept|lagegi|lagega|use|cover|apply)\w*",
        r"\b(?:star|hdfc|ergo|care|niva|bupa|icici|lombard|bajaj|allianz|sbi|tata|aig|aditya\s*birla|new\s*india|national|oriental|"
        r"united|reliance|cholamandalam|iffcotokio|cigna|cghs|esic?|ayushman|government)\b.{0,40}"
        r"\b(?:chalegi|chalega|valid|accept|work|lagegi|lagega|cover|use)\w*",
        r"\b(?:network|empanel\w*|tie\s*-?\s*up|tieup)\b",
        r"\b(?:insurance|policy|claim|mediclaim)\b.{0,30}\b(?:chalegi|chalega|lagegi|lagega|valid|accept|use\s*ho|kaam\s*karegi)\b",
        r"\breimburse\w*\b",
    ),
    "discount": _rx(
        r"\b(?:discount|chhoot|chhut|choot)\w*\b.{0,30}\b(?:kaise|kese|kaisa|kab|kitna|kitni|kitne|kya|kahan|kaha|how|what)\b",
        r"\b(?:kaise|kese|kitna|kitni|kitne|kab|how\s*much|what)\b.{0,30}\b(?:discount|chhoot|chhut|percent)\w*",
        r"\b(?:family|parivaar|parivar|ghar\s*walon|ghar\s*wale|mummy|papa|parents?|maa|wife|husband|bachche|bachchon|bacchon|bete|beti)\b"
        r".{0,25}\b(?:ko|ke|ki)\s*(?:liye\s*)?(?:bhi|bhee)\b.{0,20}\b(?:milega|milegi|milta|discount|chalega|valid|use)\b",
        r"\b(?:card|code|coupon|voucher|membership)\b.{0,20}\b(?:milega|milegi|chahiye|kaise|kahan|lagega|lena)\b",
        r"\bhow\s*(?:do|will|to|can)\s*(?:i|we)?\s*(?:get|avail|claim|use)\b.{0,20}\bdiscount\b",
    ),
    "skeptic": _rx(
        r"\b(?:not|nahi|nhi|no)\s*interest\w*\b", r"\binterest\w*\s*(?:nahi|nhi|nahin|not)\b",
        r"\b(?:zarurat|zaroorat|jarurat|jaroorat|need|requirement)\s*(?:nahi|nhi|nahin|not)\b",
        r"\b(?:nahi|nhi|no)\s*(?:zarurat|zaroorat|jarurat|need)\b",
        r"\baage\s*(?:chalo|chaliye|chalte|badho|badhiye|badhte|bado|nikalo)\b",
        r"\b(?:chhodo|chodo|chhodiye|chodiye|rehne\s*do|rehne\s*dijiye|rahne\s*do|rahne\s*dijiye|skip)\b",
        r"\b(?:baad\s*(?:me|mein|main)|later)\s*(?:dekh|soch|baat|batata|batayenge|karenge)\w*",
        r"\b(?:sochunga|sochenge|soch\s*ke\s*bata\w*|soch\s*kar\s*bata\w*|think\s*about\s*it)\b",
        r"\b(?:fraud|scam|fake|dhokha|dhoka|farzi)\b",
        r"\b(?:kyun|kyu|kyon|why)\s*(?:jaun|jau|jaaun|jaana|jayenge|jaye|jaunga|go)\b",
        r"\b(?:already|pehle\s*se|apna)\s*(?:family\s*)?doctor\b", r"\btime\s*(?:nahi|nhi)\s*(?:hai|h)\b",
        r"\bjaldi\s*(?:bolo|bataiye|batao|karo|kariye)\b", r"\bpoint\s*(?:pe|par)\s*aa\w*\b",
    ),
}

_TRIVIAL = _rx(r"^\W*(?:(?:ji|jee|haan|han|ha|hanji|haanji|ok|okay|okk|achha|acha|accha|hmm+|hm|sir|maam|madam|yes|right|"
               r"theek|thik|hai|h|bilkul|sure)\b\W*)+$")
# A doubt match is dropped when the words right around it show it is about the policy, not the hospital
# ("surgery cover hai?", "2 saal pe kitna discount?").
DOUBT_VETO: dict[str, re.Pattern] = {
    "scope": _rx(r"\bcover\w*", r"\bclaim\w*", r"\bpolicy\b", r"\binsurance\b", r"\bpremium\b", r"\bwaiting\s*period\b"),
    "discount": _rx(r"\bpremium\b", r"\bsaal\b", r"\byears?\b", r"\bemi\b", r"\bpolicy\b", r"\bncb\b", r"\brenewal\b"),
}
QUOTE_MAX = 320


@dataclass
class Evidence:
    turn: int
    customer: str
    agent: str


@dataclass
class TranscriptFacts:
    pitched: bool = False
    any_mention: bool = False
    hubs: list[str] = field(default_factory=list)          # HUBS keys, in order of HUBS
    generic_gurgaon: bool = False
    elements: dict[str, bool] = field(default_factory=lambda: {k: False for k in ELEMENTS})
    element_quotes: dict[str, str] = field(default_factory=dict)
    hub_quotes: dict[str, str] = field(default_factory=dict)
    pitch_line: str = ""
    doubts: dict[str, list[Evidence]] = field(default_factory=dict)
    agent_turns: int = 0
    customer_turns: int = 0


def _excerpt(text: str, norm: str, m: re.Match | None, limit: int = QUOTE_MAX) -> str:
    """Verbatim turn, trimmed around the match if it is long."""
    if len(text) <= limit:
        return text
    centre = int(len(text) * (m.start() / max(len(norm), 1))) if m else 0
    start = max(0, min(centre - limit // 2, len(text) - limit))
    s = text[start:start + limit]
    return ("…" if start else "") + s.strip() + ("…" if start + limit < len(text) else "")


def _agent_reply(turns: list[Turn], after: int, lookahead: int = 4) -> str:
    """The agent's answer to a customer turn: next non-trivial AGENT turn(s)."""
    parts: list[str] = []
    for t in turns[after + 1: after + 1 + lookahead]:
        if t.speaker == "AGENT":
            if not parts and len(t.norm) < 40 and _TRIVIAL.match(t.norm):
                continue
            parts.append(t.text)
            if sum(len(p) for p in parts) >= 120:
                break
        elif parts:
            break
    reply = " ".join(parts)
    return reply if len(reply) <= QUOTE_MAX else reply[:QUOTE_MAX].rstrip() + "…"


def analyze_turns(turns: list[Turn], max_evidence: int = 3) -> TranscriptFacts:
    f = TranscriptFacts()
    f.agent_turns = sum(t.speaker == "AGENT" for t in turns)
    f.customer_turns = sum(t.speaker == "CUSTOMER" for t in turns)
    inside = hospital_window(turns)
    hubs: dict[str, None] = {}

    for t, in_w in zip(turns, inside):
        has_tag = PB_TAG in t.norm
        f.any_mention |= has_tag
        if t.speaker == "AGENT":
            if has_tag and not f.pitched:
                f.pitched = True
                f.pitch_line = _excerpt(t.text, t.norm, re.search(re.escape(PB_TAG), t.norm))
            if not in_w:
                continue
            for hm in HUB_TAG_RX.finditer(t.norm):
                key = hm.group(1)
                if key in HUBS and key not in hubs:
                    hubs[key] = None
                    f.hub_quotes[key] = _excerpt(t.text, t.norm, hm)
            if re.search(r"\bgurgaon\b", t.norm):
                f.generic_gurgaon = True
            for el, rx in ELEMENT_RX.items():
                m = rx.search(t.norm)
                if el == "family_discount" and m and not _DISCOUNT_CONTEXT.search(t.norm):
                    m = None
                if m:
                    f.elements[el] = True
                    f.element_quotes.setdefault(el, _excerpt(t.text, t.norm, m))
            m = _clinic_framing(t.norm)
            if m:
                f.elements["clinic_framing"] = True
                f.element_quotes.setdefault("clinic_framing", _excerpt(t.text, t.norm, m))
        elif t.speaker == "CUSTOMER" and in_w:
            for key, rx in DOUBT_RX.items():
                m = rx.search(t.norm)
                if m and key in DOUBT_VETO and DOUBT_VETO[key].search(t.norm[max(0, m.start() - 20):m.end() + 20]):
                    m = None
                if not m:
                    continue
                ev = f.doubts.setdefault(key, [])
                if len(ev) < max_evidence:
                    ev.append(Evidence(t.idx, _excerpt(t.text, t.norm, m), _agent_reply(turns, t.idx)))

    f.hubs = [h for h in HUBS if h in hubs]
    f.generic_gurgaon = f.generic_gurgaon and not f.hubs
    return f


@dataclass
class CallFacts:
    call_id: str
    meta: dict
    facts: TranscriptFacts
    turns: list[Turn]                 # primary harmonized transcript (for the dialogue export)
    source_transcript: str            # english | hindi | none


def _merge(primary: TranscriptFacts, other: TranscriptFacts) -> TranscriptFacts:
    """OR-merge facts from the Hindi transcript into the primary one (quotes from primary first)."""
    p = primary
    p.pitched |= other.pitched
    p.any_mention |= other.any_mention
    p.pitch_line = p.pitch_line or other.pitch_line
    p.hubs = [h for h in HUBS if h in set(p.hubs) | set(other.hubs)]
    p.generic_gurgaon = (p.generic_gurgaon or other.generic_gurgaon) and not p.hubs
    for k, v in other.elements.items():
        p.elements[k] = p.elements.get(k, False) or v
    for k, v in other.element_quotes.items():
        p.element_quotes.setdefault(k, v)
    for k, v in other.hub_quotes.items():
        p.hub_quotes.setdefault(k, v)
    for k, ev in other.doubts.items():
        p.doubts.setdefault(k, ev)
    return p


def analyze_call(call_id: str, english: list[dict], hindi: list[dict] | None = None,
                 meta: dict | None = None) -> CallFacts:
    en, hi = harmonize(english), harmonize(hindi or [])
    if en:
        facts, turns, src = analyze_turns(en), en, "english"
        if hi:
            facts = _merge(facts, analyze_turns(hi))
    elif hi:
        facts, turns, src = analyze_turns(hi), hi, "hindi"
    else:
        facts, turns, src = TranscriptFacts(), [], "none"
    return CallFacts(str(call_id), meta or {}, facts, turns, src)
