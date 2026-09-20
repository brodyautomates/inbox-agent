"""
The gate. Three modes, and the hard stops that hold in every one of them.

  manual     every draft waits for your tap. Default.
  assisted   a draft goes on its own only if it passes `assisted_ok`:
             no digits, no currency symbol, no date words, short, no
             attachment in the thread, and it matches one of the approved
             templates in playbook/assisted-templates.md.
  autopilot  every draft is posted with a countdown. No tap before it
             expires, it sends. HOLD parks it for you.

Hard stops (`hard_stops`) are checked in code, not in a prompt, and a draft
that trips one always waits for a human no matter the mode:
  - the drafter flagged it ESCALATE (calls, contracts, anything on the
    playbook's never-answer list)
  - any amount at or above `ceiling_amount`
  - a look-alike address in the thread
  - a keyword from `never_answer_keywords` in config
  - the stop file exists
"""

import re
from difflib import SequenceMatcher

from . import config as C

MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december", "jan", "feb", "mar", "apr",
          "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec")
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "tomorrow", "next week", "this week", "eow", "eod")
GENERIC_LOCALS = {"info", "hello", "hi", "contact", "team", "partnerships", "marketing",
                  "press", "support", "sales", "admin", "noreply", "no-reply"}


# ---------------------------------------------------------------- amounts

_AMOUNT = re.compile(
    r"(?<![\w.])(?:[$£€]\s?)?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?(k|K|thousand|m|M|million)?(?![\w.])")


def amounts_in(text):
    """Every number that could be money, normalised to a float."""
    out = []
    for num, suffix in _AMOUNT.findall(text or ""):
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        s = (suffix or "").lower()
        if s in ("k", "thousand"):
            v *= 1000
        elif s in ("m", "million"):
            v *= 1_000_000
        out.append(v)
    return out


def over_ceiling(text, ceiling):
    return any(v >= ceiling for v in amounts_in(text) if v >= 100)


# ---------------------------------------------------------------- look-alikes

def _domain(addr):
    return addr.split("@", 1)[1].lower() if "@" in addr else ""


def lookalike(addresses):
    """True if two different domains in the thread are suspiciously similar.
    'brand.com' vs 'brand-partners.com' is fine. 'brand.com' vs 'brnad.com' is not."""
    doms = sorted({_domain(a) for a in addresses if _domain(a)})
    for i in range(len(doms)):
        for j in range(i + 1, len(doms)):
            a, b = doms[i], doms[j]
            base_a, base_b = a.rsplit(".", 1)[0], b.rsplit(".", 1)[0]
            if base_a == base_b:
                continue
            ratio = SequenceMatcher(None, base_a, base_b).ratio()
            if ratio >= 0.8 and abs(len(base_a) - len(base_b)) <= 2:
                return True
    return False


# ---------------------------------------------------------------- the gate

def hard_stops(draft_body, thread, flagged_escalate=False):
    """List of reasons this draft must wait for a human. Empty list = free to go."""
    cfg = C.load()
    reasons = []
    if C.paused():
        reasons.append("stop file exists")
    if flagged_escalate:
        reasons.append("drafter flagged ESCALATE")
    if over_ceiling(draft_body, cfg["ceiling_amount"]):
        reasons.append(f"amount at or above ceiling {cfg['ceiling_amount']}")
    addrs = []
    for m in thread or []:
        for field in ("from", "to", "cc", "reply_to"):
            for part in (m.get(field) or "").split(","):
                part = part.strip()
                if "@" in part:
                    addrs.append(part[part.index("<") + 1:part.index(">")] if "<" in part else part)
    if lookalike(addrs):
        reasons.append("look-alike address in thread")
    low = (draft_body or "").lower()
    for kw in cfg.get("never_answer_keywords") or []:
        if kw.lower() in low:
            reasons.append(f"never-answer keyword: {kw}")
            break
    return reasons


def assisted_ok(draft_body, thread, llm_ask=None):
    """The narrow filter for assisted mode. Returns (ok, reason)."""
    cfg = C.load()
    body = draft_body or ""
    low = body.lower()
    if re.search(r"\d", body):
        return False, "contains a digit"
    if any(sym in body for sym in cfg["currency_symbols"]):
        return False, "contains a currency symbol"
    words = re.findall(r"[a-z']+", low)
    if len(words) > cfg["assisted_max_words"]:
        return False, f"over {cfg['assisted_max_words']} words"
    for w in MONTHS + DAYS:
        if re.search(rf"\b{re.escape(w)}\b", low):
            return False, f"contains a date word: {w}"
    if any(m.get("attachment") for m in thread or []):
        return False, "attachment in thread"
    if llm_ask:
        try:
            with open(cfg["assisted_templates_path"]) as f:
                templates = f.read()
        except FileNotFoundError:
            return False, "no assisted-templates.md"
        verdict = llm_ask(C.prompt("template_match", templates=templates, draft=body)) or ""
        if not verdict.strip().upper().startswith("YES"):
            return False, "no approved template matches"
    return True, "passed assisted filter"
