import json
import re
from pathlib import Path

from deck_generator import DECK, FACTS
from pitch_card import card
from workbook import COUNTER_SCRIPTS, _objection

ROOT = Path(__file__).resolve().parents[1]
STATS = {"analysed": 1, "team_calls": 1, "period": "x", "scope_missing": 0, "ethical": 0}


def _plain(text):
    return re.sub(r"\s+", " ", re.sub(r"\*\*|</?b>", "", text)).strip()


def _playbook_script():
    src = (ROOT / "advisor_playbook.js").read_text()
    block = src[src.index("const SCRIPT_HI ="):src.index(";", src.index("const SCRIPT_HI ="))]
    return _plain("".join(re.findall(r'"((?:[^"\\]|\\.)*)"', block)))


def test_deck_pitch_card_and_playbook_use_the_same_script():
    script = _plain(card(STATS)["script"])
    assert _plain(DECK["hook"]["hinglish"]) == script
    assert _playbook_script() == script


def test_every_workbook_counter_script_finds_its_deck_card():
    for title, _ in COUNTER_SCRIPTS.values():
        assert _objection(title)[0] == title


def test_deck_has_no_unopened_hubs_or_app_push():
    text = json.dumps([DECK, FACTS]).lower()
    for stale in ("rohini", "sector 62", "golf course", "app ka link", "5 centres", "nearest hub", "integrated hai"):
        assert stale not in text, stale
