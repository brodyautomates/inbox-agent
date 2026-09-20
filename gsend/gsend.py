#!/usr/bin/env python3
"""
gsend: the only thing in this repo that can touch Gmail.

The OAuth token IS the sender identity. Every command checks that the token
belongs to the address in your config and refuses to run otherwise, so the
bot can never quietly send from the wrong account.

Usage:
  gsend auth                    one-time browser login (run this on a machine with a browser)
  gsend whoami                  print which address the token belongs to
  gsend test                    send one proof email to yourself and print the From header it used
  gsend list                    list drafts: id, to, subject
  gsend search <query> [max]    search the mailbox with Gmail query syntax
  gsend get <message-id>        print one message: headers and plain-text body
  gsend inbox <after-epoch>     JSON list of inbox messages newer than a unix timestamp (used by the bot)
  gsend thread <thread-id>      JSON list of every message in a thread, oldest first (used by the bot)
  gsend reply <message-id>      create a THREADED reply draft, body on stdin, prints the draft id
                                To is copied from the original sender in code. It cannot be overridden.
  gsend send <draft-id>         send one draft by id
  gsend draft-get <draft-id>    print a draft as JSON: to, subject, body, threadId
  gsend draft-update <draft-id> replace a draft's body from stdin; recipient, subject and thread stay locked
  gsend draft-delete <draft-id> delete an unsent draft

Config:   ~/.config/inbox-agent/config.json   (key "gmail_address")
Secrets:  ~/.config/inbox-agent/client_secret.json  and  token.json
"""

import base64
import datetime
import json
import os
import re
import sys
import time
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CONF_DIR = os.path.expanduser(os.environ.get("INBOX_AGENT_HOME", "~/.config/inbox-agent"))
CONFIG = os.path.join(CONF_DIR, "config.json")
TOKEN = os.path.join(CONF_DIR, "token.json")
CLIENT = os.path.join(CONF_DIR, "client_secret.json")
SEND_LOG = os.path.join(CONF_DIR, "send.log")
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def expected_address():
    try:
        with open(CONFIG) as f:
            addr = json.load(f).get("gmail_address", "").strip().lower()
    except FileNotFoundError:
        print(f"Missing {CONFIG}. Copy config.example.json there and fill in gmail_address.")
        sys.exit(1)
    if not addr or addr.endswith("@example.com"):
        print(f"Set gmail_address in {CONFIG} to the real address this agent sends from.")
        sys.exit(1)
    return addr


EXPECTED = expected_address()


def creds():
    c = None
    if os.path.exists(TOKEN):
        c = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if c and c.expired and c.refresh_token:
        c.refresh(Request())
        with open(TOKEN, "w") as f:
            f.write(c.to_json())
    if not c or not c.valid:
        print("Not authorized. Run: gsend auth   (on a machine with a browser)")
        sys.exit(1)
    return c


def svc():
    return build("gmail", "v1", credentials=creds(), cache_discovery=False)


def guard(s):
    """Refuse to run against the wrong mailbox."""
    addr = s.users().getProfile(userId="me").execute()["emailAddress"]
    if addr.lower() != EXPECTED:
        print(f"REFUSING: token belongs to {addr}, config expects {EXPECTED}.")
        print(f"Delete {TOKEN} and re-run: gsend auth (log in as {EXPECTED})")
        sys.exit(1)
    return addr


def _headers(msg):
    return {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}


def _body_text(payload):
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="replace")
    for part in payload.get("parts", []) or []:
        text = _body_text(part)
        if text:
            return text
    return ""


def _strip_quoted(text):
    out = []
    for ln in text.splitlines():
        if re.match(r"^\s*On .{5,80}wrote:?\s*$", ln):
            break
        if ln.startswith(">"):
            continue
        out.append(ln)
    return "\n".join(out).strip()


def _has_attachment(payload):
    if payload.get("filename"):
        return True
    return any(_has_attachment(p) for p in payload.get("parts", []) or [])


def _msg_dict(f):
    hh = _headers(f)
    return {
        "id": f["id"],
        "tid": f["threadId"],
        "ms": int(f.get("internalDate", 0)),
        "from": hh.get("from", "?"),
        "to": hh.get("to", ""),
        "cc": hh.get("cc", ""),
        "reply_to": hh.get("reply-to", ""),
        "subject": hh.get("subject", "(no subject)"),
        "date": hh.get("date", "?")[:31],
        "labels": f.get("labelIds", []),
        "sent_by_me": "SENT" in f.get("labelIds", []),
        "attachment": _has_attachment(f["payload"]),
        "body": _strip_quoted(_body_text(f["payload"]))[:4000] or f.get("snippet", ""),
    }


# ---------------------------------------------------------------- commands

def cmd_auth():
    if not os.path.exists(CLIENT):
        print(f"Missing {CLIENT}")
        print("Create an OAuth Desktop client in Google Cloud Console, download its JSON, save it there.")
        sys.exit(1)
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES)
    print(f"A browser window will open. Log in as {EXPECTED}.")
    c = flow.run_local_server(port=0)
    with open(TOKEN, "w") as f:
        f.write(c.to_json())
    os.chmod(TOKEN, 0o600)
    s = build("gmail", "v1", credentials=c, cache_discovery=False)
    addr = s.users().getProfile(userId="me").execute()["emailAddress"]
    if addr.lower() != EXPECTED:
        os.remove(TOKEN)
        print(f"Authorized as {addr}, which is the wrong account. Token deleted. Re-run gsend auth as {EXPECTED}.")
        sys.exit(1)
    print(f"Authorized as {addr}. Token stored at {TOKEN}.")


def cmd_whoami():
    print(svc().users().getProfile(userId="me").execute()["emailAddress"])


def cmd_test():
    s = svc()
    guard(s)
    msg = MIMEText("Send-path proof from gsend. If the From line on this email reads "
                   f"{EXPECTED}, the path is verified.")
    msg["to"] = EXPECTED
    msg["subject"] = "gsend send-path proof"
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = s.users().messages().send(userId="me", body={"raw": raw}).execute()
    got = s.users().messages().get(userId="me", id=sent["id"], format="metadata",
                                   metadataHeaders=["From"]).execute()
    frm = {h["name"]: h["value"] for h in got["payload"]["headers"]}.get("From", "?")
    print(f"Sent test to {EXPECTED}. From header: {frm}")
    ok = EXPECTED in frm.lower()
    print("VERIFIED" if ok else "MISMATCH. Do not use this path.")
    sys.exit(0 if ok else 1)


def cmd_list():
    s = svc()
    guard(s)
    resp = s.users().drafts().list(userId="me", maxResults=100).execute()
    rows = []
    for d in resp.get("drafts", []):
        full = s.users().drafts().get(userId="me", id=d["id"], format="metadata").execute()
        hh = _headers(full["message"])
        rows.append((d["id"], hh.get("to", "?"), hh.get("subject", "(no subject)")))
    for did, to, subj in rows:
        print(f"{did}\t{to}\t{subj}")
    print(f"\n{len(rows)} draft(s).")


def cmd_search(query, max_results):
    s = svc()
    guard(s)
    resp = s.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    ids = resp.get("messages", [])
    for m in ids:
        msg = s.users().messages().get(userId="me", id=m["id"], format="metadata",
                                       metadataHeaders=["From", "Subject", "Date"]).execute()
        hh = _headers(msg)
        snippet = msg.get("snippet", "").replace("\t", " ")[:120]
        print(f"{m['id']}\t{hh.get('date', '?')}\t{hh.get('from', '?')}\t"
              f"{hh.get('subject', '(no subject)')}\t{snippet}")
    print(f"\n{len(ids)} message(s).")


def cmd_get(msg_id):
    s = svc()
    guard(s)
    msg = s.users().messages().get(userId="me", id=msg_id, format="full").execute()
    hh = _headers(msg)
    for k in ("date", "from", "to", "cc", "subject"):
        if hh.get(k):
            print(f"{k.capitalize()}: {hh[k]}")
    print(f"Thread: {msg['threadId']}\n")
    print(_body_text(msg["payload"]) or msg.get("snippet", "(no text body)"))


def cmd_inbox(after_epoch):
    """Inbox messages newer than a unix timestamp, as JSON, oldest first.
    Skips anything we sent and anything that is a draft."""
    s = svc()
    guard(s)
    resp = s.users().messages().list(userId="me", q=f"in:inbox after:{int(after_epoch)}",
                                     maxResults=50).execute()
    out = []
    for m in resp.get("messages", []):
        f = s.users().messages().get(userId="me", id=m["id"], format="full").execute()
        labels = f.get("labelIds", [])
        if "SENT" in labels or "DRAFT" in labels:
            continue
        out.append(_msg_dict(f))
    out.sort(key=lambda x: x["ms"])
    print(json.dumps(out))


def cmd_thread(thread_id):
    s = svc()
    guard(s)
    t = s.users().threads().get(userId="me", id=thread_id, format="full").execute()
    out = [_msg_dict(m) for m in t.get("messages", []) if "DRAFT" not in m.get("labelIds", [])]
    out.sort(key=lambda x: x["ms"])
    print(json.dumps(out))


def cmd_reply(msg_id):
    """Threaded reply draft. To is ALWAYS the original sender. No argument can change that."""
    body = sys.stdin.read()
    if not body.strip():
        print("empty body", file=sys.stderr)
        sys.exit(1)
    s = svc()
    guard(s)
    orig = s.users().messages().get(userId="me", id=msg_id, format="metadata",
                                    metadataHeaders=["From", "Reply-To", "Subject", "Message-ID"]).execute()
    hh = _headers(orig)
    to = hh.get("reply-to") or hh.get("from")
    if not to:
        print("original message has no sender", file=sys.stderr)
        sys.exit(1)
    subject = hh.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    if hh.get("message-id"):
        msg["In-Reply-To"] = hh["message-id"]
        msg["References"] = hh["message-id"]
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    d = s.users().drafts().create(userId="me",
                                  body={"message": {"raw": raw, "threadId": orig["threadId"]}}).execute()
    print(d["id"])


def _send_with_retry(s, draft_id):
    for attempt in range(4):
        try:
            return s.users().drafts().send(userId="me", body={"id": draft_id}).execute()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(15 * (attempt + 1))


def cmd_send(draft_id):
    s = svc()
    guard(s)
    d = s.users().drafts().get(userId="me", id=draft_id, format="metadata").execute()
    hh = _headers(d["message"])
    sent = _send_with_retry(s, draft_id)
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    with open(SEND_LOG, "a") as f:
        f.write(f"{stamp}\tsent\t{hh.get('to', '?')}\t{hh.get('subject', '(no subject)')}\t{sent['id']}\n")
    print(f"Sent draft {draft_id} (message {sent['id']}).")


def cmd_draft_get(draft_id):
    s = svc()
    guard(s)
    d = s.users().drafts().get(userId="me", id=draft_id, format="full").execute()
    m = d["message"]
    hh = _headers(m)
    print(json.dumps({"to": hh.get("to", ""), "subject": hh.get("subject", ""),
                      "body": _body_text(m["payload"]), "threadId": m.get("threadId", "")}))


def cmd_draft_update(draft_id):
    """Replace the body. Recipient, subject and thread are copied from the existing
    draft in code, so an update can never redirect an email."""
    body = sys.stdin.read()
    if not body.strip():
        print("empty body", file=sys.stderr)
        sys.exit(1)
    s = svc()
    guard(s)
    d = s.users().drafts().get(userId="me", id=draft_id, format="full").execute()
    m = d["message"]
    hh = _headers(m)
    msg = MIMEText(body)
    msg["to"] = hh.get("to", "")
    msg["subject"] = hh.get("subject", "")
    if hh.get("in-reply-to"):
        msg["In-Reply-To"] = hh["in-reply-to"]
    if hh.get("references"):
        msg["References"] = hh["references"]
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = {"message": {"raw": raw}}
    if m.get("threadId"):
        payload["message"]["threadId"] = m["threadId"]
    s.users().drafts().update(userId="me", id=draft_id, body=payload).execute()
    print(draft_id)


def cmd_draft_delete(draft_id):
    s = svc()
    guard(s)
    s.users().drafts().delete(userId="me", id=draft_id).execute()
    print(f"deleted {draft_id}")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(0)
    cmd, rest = a[0], a[1:]
    table = {
        "auth": lambda: cmd_auth(),
        "whoami": lambda: cmd_whoami(),
        "test": lambda: cmd_test(),
        "list": lambda: cmd_list(),
        "search": lambda: cmd_search(rest[0], int(rest[1]) if len(rest) > 1 else 25),
        "get": lambda: cmd_get(rest[0]),
        "inbox": lambda: cmd_inbox(rest[0]),
        "thread": lambda: cmd_thread(rest[0]),
        "reply": lambda: cmd_reply(rest[0]),
        "send": lambda: cmd_send(rest[0]),
        "draft-get": lambda: cmd_draft_get(rest[0]),
        "draft-update": lambda: cmd_draft_update(rest[0]),
        "draft-delete": lambda: cmd_draft_delete(rest[0]),
    }
    fn = table.get(cmd)
    if not fn:
        print(__doc__)
        sys.exit(1)
    try:
        fn()
    except IndexError:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
