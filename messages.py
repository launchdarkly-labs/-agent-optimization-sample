"""Synthetic incoming messages the optimizer replays against each candidate.

Diverse on purpose (tone, intent, length, register, emotional charge) so the winning draft
prompt generalizes instead of overfitting to one kind of message. Keep these synthetic — no
real inbox content in the shipped repo. For your own private use, swap in a local (gitignored)
file of real messages.

The optimization here is a candidate generator, not a training run: each turn the agent
replies to all of these in one call and the judge averages GPTZero across the replies. The
defensible winner-vs-baseline comparison is a separate side-by-side eval (see the tutorial),
not something this code performs.
"""

SYNTHETIC_MESSAGES = [
    "Hey! Are you free Saturday for dinner? A few of us are getting together and it'd be great to see you.",
    "Hi, I came across your background and I'm hiring for a senior role that looks like a strong fit. Open to a quick call this week?",
    "It's been way too long! I'll be in town Thursday and Friday. Any chance you're around to grab coffee?",
    "Just a reminder that your dentist appointment is Tuesday at 2pm. Reply to confirm or let us know if you need to reschedule.",
    "Hey neighbor, a package addressed to you was left at my door by mistake. Want to swing by this weekend to grab it?",
    "Hi love, are you planning to come home for the holidays? I want to book flights soon, so let me know.",
    "We'd love for you to join us for Maya's birthday dinner on the 15th. Can you make it?",
    "Quick question, did you ever send me that recipe you mentioned at the party? Still thinking about it.",
    "Following up on my last note. Were you able to take a look at the photos from the trip?",
    "Your book club pick is due back at the library Friday. Want me to renew it for you?",
]


def batch_prompt(messages: list[str] = SYNTHETIC_MESSAGES) -> str:
    """The single user input the agent drafts against each turn: reply to every message in one
    call, returning JSON. Used as the optimization's lone userInputOption AND as the agent's
    prompt, so the UI's recorded input matches what the agent actually drafted."""
    listing = "\n\n".join(f"Message {i + 1}:\n{m}" for i, m in enumerate(messages))
    return (
        f"Write a reply to each of the {len(messages)} messages below. Return ONLY a JSON "
        'object {"replies": ["<reply to Message 1>", "<reply to Message 2>", ...]} with one '
        "reply per message, in the same order.\n\n" + listing
    )
