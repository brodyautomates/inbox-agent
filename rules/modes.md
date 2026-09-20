# Modes: manual send gate, assisted, autopilot

Three modes. Move up one at a time. Switch from your phone with `/mode manual`, `/mode assisted` or `/mode autopilot`, or write the word into `~/.config/inbox-agent/mode`.

## Manual send gate (default)

Every draft comes to your phone. Nothing goes without your tap. Run here until you stop editing drafts. Every edit you make is a rule you forgot to write in the playbook. Write it in. You are training the file, not the model.

## Assisted

The bot sends the easy ones itself. A draft goes without you only if all of these are true, checked in code in `bot/modes.py`:

- no digit anywhere in it
- no currency symbol
- no date word (month names, weekday names, "tomorrow", "next week", "EOD")
- under `assisted_max_words` (default 40)
- no attachment anywhere in the thread
- it says the same thing as one of the templates in `playbook/assisted-templates.md`, judged by Claude with a yes or no

Everything else waits for you, exactly as in manual. The card says why it waited.

## Autopilot

Every draft is posted with a countdown. `autopilot_delay_minutes` (default 10) with no tap, it sends. Tap HOLD and it waits for you like manual. Tap SEND NOW and it goes immediately. Replying with an edit always takes it off the clock.

Every morning at `digest_hour` you get one message listing what went out without you in the last day.

## Hard stops that hold in every mode

A draft that trips any of these waits for a human, whatever the mode. They are in code, not in a prompt, so an email cannot talk the bot past them.

| Stop | Where |
|---|---|
| The drafter output ESCALATE (calls, contracts, never-answer list) | prompt output, enforced in `bot.py` |
| Any amount at or above `ceiling_amount` | `modes.over_ceiling` |
| Two look-alike domains in the thread | `modes.lookalike` |
| A keyword from `never_answer_keywords` in the draft | `modes.hard_stops` |
| The stop file exists | `config.paused` |

## The stop file beats everything

```
touch ~/.config/inbox-agent/PAUSED     # nothing sends, nothing drafts, in any mode
rm ~/.config/inbox-agent/PAUSED        # carries on
```

Or `/pause` and `/resume` in Telegram. Drafts are not lost while paused. They sit in Gmail where they were.

## When to move up

Move from manual to assisted after a run of drafts you did not edit. Move from assisted to autopilot after a longer run with the assisted sends holding up. There is no right number. Pull yours from `bot.log`: count `sent` lines against `rewrote` lines. If you are editing one in five, stay where you are and fix the playbook.
