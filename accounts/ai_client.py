import time
from typing import List, Dict, Tuple
from openai import OpenAI, APIConnectionError, RateLimitError, APIError
from django.conf import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)
MODEL = settings.OPENAI_MODEL

# --- Backoff wrapper (handles 429s/transient errors) ---
def _chat_with_backoff(messages: List[Dict], max_retries: int = 3, **kwargs):
    delay = 1.5
    last_err = None
    for _ in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
            )
            return resp.choices[0].message.content or ""
        except (RateLimitError, APIConnectionError, APIError) as e:
            last_err = e
            time.sleep(delay)
            delay *= 2
    raise last_err or RuntimeError("OpenAI request failed")

# --- Prompt builders ---
def _style_blurb(style_summary: dict) -> str:
    tone = ", ".join(style_summary.get("tone_adjectives", [])[:5]) or style_summary.get("onboarding_style_keywords","")
    formality = style_summary.get("formality","neutral")
    cadence = style_summary.get("cadence","")
    vocab = style_summary.get("vocabulary_level","moderate")
    do_rules = style_summary.get("style_do", [])[:6]
    dont_rules = style_summary.get("style_dont", [])[:6]
    sent_len = style_summary.get("avg_sentence_length", 14)
    para_len = style_summary.get("avg_paragraph_length", 3)

    do_txt = "; ".join(do_rules) if do_rules else ""
    dont_txt = "; ".join(dont_rules) if dont_rules else ""

    return (
        f"Imitate the user's style: tone={tone}; formality={formality}; cadence={cadence}; "
        f"vocabulary={vocab}; avg_sentence_length≈{sent_len} words; avg_paragraph_length≈{para_len} sentences. "
        f"Follow these DO rules: {do_txt}. Avoid these DON'Ts: {dont_txt}."
    )

def _blog_system(style_summary: dict) -> str:
    return (
        "You are an SEO blog writer. Write scannable, helpful blog posts between 800 to 1200 words with headings, bullets, and examples. "
        + _style_blurb(style_summary)
    )

def _linkedin_system(style_summary: dict) -> str:
    return "You write concise LinkedIn posts with a strong hook and clear CTA. " + _style_blurb(style_summary)

# --- Public functions (drop-in replacements for stubs) ---

def generate_blog(topic: str, style_summary: dict) -> Tuple[str, dict]:
    sys = _blog_system(style_summary)
    user = (
        f"Write an SEO-friendly blog draft between 800-1200 words for the topic: '{topic}'. "
        "Include: H1, 3–5 H2 sections, bullets, a short summary, and a CTA. "
        "Return pure markdown."
    )
    content = _chat_with_backoff(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
    )
    meta = _chat_with_backoff(
        [{"role": "system", "content": "You write SEO metadata only. Return valid JSON."},
         {"role": "user", "content": f"Generate {{\"meta_title\",\"meta_description\",\"keywords\"}} for: {topic}"}],
    )
    # Very light guard against the model returning text not JSON—store as string if needed
    try:
        import json
        meta_json = json.loads(meta)
        if "keywords" in meta_json and isinstance(meta_json["keywords"], str):
            meta_json["keywords"] = [k.strip() for k in meta_json["keywords"].split(",") if k.strip()]
    except Exception:
        meta_json = {"meta_title": topic, "meta_description": "", "keywords": []}
    return content, meta_json

def generate_linkedin(topic: str, style_summary: dict) -> Tuple[str, dict]:
    sys = _linkedin_system(style_summary)
    user = (
        f"Write a LinkedIn post about '{topic}'. Hook in first line. 5–8 short lines total. "
        "End with a question. Include 3-5 relevant hashtags on the last line."
    )
    content = _chat_with_backoff(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
    )
    # Extract hashtags to meta
    import re
    tags = re.findall(r"#\w+", content)
    return content, {"hashtags": tags[:6]}

def improve_content(item_type: str, prev_body: str, style_summary: dict, opts: dict) -> Tuple[str, dict]:
    sys = _blog_system(style_summary) if item_type == "BLOG" else _linkedin_system(style_summary)
    knobs = (
        f"Length={opts.get('length','medium')}, Tone={opts.get('tone','as_is')}, "
        f"Add example={opts.get('add_example', False)}, Add data={opts.get('add_data', False)}. "
        f"Note: {opts.get('custom_note','').strip()}"
    )
    user = (
        "Improve the following draft in-place without changing the core message. "
        "Return the full revised content in the same format.\n\n"
        f"Knobs: {knobs}\n\n---\n{prev_body}"
    )
    content = _chat_with_backoff(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
    )
    return content, {"improved": True, "knobs": opts}

def change_topic(item_type: str, new_topic: str, style_summary: dict) -> Tuple[str, dict]:
    return (
        generate_blog(new_topic, style_summary)
        if item_type == "BLOG"
        else generate_linkedin(new_topic, style_summary)
    )

def analyze_style_profile(corpus: str, onboarding_keywords: str = "") -> dict:
    """
    Returns a JSON dict describing the user's style based on their uploads.
    """
    sys = "You are a writing-style analyst. You read a corpus and output a compact JSON profile of how the author writes."
    user = f"""
    Analyze the following writing samples and return a STRICT JSON object with these keys:
    - tone_adjectives: array of 3-7 adjectives
    - formality: one of ["casual","neutral","formal"]
    - cadence: description of rhythm/sentence flow (1-2 short phrases)
    - avg_sentence_length: number (approx words)
    - avg_paragraph_length: number (approx sentences)
    - sentence_patterns: array of 3-6 recurring patterns (e.g., asks rhetorical questions, starts with imperative)
    - punctuation_habits: 2-4 notes
    - vocabulary_level: one of ["simple","moderate","advanced"]
    - jargon_domains: array of domain terms frequently used
    - thematic_pillars: array of 3-8 recurring themes/topics
    - hook_styles: array of 2-5 typical opening moves
    - call_to_action_styles: array of 2-4 CTA patterns
    - emoji_usage: "none","light","moderate","heavy"
    - link_usage: "rare","sometimes","frequent"
    - style_do: array of 5-10 "do" rules for imitating the style
    - style_dont: array of 5-10 "don't" rules to avoid
    - voice_summary: 1-2 sentence summary

    If onboarding keywords are present, bias the analysis toward them but do not simply repeat them.

    Onboarding keywords (optional): {onboarding_keywords}

    CORPUS (truncated for analysis):
    \"\"\"{corpus}\"\"\"
    Return ONLY JSON, no prose.
    """
    raw = _chat_with_backoff(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_completion_tokens=900,

    )
    import json
    try:
        return json.loads(raw)
    except Exception:
        # Safe fallback so UI doesn't break
        return {"voice_summary": "Could not parse analyzer output.", "raw": raw[:2000]}

def generate_meta_from_body(body_md: str) -> dict:
    sys = "You write SEO metadata only. Return VALID JSON."
    user = (
        "Given the following article (markdown), return a JSON object with keys "
        '"meta_title","meta_description","keywords" (array of up to 8 terms). '
        "Use the strongest keyword themes actually present in the draft.\n\n"
        f"{body_md}"
    )
    raw = _chat_with_backoff(
        [{"role":"system","content":sys},{"role":"user","content":user}],
        max_tokens=220, temperature=0.3
    )
    import json
    try:
        j = json.loads(raw)
        if isinstance(j.get("keywords"), str):
            j["keywords"] = [k.strip() for k in j["keywords"].split(",") if k.strip()]
        return {"meta_title": j.get("meta_title",""),
                "meta_description": j.get("meta_description",""),
                "keywords": j.get("keywords", [])[:8]}
    except Exception:
        return {}

# --- Image search term suggestion (for banner ideas) ---
def suggest_image_search_term(body_md: str, item_type: str, topic: str) -> str:
    """
    Returns ONE short search phrase (3 words) suitable for image libraries.
    Example: "UX blog banner", "SaaS dashboard hero".
    """
    sys = "You create short, concrete image search queries for banner/hero graphics."
    user = (
        f"Draft type: {item_type}. Topic: {topic}.\n"
        "From the draft (markdown) below, produce ONE search phrase (3 words) "
        "that a designer would use to find banner/hero images. "
        "Avoid quotes. No punctuation. No hashtags.\n\n"
        f"{(body_md or '')[:4000]}"
    )
    q = _chat_with_backoff(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
    )
    # sanitize a bit
    return (q or "").strip().strip('"').replace("#", "")

def generate_style_fun_facts(style_summary: dict, corpus_text: str) -> list[str]:
    """
    Returns up to 10 short, playful, *user-specific* fun facts about the user's writing.
    Each fact must be <= 120 chars and standalone (no numbering).
    Keep it light; do not reveal sensitive info beyond writing analysis.
    If input is too small/empty, return [].
    """
    # Require some signal to avoid hallucinations
    if not (corpus_text and corpus_text.strip()):
        return []

    # Trim LARGE corpora to keep tokens sane
    sample = corpus_text[:12000]

    sys = (
        "You are an assistant that analyzes a user's writing style and returns playful, factual observations. "
        "Focus on text stats (common words, avg sentence length), tone, pacing, themes, rhetorical habits, "
        "and *light* comparisons (e.g., 'similar to [public figure]' only if stylistically plausible). "
        "It is okay to include a humorous zodiac guess as a **guess**, clearly marked as playful."
    )
    user = (
        "Given the user's writing sample and a prior style summary JSON, output EXACTLY 10 bullet lines, "
        "each <= 120 characters, with no numbering. Use concise statements. Examples:\n"
        "- Your most used noun is “growth”.\n"
        "- Avg sentence length: 17 words.\n"
        "- You ask 1.3 questions per 100 words.\n"
        "- You love em dashes — a lot.\n"
        "- Your cadence is closest to [Famous Person].\n"
        "- Playful guess: Your zodiac vibe: Virgo.\n\n"
        f"STYLE SUMMARY:\n{style_summary}\n\n"
        "WRITING SAMPLE (markdown/plain):\n"
        f"{sample}\n\n"
        "Return as plain text, one fact per line, no bullets, no numbers, no extra commentary."
    )

    raw = _chat_with_backoff(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_completion_tokens=500,
        temperature=0.7,
    )
    if not raw:
        return []
    lines = [ln.strip(" -•\t") for ln in raw.splitlines() if ln.strip()]
    # keep first 10, trim overly long lines defensively
    facts = [ln[:120] for ln in lines][:10]
    # return whatever we have, even if only 1–2 lines
    return facts