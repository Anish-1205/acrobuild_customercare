"""Interpretation policy limited to general/freechat turns."""

FREECHAT_TYPO_POLICY = (
    "For general/freechat messages, use MEDIUM typo tolerance: interpret one or two obvious "
    "character omissions, insertions, substitutions or transpositions per word, missing spaces, "
    "and common romanization variants when the surrounding sentence makes the meaning clear. "
    "Do not treat romanized Indian languages as misspelled English. Preserve the requested reply "
    "language and script. Do not silently change names, numbers, dates, negation or identifiers. "
    "If multiple meanings remain plausible, or a referent is missing from the conversation, "
    "ask one short clarification in the customer's language instead of guessing. Heavy corruption "
    "requires clarification. Correct obvious typos silently; do not lecture about spelling. "
)
