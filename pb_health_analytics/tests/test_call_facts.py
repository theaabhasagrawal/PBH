from call_facts import analyse_call, harmonise, normalise, pitch_tags


def turns(*pairs):
    return [{"speakerId": s, "time": f"0:{i:02d}", "text": t} for i, (s, t) in enumerate(pairs)]


def test_hinglish_variants_are_normalised():
    assert "policybazaar" in normalise("policy bazar ka hospital")
    assert "khud ka hospital" in normalise("khud ke hospital")
    assert "sector 62" in normalise("sec sixty two golf course")
    assert "pb health hospital" in normalise("baby health hospital ke naam se")


def test_backchannels_do_not_split_agent_blocks():
    blocks = harmonise(turns(("agent", "policybazaar ka khud ka"), ("customer", "haan ji"), ("agent", "hospital khula hai")))
    assert len(blocks) == 1 and blocks[0].speaker == "AGENT"


def test_pb_health_app_alone_is_not_a_hospital_pitch():
    f = analyse_call("1", turns(("agent", "pb health app download kijiye usme wellness programme milega")), [])
    assert not f.pitched and f.pb_health_said and f.elements["app"]


def test_network_hospitals_are_not_a_pitch():
    assert pitch_tags(normalise("with the listed policybazaar hospital aapko kuch nahi karna")) == []
    assert pitch_tags(normalise("aap apna hospital choose kar sakte hai network mein")) == []
    assert pitch_tags(normalise("policybazaar ne sir apne hospitals bhi type kar liye hai")) == []


def test_real_pitch_with_mg_road_and_claims():
    f = analyse_call("2", turns(
        ("agent", "policybazaar ka khud ka hospital khul gaya hai gurgaon m g road pe pb health ke naam se "
                  "consultation pe fifty percent ka discount milta hai"),
        ("customer", "noida mein kahan pe"),
        ("agent", "noida mein abhi khulne wala hai sir abhi gurgaon mein first hospital hai"),
    ), [])
    assert f.pitched
    assert "MG Road, Gurgaon (address only)" in f.locations and "Noida Sec 50" in f.locations
    assert {"% discount", "Other hubs 'coming soon'", "'First' hospital"} <= set(f.claims)
    assert f.doubts == ["location"] and f.doubt_quotes["location"] == "noida mein kahan pe"
    assert f.doubt_replies["location"].startswith("noida mein abhi khulne")


def test_not_far_is_not_location_friction():
    f = analyse_call("3", turns(("agent", "policybazaar ka khud ka hospital open hua hai m g road pe"),
                                ("customer", "zyada door nahi hai waise mere office se")), [])
    assert f.pitched and "location" not in f.doubts


def test_waiting_period_is_not_a_zero_wait_pitch():
    f = analyse_call("4", turns(("agent", "humara khud ka hospital hai aur policy mein waiting period do saal ka hai")), [])
    assert f.pitched and not f.elements["zero_wait"]


def test_bhi_and_on_fillers_still_count_as_a_pitch():
    for line in ["policy bazaar ka khud ka bhi hospital khul gaya hai",
                 "policy bazaar ne apna bhi hospital open kiya abhi gurgaon mein",
                 "policybazaar ne khud ka apna on hospital bhi open kiya"]:
        assert pitch_tags(normalise(line)), line
