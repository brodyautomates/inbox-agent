"""
Run:  venv/bin/python3 -m unittest tests/test_modes.py
No network, no config file needed.
"""

import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# point config at a throwaway folder so tests never touch a real install
os.environ["INBOX_AGENT_HOME"] = tempfile.mkdtemp()
import json  # noqa: E402
with open(os.path.join(os.environ["INBOX_AGENT_HOME"], "config.json"), "w") as f:
    json.dump({"gmail_address": "you@example.com", "telegram_token": "x", "allowed_user": 1,
               "ceiling_amount": 5000, "never_answer_keywords": ["equity"]}, f)

from bot import modes  # noqa: E402


class Amounts(unittest.TestCase):
    def test_parses_k_and_commas(self):
        self.assertIn(7500.0, modes.amounts_in("we're at 7.5k for that"))
        self.assertIn(14250.0, modes.amounts_in("$14,250 broken into"))
        self.assertIn(8000.0, modes.amounts_in("let's land at 8k even"))

    def test_ceiling(self):
        self.assertTrue(modes.over_ceiling("we can do 5k", 5000))
        self.assertFalse(modes.over_ceiling("we can do 4.9k", 5000))
        self.assertFalse(modes.over_ceiling("3 videos over 2 weeks", 5000))


class Lookalike(unittest.TestCase):
    def test_flags_near_miss(self):
        self.assertTrue(modes.lookalike(["a@brand.example", "b@brnad.example"]))
        self.assertTrue(modes.lookalike(["a@acme-inc.example", "b@acme-lnc.example"]))

    def test_allows_related_and_unrelated(self):
        self.assertFalse(modes.lookalike(["a@brand.example", "b@brand-partners.example"]))
        self.assertFalse(modes.lookalike(["a@brand.example", "b@other.example"]))
        self.assertFalse(modes.lookalike(["a@brand.example", "b@brand.example"]))


class Assisted(unittest.TestCase):
    thread = [{"from": "x@example.com", "attachment": False}]

    def test_clean_short_reply_passes_filter(self):
        ok, why = modes.assisted_ok("Hi Sam,\n\nThanks for reaching out. I will come back to you with scope and pricing shortly.\n\nBest regards,\nAlex", self.thread)
        self.assertTrue(ok, why)

    def test_number_blocks(self):
        ok, why = modes.assisted_ok("We are at 5k for that.", self.thread)
        self.assertFalse(ok)
        self.assertIn("digit", why)

    def test_date_word_blocks(self):
        ok, why = modes.assisted_ok("Can we speak on Tuesday?", self.thread)
        self.assertFalse(ok)

    def test_attachment_blocks(self):
        ok, why = modes.assisted_ok("Received, thank you.", [{"attachment": True}])
        self.assertFalse(ok)


class HardStops(unittest.TestCase):
    def test_ceiling_and_keyword_and_escalate(self):
        stops = modes.hard_stops("We could do 6k with equity.", [{"from": "a@example.com"}], flagged_escalate=True)
        joined = " ".join(stops)
        self.assertIn("ceiling", joined)
        self.assertIn("equity", joined)
        self.assertIn("ESCALATE", joined)

    def test_clean_draft_has_no_stops(self):
        self.assertEqual(modes.hard_stops("Thanks, I will revert shortly.", [{"from": "a@example.com"}]), [])


if __name__ == "__main__":
    unittest.main()
