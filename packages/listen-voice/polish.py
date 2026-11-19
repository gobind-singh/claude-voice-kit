"""Polish raw speech-to-text output: spacing, capitals, end punctuation, known names.

Parakeet-unified (and many other models) return text like "do everything plan for all " with no
final full stop or question mark. This module fixes that instantly, with no model involved.
Deeper fixes (commas, misheard words) are left to the caller, e.g. an LLM step.
"""
import re

WH_WORDS = {"what", "why", "how", "when", "where", "who", "whom", "whose", "which"}
AUXILIARIES = {
    "is", "are", "was", "were", "am", "do", "does", "did", "can", "could", "would",
    "should", "will", "shall", "may", "might", "must", "have", "has", "had",
    "isn't", "aren't", "don't", "doesn't", "didn't", "can't", "couldn't", "won't",
    "wouldn't", "shouldn't", "haven't", "hasn't",
}
# "Do you…" is a question, "Do everything…" is an instruction: an auxiliary only starts a
# question when a subject follows it.
SUBJECTS = {"i", "you", "we", "they", "he", "she", "it", "this", "that", "these", "those",
            "there", "the", "a", "an", "my", "your", "our", "its", "his", "her", "their", "anyone",
            "someone", "everyone", "anything", "something", "everything"}
TAG_QUESTIONS = re.compile(r"\b(right|okay|ok|correct|yes or no)\s*$", re.I)


def fix_vocabulary(text, vocabulary=None, aliases=None):
    """Apply exact-case names ("herdr", "Kokoro") and spoken aliases ("harder" -> "herdr")."""
    for wrong, right in (aliases or {}).items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text, flags=re.I)
    for term in vocabulary or []:
        text = re.sub(rf"\b{re.escape(term)}\b", term, text, flags=re.I)
    return text


def is_question(t):
    words = re.findall(r"[a-z']+", t.lower())
    if not words:
        return False
    first = re.sub(r"'(s|re|ll|d)$", "", words[0])          # what's -> what
    if first in WH_WORDS:
        return True
    if first in AUXILIARIES and len(words) > 1 and words[1] in SUBJECTS and \
            not (words[1] == "everything" and first == "do"):
        return True
    return bool(TAG_QUESTIONS.search(t))


def polish(text, vocabulary=None, aliases=None):
    t = (text or "").replace(" ", " ")
    t = re.sub(r"\s+", " ", t).strip()                     # trim + collapse spaces
    t = re.sub(r"\s+([,.;:?!])", r"\1", t)                 # no space before punctuation
    t = re.sub(r"([,;:?!])(?=[A-Za-z])", r"\1 ", t)        # one space after punctuation
    if not t:
        return ""
    t = fix_vocabulary(t, vocabulary, aliases)
    t = re.sub(r"\bi\b", "I", t)                           # "i think" -> "I think"
    t = t[0].upper() + t[1:]                               # capital first letter
    t = re.sub(r"([.?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)
    if t[-1] not in ".?!":
        t += "?" if is_question(t) else "."
    return t


if __name__ == "__main__":
    for s in ["do everything plan for all ", "  is it done", "first provide me the plan", "what's happening",
              "tell harder to run the tests", "i think it works , right", "New PR"]:
        print(repr(s), "->", repr(polish(s, ["herdr"], {"harder": "herdr", "hider": "herdr"})))
