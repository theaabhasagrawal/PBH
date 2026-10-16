from call_facts import analyze_call, harmonize, hospital_window, normalize


def turns(*pairs):
    return [{"speakerId": s, "time": f"0:{i:02d}", "text": t} for i, (s, t) in enumerate(pairs)]


FILLER = [("agent", "Sir premium 18,000 aata hai saal ka."), ("customer", "Theek hai, aur kya kya cover hai?")] * 6


# ---------------- harmonization ----------------
def test_hinglish_variants_become_pitch_tags():
    assert normalize("Policybazaar ka khud ke hospital hai") == "<pb_hospital> hai"
    assert normalize("P B Health") == "<pb_hospital>"
    assert normalize("hamare apne hospital hain") == "<pb_hospital> hain"
    assert normalize("Policy Bazar ka hospitel") == "<pb_hospital>"
    assert normalize("pb ka hospital hai") == "<pb_hospital> hai"
    assert normalize("Policybazaar ka khud ka multispeciality hospital hai") == "<pb_hospital> hai"
    assert normalize("hamara ek naya multi-speciality hospital") == "<pb_hospital>"
    assert normalize("Policybazaar ne Gurgaon mein hospital khola hai") == "<pb_hospital> policybazaar ne gurgaon mein hospital khola hai"
    assert normalize("हमारा अपना हॉस्पिटल है।") == "<pb_hospital> hai।"


def test_your_choice_of_hospital_is_not_a_pitch():
    assert "<pb_hospital>" not in normalize("Aap apna hospital choose kar sakte hain network mein")
    assert "<pb_hospital>" not in normalize("aapka apna hospital select kijiye")
    assert normalize("apna hospital hai Gurgaon mein") == "<pb_hospital> hai gurgaon mein"


def test_hub_variants():
    assert normalize("IFFCO chauk") == "<hub:iffco_chowk>"
    assert normalize("Gurugram sec-62 golf course road") == "<hub:sector_62>"
    assert normalize("Faridabad sector २") == "<hub:faridabad_sec2>"
    assert normalize("noida sec 50") == "<hub:noida_sec50>"
    assert normalize("रोहिणी") == "<hub:rohini>"
    # Noida's own Sector 62 is Noida, not the Golf Course hub; IFFCO Tokio is an insurer
    assert normalize("noida sector 62") == "<hub:noida_sec50>"
    assert "<hub:" not in normalize("iffco tokio ki policy")


def test_speakers_are_separated_and_empty_lines_dropped():
    h = harmonize(turns(("Agent", "Namaste"), ("customer_1", "haan"), ("agent", "  "), ("bot", "beep")))
    assert [t.speaker for t in h] == ["AGENT", "CUSTOMER", "UNKNOWN"]
    assert [t.idx for t in h] == [0, 1, 2]


# ---------------- pitch facts ----------------
def test_full_story_pitch():
    c = analyze_call("1", turns(
        ("agent", "Sir ek important baat, Policybazaar ka khud ka multispeciality hospital hai, PB Health."),
        ("agent", "IFFCO Chowk aur Sector 62 Golf Course pe hai, ICU aur OT sab hai."),
        ("agent", "Doctors fixed salary pe hain, koi target nahi, toh overcharging ka sawal hi nahi."),
        ("agent", "App se slot book kijiye, line mein khade hone ki zarurat nahi."),
        ("agent", "PB Health app download kar lijiye, aapki family ko exclusive discount milega."),
        ("agent", "Cashless bhi poora integrated hai."),
    ))
    f = c.facts
    assert f.pitched and f.hubs == ["iffco_chowk", "sector_62"] and not f.generic_gurgaon
    assert all(f.elements[k] for k in ("multispeciality", "ethical", "zero_wait", "app", "family_discount", "cashless"))
    assert not f.elements["clinic_framing"]
    assert "Policybazaar ka khud ka multispeciality hospital" in f.pitch_line


def test_policy_talk_outside_the_hospital_window_is_not_counted():
    c = analyze_call("2", turns(
        ("agent", "Is plan mein cashless claim milega aur 2 saal lene pe family discount bhi."),
        ("agent", "Policybazaar app download kar lijiye policy documents ke liye."),
        *FILLER,
        ("agent", "Aur haan, Policybazaar ka apna hospital bhi hai Gurgaon mein."),
    ))
    f = c.facts
    assert f.pitched and f.generic_gurgaon and f.hubs == []
    assert not any(f.elements[k] for k in ("cashless", "family_discount", "app"))


def test_clinic_or_opd_pass_framing():
    c = analyze_call("3", turns(("agent", "PB Health ek OPD pass ki tarah hai, clinic hai Gurgaon mein.")))
    assert c.facts.elements["clinic_framing"] and not c.facts.elements["multispeciality"]
    ok = analyze_call("4", turns(("agent", "PB Health sirf clinic nahi hai, full hospital hai, ICU bhi hai.")))
    assert ok.facts.elements["multispeciality"] and not ok.facts.elements["clinic_framing"]


def test_hub_named_outside_window_does_not_count():
    c = analyze_call("5", turns(("agent", "Aap Faridabad se ho na?"), *FILLER, ("agent", "humara hospital bhi hai")))
    assert c.facts.pitched and c.facts.hubs == []


def test_customer_mention_is_not_an_agent_pitch():
    c = analyze_call("6", turns(("customer", "PB Health hospital ke baare mein suna tha"), ("agent", "Ji sir")))
    assert c.facts.any_mention and not c.facts.pitched


# ---------------- doubts ----------------
def test_each_doubt_bucket_with_agent_reply():
    c = analyze_call("7", turns(
        ("agent", "Policybazaar ka khud ka hospital hai, PB Health."),
        ("customer", "Sirf OPD clinic hai kya ya surgery bhi hoti hai?"),
        ("agent", "Ji."),
        ("agent", "Nahi sir, full multispeciality hospital hai, OT ICU sab hai."),
        ("customer", "Doctors kaun hain? Max jaisa hai kya?"),
        ("agent", "Senior specialists hain, fixed salary pe."),
        ("customer", "Gurgaon toh bahut door hai, main Rohini mein hoon."),
        ("agent", "Rohini mein bhi hamara centre hai sir."),
        ("customer", "Meri Star ki policy wahan chalegi? Cashless hoga?"),
        ("agent", "Main system mein check karke batata hoon."),
        ("customer", "Discount kaise milega, family ko bhi milega?"),
        ("agent", "App pe login karke booking kijiye."),
        ("customer", "Achha theek hai, aage chalo."),
    ))
    d = c.facts.doubts
    assert set(d) == {"scope", "trust", "location", "cashless", "discount", "skeptic"}
    assert d["scope"][0].customer == "Sirf OPD clinic hai kya ya surgery bhi hoti hai?"
    assert d["scope"][0].agent.startswith("Nahi sir, full multispeciality")   # trivial "Ji." skipped
    assert d["location"][0].agent == "Rohini mein bhi hamara centre hai sir."
    assert d["skeptic"][0].agent == ""                                        # call ended, no reply
    assert c.facts.hubs == ["rohini"]


def test_policy_questions_are_not_hospital_doubts():
    c = analyze_call("8", turns(
        ("agent", "PB Health hospital bhi hai hamara."),
        ("customer", "Surgery cover hai kya is policy mein?"),
        ("customer", "Max Bupa wali policy port ho jayegi?"),
        ("customer", "2 saal ka loon toh kitna discount milega?"),
        ("customer", "Maine kaha na pehle details bhejo."),
        ("customer", "so far theek hai"),
    ))
    assert set(c.facts.doubts) == set()


def test_doubts_outside_window_are_ignored():
    c = analyze_call("9", turns(("customer", "Not interested, aage chalo"), *FILLER, ("agent", "khud ka hospital hai")))
    assert c.facts.doubts == {}


def test_hindi_transcript_is_merged():
    english = turns(("agent", "Sir aapke liye ek baat."), ("customer", "haan boliye"))
    hindi = turns(("agent", "पॉलिसीबाज़ार का खुद का हॉस्पिटल है, नोएडा सेक्टर ५० में।"), ("customer", "कैशलेस होगा क्या?"))
    c = analyze_call("10", english, hindi)
    assert c.source_transcript == "english"
    assert c.facts.pitched and c.facts.hubs == ["noida_sec50"] and "cashless" in c.facts.doubts


def test_window_extends_while_talk_stays_on_hospital():
    t = harmonize(turns(("agent", "humara hospital hai"), *[("customer", "doctor kaun hai")] * 10, ("customer", "ok")))
    w = hospital_window(t)
    assert all(w[:11]) and len(w) == 12
