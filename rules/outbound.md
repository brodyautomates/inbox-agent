# Outbound: why this repo does not ship it, and what you owe if you add it

This agent replies to people who emailed you first. There is no cold email code in it, on purpose. Replying to an inbound message is barely regulated. Emailing a stranger first is regulated in every major market, with per-message penalties, and the rules differ by where the recipient is, not where you are.

If you extend the bot to send first, you take on the obligations below. This is not legal advice. These are the rules as published. Check the current figures before you rely on them, because they are indexed and they move.

## United States: CAN-SPAM

You may email a business contact without prior consent, until they opt out. Every message needs:

- your real name and a valid physical postal address
- an honest subject line and honest headers
- a clear way to opt out, honoured within ten business days
- no further mail to anyone who opted out, ever

Penalties are counted per email. The figure was over fifty thousand dollars per message when this was written. Source: FTC, CAN-SPAM Act compliance guide.

## Canada: CASL

Consent before the first message, and proving you had it is your job. The implied-consent business exemption is narrower than most people assume. Penalties run to the low millions per violation for individuals and higher for companies. Jurisdiction follows the recipient. Source: CRTC, Canada's Anti-Spam Legislation.

## EU and UK: GDPR, ePrivacy, PECR

A lawful basis, a statement of where you got their address, and an opt-out in every message. Some member states require consent even for business-to-business email. Source: ICO guidance on direct marketing, and the relevant national regulator.

## If they might be in Canada or Europe

Get consent first. It is simpler than running three systems and being wrong about one.

## What the code would have to enforce, not the prompt

If you build an outbound path, these belong in code:

1. A do-not-contact list checked before any draft is written. Any reply containing "unsubscribe", "remove me", "stop", or "take me off" adds that sender to the list permanently, in code, before the model sees it.
2. Your business name, postal address, and an opt-out line appended by the code to every outbound draft. Missing footer, no draft.
3. A hard daily cap on cold drafts.
4. A separate mode flag, default off, with the manual send gate forced on for every cold email regardless of the mode setting.
5. Every refusal logged with the reason.

None of this is in the repo. The bot's `gsend reply` command cannot send to anyone who did not write first, and there is no `gsend compose`. That is the line, and it is drawn in code.
