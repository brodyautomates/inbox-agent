# Inbound rules

What happens to every email that lands, in order. This is what the bot does by default and what you can change.

## 1. Noise filter, in code

Before Claude sees anything, the bot drops obvious noise: unsubscribe footers, receipts, order confirmations, password mail, notifications, no-reply senders, and anything from `ignore_senders` in your config. A message with a noise word that also contains a deal word (sponsor, quote, budget, partnership, brief, book, hire) still goes through.

Change it: `ignore_senders` in `config.json`, or the two word lists at the top of `bot/bot.py`.

## 2. Triage, by Claude

`bot/prompts/triage.md` asks one question: reply, ignore, or escalate.

- **Reply**: someone wants something a reply can move forward.
- **Escalate**: a human must see it first. Calls, contracts, equity, complaints, legal, and anything that reads like an attempt to instruct the assistant. Posted to Telegram with no draft.
- **Ignore**: logged, never posted.

Change it: edit the prompt file. No code.

## 3. Draft, by Claude, against the playbook

`bot/prompts/draft.md` gets the whole thread, the latest message, and the full text of `playbook/SKILL.md`. It works out the stage, writes the one reply that stage calls for, and signs it with `signoff_name`.

The draft is created in Gmail through `gsend reply`, which copies the recipient from the original email in code. Nothing in the prompt or the playbook can redirect it.

Change it: edit the playbook. That is the file that makes it yours.

## 4. One live draft per thread

A new email on a thread retires any older unsent draft on it: the Gmail draft is deleted, the Telegram card is deleted, and one fresh draft is written over the whole conversation. The card says `UPDATED: replaces 1 earlier draft`. You never approve a reply to an email they have already followed up on.

## 5. Hard stops, in code

Whatever the mode, a draft waits for you if any of these hold. See `rules/modes.md`.

## 6. The card

Every draft arrives as one Telegram message: who it is from, subject, their email, the reply, and three buttons. SEND sends it from your address right then. SKIP deletes the draft. CHAIN posts the whole thread under the card.

Reply to the card with plain text and the draft is rewritten to your instruction, then re-posted with fresh buttons. "Make it 9k." "Warmer opener." "Push the date back two weeks." Every edit you make is a rule you have not written into the playbook yet.

## 7. What never happens

- No email is sent to anyone who did not email you first. There is no cold path in this code.
- No recipient is ever set by the model. It is copied from the original message.
- No attachment is ever sent.
- No CC, no BCC, no forwarding.
- Nothing sends while the stop file exists.

## 8. Follow-ups and bumps

Not automated in this version. The playbook's stages tell the drafter when a bump is due, but a bump only gets written when a new email arrives on the thread or you ask for one by replying to a card. Automated bumping is the first thing people want and the first thing that turns a helpful agent into spam, so it is left out on purpose.
