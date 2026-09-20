"""
The bot's memory: one JSON file.

  offset        last Telegram update id handled
  watermark     unix seconds; inbox mail older than this is never fetched again
  seen          message ids already processed
  announced     draft id -> Telegram message id of its card
  msgmap        Telegram message id -> draft id (or "x:<did>" for helper messages that die with it)
  done          draft ids that were sent or skipped. Checked BEFORE every send.
  meta          draft id -> {tid, addr, subj, msg_id, ms}
  retry         inbound messages waiting for Claude to come back
  countdown     draft id -> unix seconds when autopilot may send it
  auto_sent     [{did, to, subj, at, mode, why}] for the morning digest
  last_digest   YYYY-MM-DD

Never hand-edit this file while the bot runs. Stop the service first.
"""

import json
import os
import time

from . import config as C

FRESH = {
    "offset": 0,
    "watermark": 0,
    "seen": [],
    "announced": {},
    "msgmap": {},
    "done": [],
    "meta": {},
    "retry": [],
    "countdown": {},
    "auto_sent": [],
    "last_digest": "",
}


def load():
    st = dict(FRESH)
    if os.path.exists(C.STATE):
        with open(C.STATE) as f:
            st.update(json.load(f))
    if not st["watermark"]:
        # first run: only look at mail from now on, never the whole history
        st["watermark"] = int(time.time())
    return st


def save(st):
    # keep seen bounded
    if len(st["seen"]) > 5000:
        st["seen"] = st["seen"][-3000:]
    tmp = C.STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.replace(tmp, C.STATE)


def record_draft(st, did, m, mid=None):
    st["meta"][did] = {"tid": m.get("tid"), "addr": addr_of(m.get("from", "")),
                       "subj": m.get("subject", ""), "msg_id": m.get("id"),
                       "ms": m.get("ms", 0), "to": m.get("reply_to") or m.get("from", "")}
    if mid:
        st["announced"][did] = mid
        st["msgmap"][str(mid)] = did


def addr_of(s):
    s = s or ""
    if "<" in s and ">" in s:
        return s[s.index("<") + 1:s.index(">")].strip().lower()
    return s.strip().lower()


def helper_message(st, mid, did):
    """A chain view or a notice that should disappear when the draft is done."""
    st["msgmap"][str(mid)] = "x:" + did


def messages_for(st, did):
    return [int(mid) for mid, v in st["msgmap"].items()
            if v == did or v == "x:" + did]


def forget(st, did):
    for mid in messages_for(st, did):
        st["msgmap"].pop(str(mid), None)
    st["announced"].pop(did, None)
    st["countdown"].pop(did, None)
