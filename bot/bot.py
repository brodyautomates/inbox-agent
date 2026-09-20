#!/usr/bin/env python3
"""
inbox-agent: the daemon.

Every `poll_seconds`:
  1. fetch inbox mail newer than the watermark (through gsend)
  2. triage each message: worth a reply, or not
  3. draft the reply against the playbook, create it in Gmail (gsend reply)
  4. retire any older unsent draft on the same thread
  5. post the draft to Telegram with SEND / SKIP / CHAIN
  6. apply the mode: manual waits, assisted auto-sends the narrow set,
     autopilot posts a countdown
  7. sweep handled messages, save state

Between polls it long-polls Telegram for taps and edit instructions.

Run:  python3 -m bot.bot            from the repo root, inside the venv
      python3 -m bot.bot --once     one poll cycle, then exit (for testing)
"""

import json
import os
import re
import subprocess
import sys
import time

from . import config as C
from . import llm
from . import modes
from . import state as S
from . import tg

GSEND = [sys.executable, os.path.join(C.REPO, "gsend", "gsend.py")]
IN_FLIGHT = set()
MAX_RETRY = 8
DEAL_HINTS = ("sponsor", "partnership", "collab", "campaign", "budget", "rate", "quote",
              "proposal", "brief", "enquiry", "inquiry", "work with", "pricing", "book",
              "hire", "project", "opportunity", "interested in")
NOISE_HINTS = ("unsubscribe", "receipt", "invoice #", "your order", "password", "verify your",
               "newsletter", "webinar", "digest", "no-reply", "noreply", "notification")


# ---------------------------------------------------------------- gsend bridge

def gsend(*args, stdin=None, timeout=300):
    r = subprocess.run(GSEND + list(args), capture_output=True, text=True, input=stdin,
                       timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def fetch_inbox(after):
    rc, out, err = gsend("inbox", str(int(after)), timeout=180)
    if rc != 0:
        C.log(f"inbox fetch failed: {err[:200]}")
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        C.log(f"inbox fetch bad json: {out[:120]}")
        return None


def fetch_thread(tid):
    rc, out, _ = gsend("thread", tid, timeout=180)
    if rc != 0:
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []


def draft_get(did):
    rc, out, _ = gsend("draft-get", did, timeout=120)
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- triage + draft

def looks_like_noise(m):
    text = f"{m.get('from', '')} {m.get('subject', '')} {m.get('body', '')[:600]}".lower()
    cfg = C.load()
    if any(s.lower() in m.get("from", "").lower() for s in cfg.get("ignore_senders") or []):
        return True
    if any(h in text for h in NOISE_HINTS) and not any(h in text for h in DEAL_HINTS):
        return True
    return False


def render_thread(thread, limit=6000):
    parts = []
    for m in thread:
        who = "ME" if m.get("sent_by_me") else m.get("from", "?")
        parts.append(f"--- {m.get('date', '')} | {who}\n{m.get('body', '')[:2000]}")
    text = "\n\n".join(parts)
    return text[-limit:]


def triage(m):
    """'REPLY', 'IGNORE', or 'ESCALATE: reason'. None when Claude is down."""
    out = llm.ask(C.prompt("triage", sender=m.get("from", ""), subject=m.get("subject", ""),
                           body=m.get("body", "")[:2500]), timeout=120)
    if out is None:
        return None
    first = out.strip().splitlines()[0].strip().upper() if out.strip() else "IGNORE"
    if first.startswith("REPLY"):
        return "REPLY"
    if first.startswith("ESCALATE"):
        return out.strip().splitlines()[0].strip()
    return "IGNORE"


def write_draft(m, thread, instruction=None):
    """Returns (draft_id, body) or (None, reason)."""
    cfg = C.load()
    out = llm.ask(C.prompt("draft", playbook=C.playbook(), thread=render_thread(thread),
                           latest_from=m.get("from", ""), latest_subject=m.get("subject", ""),
                           latest_body=m.get("body", "")[:3000],
                           instruction=instruction or "none",
                           signoff=cfg.get("signoff_name") or "[your name]"), timeout=240)
    if out is None:
        return None, "claude unavailable"
    body = out.strip()
    up = body.upper()
    if up.startswith("ESCALATE"):
        return None, body.splitlines()[0][:200]
    if up.startswith("NO-REPLY"):
        return None, body.splitlines()[0][:200]
    rc, did, err = gsend("reply", m["id"], stdin=body + "\n", timeout=120)
    if rc != 0:
        return None, f"gsend reply failed: {err[:160]}"
    return did.strip(), body


def rewrite_draft(did, instruction):
    d = draft_get(did)
    if not d:
        return None, "draft not found (sent or deleted?)"
    out = llm.ask(C.prompt("rewrite", playbook=C.playbook(), to=d["to"], subject=d["subject"],
                           draft=d["body"], instruction=instruction), timeout=300)
    if not out:
        return None, "claude unavailable"
    body = out.strip()
    rc, _, err = gsend("draft-update", did, stdin=body + "\n", timeout=120)
    if rc != 0:
        return None, f"draft update failed: {err[:160]}"
    return did, body


# ---------------------------------------------------------------- announce

def card_text(m, body, banner="", stops=None, mode=None, due_min=None):
    head = banner
    if stops:
        head += "WAITS FOR YOU: " + "; ".join(stops) + "\n"
    elif mode == "autopilot" and due_min:
        head += f"AUTOPILOT: sends in {due_min} min unless you tap HOLD\n"
    elif mode == "assisted":
        head += "ASSISTED: did not pass the filter, waits for you\n"
    return (f"{head}From: {m.get('from', '?')}\n{m.get('subject', '')}\n\n"
            f"THEIR EMAIL:\n{m.get('body', '')[:1200]}\n\n"
            f"REPLY:\n{body[:1800]}")


def retire_older(st, m, keep_did):
    """A new email on a thread makes any older unsent draft on it stale."""
    gone = 0
    for did, meta in list(st["meta"].items()):
        if did == keep_did or did in st["done"]:
            continue
        if meta.get("tid") == m.get("tid"):
            gsend("draft-delete", did, timeout=60)
            for mid in S.messages_for(st, did):
                tg.delete(mid)
            st["done"].append(did)
            S.forget(st, did)
            gone += 1
    return gone


def auto_send(st, did, m, why, mode):
    """Send without a tap. Same commit-before-fire path as a manual SEND."""
    if did in st["done"] or did in IN_FLIGHT:
        return False
    IN_FLIGHT.add(did)
    st["done"].append(did)
    S.save(st)
    try:
        rc, out, err = gsend("send", did)
    finally:
        IN_FLIGHT.discard(did)
    if rc != 0:
        st["done"].remove(did)
        S.save(st)
        C.log(f"auto send FAILED {did}: {err[:160]}")
        tg.say(f"Auto send failed, draft untouched: {err[:300]}", tg.done_keyboard("err"))
        return False
    st["auto_sent"].append({"did": did, "to": m.get("from", "?"), "subj": m.get("subject", ""),
                            "at": time.time(), "mode": mode, "why": why})
    for mid in S.messages_for(st, did):
        tg.delete(mid)
    S.forget(st, did)
    C.log(f"auto sent {did} [{mode}] {why}")
    return True


def announce(st, m, did, body, thread, escalate_reason=None):
    cfg = C.load()
    mode = C.mode()
    retired = retire_older(st, m, did)
    banner = f"UPDATED: replaces {retired} earlier draft\n" if retired else ""
    stops = modes.hard_stops(body, thread, flagged_escalate=bool(escalate_reason))
    if stops or mode == "manual":
        resp = tg.say(card_text(m, body, banner, stops=stops), tg.draft_keyboard(did))
        if resp.get("ok"):
            S.record_draft(st, did, m, resp["result"]["message_id"])
        return
    if mode == "assisted":
        ok, why = modes.assisted_ok(body, thread, llm_ask=llm.ask)
        if ok:
            S.record_draft(st, did, m)
            resp = tg.say(card_text(m, body, banner + "ASSISTED: sending now\n"))
            if resp.get("ok"):
                st["msgmap"][str(resp["result"]["message_id"])] = did
            auto_send(st, did, m, why, "assisted")
            return
        resp = tg.say(card_text(m, body, banner, mode="assisted"), tg.draft_keyboard(did))
        if resp.get("ok"):
            S.record_draft(st, did, m, resp["result"]["message_id"])
        return
    # autopilot
    delay = int(cfg["autopilot_delay_minutes"])
    resp = tg.say(card_text(m, body, banner, mode="autopilot", due_min=delay),
                  tg.countdown_keyboard(did))
    if resp.get("ok"):
        S.record_draft(st, did, m, resp["result"]["message_id"])
        st["countdown"][did] = time.time() + delay * 60


def handle_inbound(st, m):
    """Returns 'done' or 'retry'."""
    verdict = triage(m)
    if verdict is None:
        return "retry"
    if verdict == "IGNORE":
        C.log(f"ignored {m['from'][:40]} | {m['subject'][:50]}")
        return "done"
    thread = fetch_thread(m["tid"]) or [m]
    if verdict.startswith("ESCALATE"):
        reason = verdict.split(":", 1)[1].strip() if ":" in verdict else "needs you"
        resp = tg.say(f"NEEDS YOU: {reason[:150]}\nFrom: {m['from']}\n{m['subject']}\n\n"
                      f"{m['body'][:1800]}", tg.done_keyboard("esc"))
        C.log(f"escalated {m['from'][:40]} | {reason[:60]}")
        return "done"
    did, body = write_draft(m, thread)
    if did:
        announce(st, m, did, body, thread)
        C.log(f"drafted {did} for {m['from'][:40]}")
        return "done"
    if body.upper().startswith("ESCALATE"):
        reason = body.split(":", 1)[1].strip() if ":" in body else "needs you"
        tg.say(f"NEEDS YOU: {reason[:150]}\nFrom: {m['from']}\n{m['subject']}\n\n{m['body'][:1800]}",
               tg.done_keyboard("esc"))
        C.log(f"escalated at draft {m['from'][:40]} | {reason[:60]}")
        return "done"
    if body.upper().startswith("NO-REPLY"):
        C.log(f"no reply warranted {m['from'][:40]}: {body[:80]}")
        return "done"
    C.log(f"draft failed {m['id']}: {body[:100]}")
    return "retry"


# ---------------------------------------------------------------- the poll

def poll_inbox(st):
    if llm.down():
        return
    msgs = fetch_inbox(st["watermark"] - 300)
    if msgs is None:
        return
    seen = set(st["seen"])
    queued = {r["id"] for r in st["retry"]}
    for m in msgs:
        if m["id"] in seen or m["id"] in queued or m.get("sent_by_me"):
            continue
        if looks_like_noise(m):
            st["seen"].append(m["id"])
            continue
        result = handle_inbound(st, m)
        if result == "retry":
            st["retry"].append({"id": m["id"], "m": m, "n": 0, "next": time.time() + 900})
            if llm.down():
                break
        else:
            st["seen"].append(m["id"])
        st["watermark"] = max(st["watermark"], m["ms"] // 1000)
        S.save(st)
    if msgs and not llm.down():
        st["watermark"] = max(st["watermark"], max(m["ms"] for m in msgs) // 1000)


def process_retries(st):
    if llm.down():
        return
    now = time.time()
    keep = []
    for r in st["retry"]:
        if r["next"] > now:
            keep.append(r)
            continue
        result = handle_inbound(st, r["m"])
        if result == "retry":
            r["n"] += 1
            if r["n"] >= MAX_RETRY:
                C.log(f"giving up on {r['id']} after {MAX_RETRY} tries")
                tg.say(f"Could not draft a reply after {MAX_RETRY} tries. Handle by hand.\n"
                       f"From: {r['m']['from']}\n{r['m']['subject']}", tg.done_keyboard("err"))
                st["seen"].append(r["id"])
            else:
                r["next"] = now + min(3600, 900 * (r["n"] + 1))
                keep.append(r)
            if llm.down():
                keep.extend(x for x in st["retry"] if x is not r and x not in keep)
                break
        else:
            st["seen"].append(r["id"])
    st["retry"] = keep


def fire_countdowns(st):
    now = time.time()
    for did, due in list(st["countdown"].items()):
        if did in st["done"]:
            st["countdown"].pop(did, None)
            continue
        if due > now or C.paused():
            continue
        meta = st["meta"].get(did, {})
        m = {"from": meta.get("to", "?"), "subject": meta.get("subj", "")}
        st["countdown"].pop(did, None)
        auto_send(st, did, m, "countdown expired", "autopilot")


def digest(st):
    cfg = C.load()
    today = time.strftime("%Y-%m-%d")
    if st["last_digest"] == today or time.localtime().tm_hour != int(cfg["digest_hour"]):
        return
    cutoff = time.time() - 86400
    rows = [r for r in st["auto_sent"] if r["at"] >= cutoff]
    st["auto_sent"] = [r for r in st["auto_sent"] if r["at"] >= cutoff - 6 * 86400]
    st["last_digest"] = today
    if not rows:
        return
    lines = [f"Sent without you in the last 24h ({len(rows)}):"]
    for r in rows:
        lines.append(f"- {r['to'][:40]} | {r['subj'][:50]} [{r['mode']}]")
    tg.say("\n".join(lines), tg.done_keyboard("digest"))


def sweep(st):
    for mid, val in list(st["msgmap"].items()):
        base = val[2:] if val.startswith("x:") else val
        if base in st["done"]:
            tg.delete(mid)
            st["msgmap"].pop(mid, None)


# ---------------------------------------------------------------- taps and text

def do_send(st, did, mid, cb_id):
    if did in st["done"]:
        tg.ack(cb_id, "Already handled. Nothing sent again.", alert=True)
        tg.stamp(mid, "HANDLED", did)
        return
    if C.paused():
        tg.ack(cb_id, "Paused: stop file exists. Nothing sent.", alert=True)
        return
    if not tg.ack(cb_id, "Sending..."):
        C.log(f"stale send tap ignored {did}")
        tg.say("That SEND tap was replayed by Telegram after downtime and was ignored. "
               "Nothing sent. Tap SEND again if you still want it out.", reply_to=mid)
        return
    if did in IN_FLIGHT:
        return
    IN_FLIGHT.add(did)
    st["done"].append(did)          # commit BEFORE firing: a crash can lose a send, never double it
    st["countdown"].pop(did, None)
    S.save(st)
    tg.stamp(mid, "SENDING", did)
    try:
        rc, out, err = gsend("send", did)
    finally:
        IN_FLIGHT.discard(did)
    if rc == 0:
        for m_id in S.messages_for(st, did):
            tg.delete(m_id)
        S.forget(st, did)
        C.log(f"sent {did}")
    else:
        st["done"].remove(did)
        S.save(st)
        tg.edit_keyboard(mid, tg.draft_keyboard(did))
        tg.say(f"Send failed, draft untouched: {err or out}"[:500], tg.done_keyboard("err"), reply_to=mid)
        C.log(f"send FAILED {did}: {err[:160]}")


def handle_callback(st, cb):
    action, did = cb["data"].split(":", 1)
    mid = cb.get("message", {}).get("message_id")
    if action == "noop":
        tg.ack(cb["id"], "Already handled.", alert=True)
    elif action == "clr":
        tg.ack(cb["id"], "Cleared.")
        if mid:
            tg.delete(mid)
            st["msgmap"].pop(str(mid), None)
    elif action == "chain":
        tg.ack(cb["id"])
        meta = st["meta"].get(did, {})
        thread = fetch_thread(meta.get("tid", "")) if meta.get("tid") else []
        text = render_thread(thread, limit=3800) or "No thread found."
        resp = tg.say("CHAIN\n" + text, reply_to=mid)
        if resp.get("ok"):
            S.helper_message(st, resp["result"]["message_id"], did)
    elif action == "hold":
        tg.ack(cb["id"], "Held. It now waits for your tap.")
        st["countdown"].pop(did, None)
        tg.edit_keyboard(mid, tg.draft_keyboard(did))
        C.log(f"held {did}")
    elif action == "send":
        do_send(st, did, mid, cb["id"])
    elif action == "skip":
        if not tg.ack(cb["id"], "Skipped."):
            C.log(f"stale skip tap ignored {did}")
            return
        if did in st["done"]:
            return
        st["done"].append(did)
        st["countdown"].pop(did, None)
        S.save(st)
        gsend("draft-delete", did, timeout=60)
        for m_id in S.messages_for(st, did):
            tg.delete(m_id)
        S.forget(st, did)
        C.log(f"skipped {did}")


def handle_text(st, msg):
    text = (msg.get("text") or "").strip()
    if not text:
        return
    low = text.lower()
    if low.startswith("/mode"):
        parts = low.split()
        if len(parts) == 2 and parts[1] in ("manual", "assisted", "autopilot"):
            C.set_mode(parts[1])
            tg.say(f"Mode is now {parts[1]}.")
            C.log(f"mode -> {parts[1]}")
        else:
            tg.say(f"Mode is {C.mode()}. Use: /mode manual | assisted | autopilot")
        return
    if low in ("/status", "/start", "/help"):
        pending = [d for d in st["announced"] if d not in st["done"]]
        tg.say(f"Mode: {C.mode()}\nPaused: {'yes' if C.paused() else 'no'}\n"
               f"Waiting for you: {len(pending)}\nRetry queue: {len(st['retry'])}\n"
               f"Claude: {'DOWN' if llm.down() else 'ok'}\n\n"
               "Reply to a draft message to edit it. /mode to switch modes. /pause and /resume for the stop file.")
        return
    if low == "/pause":
        open(C.PAUSE_FILE, "a").close()
        tg.say("Paused. Nothing will send until /resume.")
        return
    if low == "/resume":
        try:
            os.remove(C.PAUSE_FILE)
        except FileNotFoundError:
            pass
        tg.say("Resumed.")
        return
    reply_to = msg.get("reply_to_message", {}).get("message_id")
    did = st["msgmap"].get(str(reply_to)) if reply_to else None
    if did and did.startswith("x:"):
        did = did[2:]
    if not did:
        tg.say("I could not tie that to a draft. Swipe-reply on the draft's own message, "
               "the one with the SEND button.")
        return
    if did in st["done"]:
        tg.say("That draft was already sent or skipped.")
        return
    if C.paused():
        tg.say("Paused: stop file exists.")
        return
    st["countdown"].pop(did, None)   # an edit always takes it off autopilot's clock
    tg.say("Rewriting...", reply_to=msg.get("message_id"))
    new_did, body = rewrite_draft(did, text)
    if not new_did:
        tg.say(f"Rewrite failed, original draft untouched: {body}"[:500])
        return
    meta = st["meta"].get(did, {})
    resp = tg.say(f"UPDATED DRAFT to {meta.get('to', '?')}\n{meta.get('subj', '')}\n\n{body}",
                  tg.draft_keyboard(did))
    if resp.get("ok"):
        old = st["announced"].get(did)
        if old:
            tg.delete(old)
            st["msgmap"].pop(str(old), None)
        st["announced"][did] = resp["result"]["message_id"]
        st["msgmap"][str(resp["result"]["message_id"])] = did
    C.log(f"rewrote {did}: {text[:60]!r}")


# ---------------------------------------------------------------- main

def cycle(st):
    if not C.paused():
        try:
            sweep(st)
            poll_inbox(st)
            process_retries(st)
        except Exception as e:
            C.log(f"cycle error: {e!r}")
    try:
        fire_countdowns(st)
        digest(st)
    except Exception as e:
        C.log(f"post-cycle error: {e!r}")
    if llm.down() and not st.get("outage_told"):
        st["outage_told"] = True
        tg.say("Claude is unavailable, so nothing can be drafted. Nothing is lost: inbound is "
               "held and resumes on its own.\n\n" + llm.OUTAGE["why"][:200] +
               "\n\nIf this says login or auth: make a new token with `claude setup-token` "
               "and put it in ~/.config/inbox-agent/env, then restart the service.",
               tg.done_keyboard("outage"))
    if st.get("outage_told") and llm.OUTAGE.get("recovered"):
        st["outage_told"] = False
        llm.OUTAGE.update(at=0.0, recovered=False)
        tg.say("Claude is back. Resuming.")
    S.save(st)


def main():
    cfg = C.load()
    if not cfg["telegram_token"] or not cfg["allowed_user"]:
        raise SystemExit("Set telegram_token and allowed_user in config.json first. Run tools/doctor.py.")
    st = S.load()
    C.log(f"inbox-agent started, mode={C.mode()}, backend={cfg['claude_backend']}")
    if "--once" in sys.argv:
        cycle(st)
        return
    last = 0.0
    while True:
        if time.time() - last > int(C.load()["poll_seconds"]):
            cycle(st)
            last = time.time()
        resp = tg.api("getUpdates", offset=st["offset"] + 1, timeout=50)
        if not resp.get("ok"):
            time.sleep(5)
            continue
        for upd in resp["result"]:
            st["offset"] = max(st["offset"], upd["update_id"])
            frm = (upd.get("message") or upd.get("callback_query") or {}).get("from", {})
            if frm.get("id") != int(C.load()["allowed_user"]):
                C.log(f"dropped update from non-allowlisted user {frm.get('id')}")
                continue            # first thing, before anything is read
            try:
                if "callback_query" in upd:
                    handle_callback(st, upd["callback_query"])
                elif "message" in upd:
                    handle_text(st, upd["message"])
            except Exception as e:
                C.log(f"handler error: {e!r}")
                tg.say(f"Handler error, draft untouched: {e!r}"[:300], tg.done_keyboard("err"))
            S.save(st)


if __name__ == "__main__":
    main()
