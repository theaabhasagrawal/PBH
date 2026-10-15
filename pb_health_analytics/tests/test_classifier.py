from classifier import classify_call


def turns(*pairs):
    return [{"speakerId": s, "time": f"0:{i:02d}", "text": t} for i, (s, t) in enumerate(pairs)]


def test_full_pitch_scores_100_when_nearest_hub_named():
    t = turns(
        ("customer", "Main Noida sector 75 mein rehta hoon"),
        ("agent", "Sir Policybazaar ka khud ka hospital hai, PB Health, multispeciality hospital hai ICU ke saath."),
        ("agent", "Noida Sector 50 mein hamara centre hai."),
        ("agent", "Doctors salary based hain, koi target nahi, overcharge nahi karte."),
        ("agent", "Waiting time zero hai, pre-book kar sakte hain."),
        ("agent", "PB Health app download kar lijiye."),
        ("agent", "Aapki family ko exclusive discount milega."),
    )
    r = classify_call("1", t)
    assert r.pitched and r.nearest_hub == "Noida" and r.region_matched
    assert r.adherence_score == 100
    assert r.hubs_mentioned == ["Noida"]


def test_location_without_region_match_gets_base_points_only():
    t = turns(("customer", "Hum Rohini mein rehte hain"),
              ("agent", "Hamara apna hospital IFFCO Chowk Gurgaon mein hai"))
    r = classify_call("2", t)
    assert r.pitched and r.pillars["location"] and not r.region_matched
    assert r.adherence_score == 18
    assert r.nearest_hub == "Rohini"


def test_customer_mention_is_not_an_agent_pitch():
    t = turns(("customer", "Policybazaar ka koi hospital hai kya? PB health ke baare mein suna"),
              ("agent", "Ji details baad mein bhejta hoon"))
    r = classify_call("3", t)
    assert r.any_mention and not r.pitched and r.adherence_score == 0


def test_objections_detected_from_customer_turns_only():
    t = turns(("agent", "PB Health hospital hai, Max Fortis jaisa hi hai"),
              ("customer", "Gurgaon toh bahut door hai"),
              ("customer", "Meri Star Health policy wahan chalegi kya?"),
              ("customer", "Wahan surgery bhi hoti hai kya?"),
              ("customer", "Discount kaise milega?"))
    r = classify_call("4", t)
    assert set(r.objections) == {"location_distance", "insurance_validity", "facility_scope", "discount_confusion"}
    assert "clinical_trust" not in r.objections  # agent said "Max Fortis", not the customer


def test_sector_2_only_counts_as_faridabad_with_context():
    assert classify_call("5", turns(("agent", "apna hospital sector 2 mein hai"))).hubs_mentioned == []
    assert classify_call("6", turns(("agent", "apna hospital Faridabad sector 2 mein hai"))).hubs_mentioned == ["Faridabad"]


def test_devanagari_and_multiple_transcripts():
    hindi = turns(("agent", "हमारा अपना हॉस्पिटल है, फरीदाबाद में"))
    english = turns(("agent", "Please download the PB Health app"))
    r = classify_call("7", [english, hindi])
    assert r.pitched and r.pillars["app"] and "Faridabad" in r.hubs_mentioned


def test_metadata_city_fallback_for_region():
    r = classify_call("8", turns(("agent", "khud ka hospital hai, Noida sector 50")), metadata_city="Ghaziabad")
    assert r.nearest_hub == "Noida" and r.region_matched
