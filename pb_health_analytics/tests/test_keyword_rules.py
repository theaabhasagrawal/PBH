from keyword_rules import CURRENT_ROWS, PHRASE_ROWS, WORD_ROWS, TOKEN, hit, rows


def call(text):
    toks = TOKEN.findall(text.lower())
    return {"tokens": set(toks), "seq": " " + " ".join(toks) + " "}


def test_discount_talk_is_not_a_pitch_under_new_rules():
    c = call("is plan mein aapko das percent ka discount milega aur claims bhi jaldi settle hote hai")
    assert hit(rows(CURRENT_ROWS), c)          # the old list flags it
    assert not hit(rows(PHRASE_ROWS), c)
    assert not hit(rows(WORD_ROWS), c)


def test_real_pitch_lines_are_caught():
    for line in ["policy bazaar ka khud ka bhi hospital khul gaya hai m g road pe",
                 "humara p b health hospital gurgaon mein open ho gaya hai",
                 "iffco chowk pe hospital open hua hai policybazaar ka"]:
        assert hit(rows(PHRASE_ROWS), call(line)), line


def test_phrases_need_adjacent_words():
    # "khud" and "hospital" far apart is not the phrase "khud ka hospital"
    assert not hit([("khud ka hospital",)], call("aap khud ka plan dekh lo, network mein hospital bahut hai"))
