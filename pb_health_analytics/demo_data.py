"""
Synthetic call generator for OFFLINE / DEMO use only.

The portal is only reachable from the PB network. This module produces
realistic-looking Hinglish call transcripts (with the skews we suspect: heavy
Gurgaon bias, weak app push) so the classifier, dashboard and deck can be
exercised end to end without network access. Every demo call is stored with
source='demo' and the dashboard shows a banner whenever demo rows are present.
Never mix demo rows into a real baseline - use a separate DB (PB_DB_PATH) or
`python analyzer.py --purge-demo`.
"""
from __future__ import annotations

import random
import zlib
from datetime import date, timedelta

import config

TEAMS = {
    "Health Fresh - Gurgaon": ["Rahul Sharma", "Neha Verma", "Amit Yadav", "Pooja Singh", "Vikas Kumar"],
    "Health Fresh - Noida": ["Sandeep Gupta", "Anjali Mishra", "Rohit Chauhan", "Kavita Rawat"],
    "Health Renewal - NCR": ["Manish Tiwari", "Priya Saxena", "Deepak Joshi", "Sneha Kapoor", "Arjun Mehta"],
    "Health Term Combo": ["Farhan Ali", "Ritu Bansal", "Gaurav Malhotra"],
}
# (customer phrase, metadata city)
REGIONS = [
    ("main Noida sector 75 mein rehta hoon", "Noida"),
    ("hum Ghaziabad Indirapuram mein hain", "Ghaziabad"),
    ("Gurgaon sector 45 mein ghar hai", "Gurgaon"),
    ("Sohna Road pe rehte hain", "Gurgaon"),
    ("Faridabad sector 15 mein hoon", "Faridabad"),
    ("Rohini sector 9 se baat kar raha hoon", "Delhi"),
    ("Janakpuri, West Delhi", "Delhi"),
    ("Laxmi Nagar, East Delhi mein", "Delhi"),
    ("Dwarka sector 12", "Delhi"),
    ("Saket, South Delhi", "Delhi"),
]
HUB_LINES = {
    "IFFCO Chowk": "Hamara flagship hospital IFFCO Chowk Gurgaon mein hai",
    "Sector 62": "ek branch Golf Course Extension, Sector 62 Gurgaon mein bhi hai",
    "Faridabad": "Faridabad Sector 2 mein bhi hamara hospital hai",
    "Noida": "Noida Sector 50 mein bhi centre hai",
    "Rohini": "Delhi mein Rohini mein bhi hamara hospital hai",
}
HUB_WEIGHTS = {"IFFCO Chowk": 0.55, "Sector 62": 0.2, "Faridabad": 0.07, "Noida": 0.1, "Rohini": 0.08}

PILLAR_LINES = {
    "multispeciality": ["Ye sirf clinic nahi hai sir, full multispeciality hospital hai, ICU aur OT sab hai.",
                        "Multispeciality hospital hai, daycare surgery bhi hoti hai wahan."],
    "ethical": ["Wahan doctors salary based hain, koi target nahi hai, toh overcharge ka sawal hi nahi.",
                "Doctors fixed salary pe hain sir, faltu test ya operation nahi likhte."],
    "zero_wait": ["Waiting time zero hai, app se pre-book karke seedha doctor se milte hain.",
                  "Line mein khade nahi hona padta, online appointment hota hai."],
    "app": ["Aap PB Health app download kar lijiye Play Store se, wahan sab booking ho jaati hai.",
            "Main link bhej raha hoon, PB Health app install kar lijiye."],
    "family_discount": ["Aapko aur aapki family ko consultation aur tests pe exclusive discount milta hai.",
                        "Family discount bhi hai sir, parivaar walon ko bhi chhoot milti hai."],
    "top_doctors": ["Senior specialists hain - cardiology, ortho, gynecology sab."],
    "cashless": ["Aur Policybazaar ke saath poora cashless hai, zero deduction."],
}
OBJECTION_LINES = {
    "location_distance": ["Gurgaon toh bahut door hai mere liye, main Noida mein hoon.",
                          "Mere ghar ke paas koi branch hai kya? Itna door kaun jaayega."],
    "clinical_trust": ["Max ya Fortis jaisa hai kya? Doctors kaun hain wahan?",
                       "Naya hospital hai, bharosa kaise karein?"],
    "insurance_validity": ["Meri Star Health wali policy wahan chalegi kya cashless?",
                           "Mera existing HDFC Ergo insurance hai, wo valid hoga kya?"],
    "facility_scope": ["Wahan surgery bhi hoti hai kya? Ya sirf clinic hai?",
                       "Kya wahan ICU hai, emergency mein admit kar sakte hain?"],
    "discount_confusion": ["Discount kaise milega? Koi card milega kya?",
                           "Discount family ko bhi milega kya, kaise claim karna hai?"],
    "general_skepticism": ["Abhi zarurat nahi hai, main sochunga.", "Mujhe interest nahi hai abhi."],
}
FILLER = [
    ("agent", "Namaste sir, main Policybazaar se baat kar raha hoon, aapne health insurance ke liye enquiry ki thi."),
    ("customer", "Haan ji, bataiye."),
    ("agent", "Sir family mein kitne members ko cover karna hai aur kisi ko koi pre-existing disease hai?"),
    ("customer", "Main, wife aur do bacche. Papa ko sugar hai."),
    ("agent", "Theek hai sir, main aapko 10 lakh ka family floater suggest karunga, premium approx 22 hazaar aayega."),
]
CLOSE = [("customer", "Theek hai, aap details WhatsApp kar dijiye."),
         ("agent", "Bilkul sir, main abhi bhej deta hoon. Dhanyawaad.")]


def _ts(i: int) -> str:
    s = i * 17 + random.randint(0, 9)
    return f"{s // 60}:{s % 60:02d}"


def generate_call(call_id: int, day: date, rng: random.Random) -> tuple[dict, list[dict]]:
    team = rng.choice(list(TEAMS))
    agent = rng.choice(TEAMS[team])
    # agent "skill" makes some agents consistently better
    skill = (zlib.crc32(agent.encode()) % 100) / 100
    region_line, city = rng.choice(REGIONS)
    turns: list[tuple[str, str]] = list(FILLER[:2])
    turns.append(("customer", f"Ji, {region_line}."))
    turns += FILLER[2:]

    pitched = rng.random() < 0.55 + 0.3 * skill
    if pitched:
        turns.append(("agent", rng.choice([
            "Sir ek aur baat, Policybazaar ka khud ka hospital hai - PB Health Hospital.",
            "Aur sir, hamara apna hospital bhi hai, PB Health.",
            "Sir humara khud ka hospital hai Delhi NCR mein.",
        ])))
        if rng.random() < 0.6 + 0.3 * skill:
            hub = rng.choices(list(HUB_WEIGHTS), weights=list(HUB_WEIGHTS.values()))[0]
            turns.append(("agent", HUB_LINES[hub] + "."))
            if rng.random() < 0.25 + 0.4 * skill:
                extra = rng.choice([h for h in HUB_LINES if h != hub])
                turns.append(("agent", "Aur " + HUB_LINES[extra] + "."))
        probs = {"multispeciality": .5, "ethical": .35, "zero_wait": .3, "app": .18,
                 "family_discount": .4, "top_doctors": .3, "cashless": .45}
        for pillar, p in probs.items():
            if rng.random() < p + 0.35 * skill:
                turns.append(("agent", rng.choice(PILLAR_LINES[pillar])))
        obj_probs = {"location_distance": .22, "clinical_trust": .18, "insurance_validity": .15,
                     "facility_scope": .1, "discount_confusion": .12, "general_skepticism": .08}
        for obj, p in obj_probs.items():
            if rng.random() < p:
                turns.append(("customer", rng.choice(OBJECTION_LINES[obj])))
                turns.append(("agent", "Ji sir, main samjha deta hoon."))
    elif rng.random() < 0.2:
        turns.append(("customer", "Policybazaar ka koi hospital bhi hai kya?"))
        turns.append(("agent", "Ji sir, uski details main baad mein share kar dunga."))
    turns += CLOSE

    english = [{"speakerId": spk, "time": _ts(i), "timeStamp": i * 17000, "text": txt}
               for i, (spk, txt) in enumerate(turns)]
    meta = {
        "call_id": f"DEMO{call_id:07d}",
        "call_ts": f"{day.isoformat()} {rng.randint(9, 20):02d}:{rng.randint(0, 59):02d}:00",
        "agent_id": f"PW{zlib.crc32(agent.encode()) % 90000 + 10000}",
        "agent_name": agent, "team": team, "manager": team.split(" - ")[0] + " Mgr",
        "city": city, "state": "Delhi" if city == "Delhi" else ("Haryana" if city in ("Gurgaon", "Faridabad") else "Uttar Pradesh"),
        "talktime": rng.randint(150, 1100), "lead_id": str(rng.randint(10**8, 10**9)),
        "matched_terms": ["pb health"] if pitched else [], "audio_url": None, "source": "demo",
    }
    return meta, english


def generate(start: date, end: date, calls_per_day: int = 60, seed: int = 7):
    rng = random.Random(seed + start.toordinal())
    random.seed(seed)
    cid = start.toordinal() * 1000
    day = start
    while day <= end:
        n = int(calls_per_day * rng.uniform(0.8, 1.2))
        for _ in range(n):
            cid += 1
            yield generate_call(cid, day, rng)
        day += timedelta(days=1)


def demo_denominator(n_analyzed: int, rng_seed: int) -> int:
    """Pretend ~5x more qualified NCR calls happened than were caught by the hospital search."""
    return int(n_analyzed * random.Random(rng_seed).uniform(3.5, 5.0))
