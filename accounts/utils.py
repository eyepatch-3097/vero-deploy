from PyPDF2 import PdfReader
import io, re
from collections import Counter
from .models import CreditTransaction
from datetime import datetime

ALLOWED_EXTS = {".txt": "TXT", ".pdf": "PDF"}

def extract_text_from_file(f, file_type: str) -> str:
    if file_type == "TXT":
        data = f.read()
        if isinstance(data, bytes):
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("latin-1", errors="ignore")
        return str(data)
    elif file_type == "PDF":
        # PyPDF2 expects a file-like object; if InMemoryUploadedFile, it already is
        reader = PdfReader(f)
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        return "\n".join(texts)
    return ""

def simple_style_summary(onboarding_keywords: str, corpus: str) -> dict:
    # v0: very basic stats; we’ll replace with GPT later
    clean = re.sub(r"\s+", " ", corpus).strip()
    words = re.findall(r"[A-Za-z’']+", clean.lower())
    total_words = len(words)
    sentences = re.split(r"[.!?]+", clean)
    sentences = [s.strip() for s in sentences if s.strip()]
    avg_sentence_len = round(total_words / max(1, len(sentences)), 2)

    common = Counter(words)
    top_words = [w for w, c in common.most_common(10) if len(w) > 3]

    return {
        "source_words": total_words,
        "sentence_count": len(sentences),
        "avg_sentence_len": avg_sentence_len,
        "top_words": top_words,
        "onboarding_style_keywords": onboarding_keywords or "",
        "notes": "v0 heuristic profile; replace with GPT in next phase.",
    }

def record_credit_change(user, amount: int, kind: str, note: str=""):
    """Adjust user balance and record a transaction."""
    user.credits = max(0, user.credits + amount)
    user.save(update_fields=["credits"])
    CreditTransaction.objects.create(
        user=user,
        kind=kind,
        amount=amount,
        balance_after=user.credits,
        note=note
    )

def stub_generate_content(content_type: str, topic: str, style_summary: dict) -> tuple[str, dict]:
    """
    Returns (body_md, meta_json) as a stub.
    Later, replace this with an OpenAI call using style_summary.
    """
    tone = style_summary.get("onboarding_style_keywords", "") or "clear, friendly"
    top_words = style_summary.get("top_words", [])[:5]
    top_words_str = ", ".join(top_words) if top_words else "insights, strategy"

    if content_type == "BLOG":
        meta = {
            "meta_title": f"{topic} – Practical Guide",
            "meta_description": f"An approachable take on {topic} with {tone} tone.",
            "keywords": [topic] + top_words,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }
        body = f"""# {topic}

(*Tone hint: {tone}*)

## Why this matters
A short, practical explanation tying **{topic}** to outcomes. Use common terms like {top_words_str}.

## Key ideas
- Point 1
- Point 2
- Point 3

## What to do next
Close with a clear CTA and an example relevant to your audience.

*This is a stub draft for wiring credits & history. Replace via GPT later.*
"""
        return body, meta

    # LinkedIn
    meta = {"hashtags": ["#marketing", "#d2c", "#cx"], "generated_at": datetime.utcnow().isoformat() + "Z"}
    body = f"""👉 {topic}

Hot take in a {tone} tone.

• One crisp insight
• One relatable example
• One nudge to act

{ " ".join(meta["hashtags"]) }

*Stub draft – replace with GPT later.*
"""
    return body, meta

def stub_improve_content(item_type: str, prev_body: str, style_summary: dict, opts: dict) -> tuple[str, dict]:
    # This is a very naive modifier; later replace with GPT using opts + style_summary
    length = opts.get("length","medium")
    tone = opts.get("tone","as_is")
    add_example = opts.get("add_example", False)
    add_data = opts.get("add_data", False)
    note = opts.get("custom_note","").strip()

    body = prev_body

    # tone shim
    if tone == "casual":
        body += "\n\n_Plus-up: softened tone and conversational phrasing._"
    elif tone == "formal":
        body += "\n\n_Plus-up: tightened tone and more formal wording._"

    # length shim
    if length == "short":
        body += "\n\n_(Edited for brevity.)_"
    elif length == "long":
        body += "\n\n_(Expanded with a bit more detail.)_"

    if add_example:
        body += "\n\n**Example:** A D2C skincare brand turned CS tickets into Reels ideas and saw 18% more saves."

    if add_data:
        body += "\n\n**Data nugget:** Brands posting 3–4/week with conversation starters see ~12–20% higher comment rates."

    if note:
        body += f"\n\n_Note applied:_ {note}"

    meta = {"improved": True}
    return body, meta

def stub_change_topic_content(item_type: str, new_topic: str, style_summary: dict) -> tuple[str, dict]:
    # Reuse the original stub generator but for a new topic
    return stub_generate_content(item_type, new_topic, style_summary)

# accounts/utils.py
def merge_user_inputs_into_profile_json(summary: dict, onboarding) -> dict:
    summary = dict(summary or {})
    # inject/overwrite keys the UI expects
    summary["industry"] = getattr(onboarding, "industry", "") or summary.get("industry", "")
    summary["user_topical_keywords"] = parse_keywords(getattr(onboarding, "topical_keywords", ""))  # list
    summary["style_keywords"] = parse_keywords(getattr(onboarding, "writing_style_keywords", ""))   # list
    summary["author_bio"] = getattr(onboarding, "bio", "") or summary.get("author_bio", "")
    summary["user_style_self_desc"] = getattr(onboarding, "style_self_desc", "") or summary.get("user_style_self_desc", "")
    summary["goals"] = getattr(onboarding, "goals", "") or summary.get("goals", "")
    return summary

def parse_keywords(s: str):
    if not s: return []
    # split by commas or newlines, strip, dedupe
    raw = [x.strip() for x in re.split(r"[,;\n]", s) if x.strip()]
    return list(dict.fromkeys(raw))[:20]

# accounts/utils.py
def style_scores_from_profile(profile_json: dict) -> dict:
    pj = profile_json or {}
    # Normalize a few dimensions to 0..10
    avg_sent = pj.get("avg_sentence_length", 14) or 14
    avg_para = pj.get("avg_paragraph_length", 3) or 3
    formality = {"casual":3, "neutral":5, "formal":8}.get(pj.get("formality","neutral"), 5)
    vocab = {"simple":3, "moderate":6, "advanced":9}.get(pj.get("vocabulary_level","moderate"), 6)
    emoji = {"none":1, "light":4, "moderate":7, "heavy":9}.get(pj.get("emoji_usage","none"), 1)
    # heuristic mappings
    informational = min(10, 4 + len(pj.get("thematic_pillars", [])))
    persuasive = min(10, 3 + len(pj.get("call_to_action_styles", [])))
    # sentence length: mid-range (12-18) gets higher score
    sent_score = 10 - min(10, abs((avg_sent or 14) - 15))
    para_score = max(1, min(10, int( (avg_para/4)*10 )))  # rough
    emotion = min(10, 3 + len([t for t in (pj.get("tone_adjectives") or []) if t.lower() in {"warm","excited","bold","empathetic","fun"}]))

    return {
        "Emotion": emotion,
        "Informational": informational,
        "Persuasiveness": persuasive,
        "Formality": formality,
        "Vocabulary": vocab,
        "Emoji usage": emoji,
        "Sentence length": max(1, min(10, int(sent_score))),
    }