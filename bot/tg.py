"""Thin Telegram Bot API client. No library, just urllib."""

import json
import urllib.parse
import urllib.request

from . import config as C


def _api_base():
    return f"https://api.telegram.org/bot{C.load()['telegram_token']}"


def api(method, **params):
    data = urllib.parse.urlencode(
        {k: v if isinstance(v, str) else json.dumps(v) for k, v in params.items()}).encode()
    req = urllib.request.Request(f"{_api_base()}/{method}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=70) as r:
            return json.load(r)
    except Exception as e:
        C.log(f"telegram {method}: {e!r}")
        return {"ok": False}


def chat_id():
    # the allowlisted user's private chat with the bot
    return C.load()["allowed_user"]


def say(text, keyboard=None, reply_to=None):
    kw = {"chat_id": chat_id(), "text": text[:4000]}
    if keyboard:
        kw["reply_markup"] = keyboard
    if reply_to:
        kw["reply_parameters"] = {"message_id": reply_to}
    return api("sendMessage", **kw)


def edit_keyboard(mid, keyboard):
    return api("editMessageReplyMarkup", chat_id=chat_id(), message_id=mid,
               reply_markup=keyboard or {"inline_keyboard": []})


def edit_text(mid, text, keyboard=None):
    kw = {"chat_id": chat_id(), "message_id": mid, "text": text[:4000]}
    if keyboard:
        kw["reply_markup"] = keyboard
    return api("editMessageText", **kw)


def delete(mid):
    return api("deleteMessage", chat_id=chat_id(), message_id=int(mid)).get("ok", False)


def ack(cb_id, text=None, alert=False):
    """Acknowledge a button tap. Telegram refuses acks for taps older than a
    minute or so, which is exactly how the bot detects a replayed tap after a
    restart: no ack, no send."""
    kw = {"callback_query_id": cb_id}
    if text:
        kw["text"] = text
    if alert:
        kw["show_alert"] = True
    return api("answerCallbackQuery", **kw).get("ok", False)


def stamp(mid, label, did):
    """Replace the buttons with one dead button so nothing can be tapped twice."""
    return edit_keyboard(mid, {"inline_keyboard": [[{"text": label, "callback_data": f"noop:{did}"}]]})


# ---------------------------------------------------------------- keyboards

def draft_keyboard(did):
    return {"inline_keyboard": [
        [{"text": "SEND", "callback_data": f"send:{did}"},
         {"text": "SKIP", "callback_data": f"skip:{did}"},
         {"text": "CHAIN", "callback_data": f"chain:{did}"}],
    ]}


def countdown_keyboard(did):
    return {"inline_keyboard": [
        [{"text": "SEND NOW", "callback_data": f"send:{did}"},
         {"text": "HOLD", "callback_data": f"hold:{did}"},
         {"text": "SKIP", "callback_data": f"skip:{did}"},
         {"text": "CHAIN", "callback_data": f"chain:{did}"}],
    ]}


def done_keyboard(tag="x"):
    return {"inline_keyboard": [[{"text": "DONE", "callback_data": f"clr:{tag}"}]]}
