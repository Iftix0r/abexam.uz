import json
import os

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """Siz AbExam platformasining AI yordamchisisiz. Foydalanuvchilarga IELTS imtihoniga tayyorlanishda,
lug'at boyligini oshirishda va platformadan foydalanishda yordam berasiz.
Javoblarni har doim o'zbek tilida bering. Qisqa va aniq javob bering."""

SPEAKING_EVAL_PROMPT = """You are an expert IELTS Speaking examiner. Evaluate the following spoken response transcript strictly.
Return ONLY a valid JSON object with this exact structure (no markdown, no extra text):
{
  "band": <float 1.0-9.0 in 0.5 steps>,
  "fluency_coherence": <float 1.0-9.0 in 0.5 steps>,
  "lexical_resource": <float 1.0-9.0 in 0.5 steps>,
  "grammatical_range": <float 1.0-9.0 in 0.5 steps>,
  "pronunciation": <float 1.0-9.0 in 0.5 steps>,
  "word_count": <int>,
  "strengths": [<string>, <string>],
  "improvements": [<string>, <string>, <string>],
  "feedback": "<2-3 sentence overall feedback in Uzbek language>",
  "sample_phrases": [<string>, <string>]
}
Note: pronunciation score should be estimated from written features (word choice, complexity). Be strict and realistic."""

WRITING_EVAL_PROMPT = """You are an expert IELTS examiner. Evaluate the following IELTS Writing Task 2 essay strictly.
Return ONLY a valid JSON object with this exact structure (no markdown, no extra text):
{
  "band": <float 1.0-9.0 in 0.5 steps>,
  "task_achievement": <float 1.0-9.0 in 0.5 steps>,
  "coherence_cohesion": <float 1.0-9.0 in 0.5 steps>,
  "lexical_resource": <float 1.0-9.0 in 0.5 steps>,
  "grammatical_accuracy": <float 1.0-9.0 in 0.5 steps>,
  "strengths": [<string>, <string>],
  "improvements": [<string>, <string>, <string>],
  "feedback": "<2-3 sentence overall feedback in Uzbek language>"
}
Be strict and realistic. A 250-word essay cannot score above 6.5. Less than 150 words: max 5.0."""


def get_ai_response(message, history=None):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": message})
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Xatolik yuz berdi: {str(e)}"


def evaluate_writing(text: str) -> dict:
    """
    Evaluate an IELTS Writing Task 2 essay using GPT-4o-mini.
    Returns a dict with band scores and feedback, or falls back to word-count scoring on error.
    """
    if not text or not text.strip():
        return _fallback_writing_eval("")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": WRITING_EVAL_PROMPT},
                {"role": "user", "content": f"Essay to evaluate:\n\n{text[:3000]}"},
            ],
            temperature=0.3,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        return {
            "band": _clamp_band(data.get("band", 5.0)),
            "task_achievement": _clamp_band(data.get("task_achievement", 5.0)),
            "coherence_cohesion": _clamp_band(data.get("coherence_cohesion", 5.0)),
            "lexical_resource": _clamp_band(data.get("lexical_resource", 5.0)),
            "grammatical_accuracy": _clamp_band(data.get("grammatical_accuracy", 5.0)),
            "strengths": data.get("strengths", [])[:3],
            "improvements": data.get("improvements", [])[:3],
            "feedback": data.get("feedback", ""),
            "ai_graded": True,
        }
    except Exception:
        return _fallback_writing_eval(text)


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Transcribe audio using OpenAI Whisper API. Returns transcript text."""
    import io
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename
    try:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en",
        )
        return transcript.text.strip()
    except Exception as e:
        return f"[Transcription error: {e}]"


def evaluate_speaking(transcript: str, question: str = "") -> dict:
    """
    Evaluate an IELTS Speaking response from its transcript.
    Returns dict with band scores and feedback, or fallback on error.
    """
    if not transcript or not transcript.strip() or transcript.startswith("[Transcription error"):
        return _fallback_speaking_eval(transcript)

    context = f"Question: {question}\n\nTranscript: {transcript[:2000]}" if question else f"Transcript: {transcript[:2000]}"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SPEAKING_EVAL_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=0.3,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return {
            "band": _clamp_band(data.get("band", 5.0)),
            "fluency_coherence": _clamp_band(data.get("fluency_coherence", 5.0)),
            "lexical_resource": _clamp_band(data.get("lexical_resource", 5.0)),
            "grammatical_range": _clamp_band(data.get("grammatical_range", 5.0)),
            "pronunciation": _clamp_band(data.get("pronunciation", 5.0)),
            "word_count": int(data.get("word_count", len(transcript.split()))),
            "strengths": data.get("strengths", [])[:3],
            "improvements": data.get("improvements", [])[:3],
            "feedback": data.get("feedback", ""),
            "sample_phrases": data.get("sample_phrases", [])[:2],
            "transcript": transcript,
            "ai_graded": True,
        }
    except Exception:
        return _fallback_speaking_eval(transcript)


def _fallback_speaking_eval(transcript: str) -> dict:
    words = len(transcript.split()) if transcript else 0
    band = 5.0 if words > 30 else 4.0
    return {
        "band": band,
        "fluency_coherence": band,
        "lexical_resource": band,
        "grammatical_range": band,
        "pronunciation": band,
        "word_count": words,
        "strengths": [],
        "improvements": ["Javobni kengaytiring va misollar keltiring"],
        "feedback": f"Javob {words} so'zdan iborat. AI baholash vaqtincha mavjud emas.",
        "sample_phrases": [],
        "transcript": transcript or "",
        "ai_graded": False,
    }


def _clamp_band(value) -> float:
    """Round to nearest 0.5 and clamp to [1.0, 9.0]."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 5.0
    v = round(v * 2) / 2
    return max(1.0, min(9.0, v))


# ── IELTS Exam Generator ────────────────────────────────────────────────────────

_GENERATOR_SYSTEM = """You are an expert IELTS test writer with 15 years of experience creating official Cambridge-style exams.
You write 100% original, plagiarism-free content that follows IELTS standards precisely.
Always return ONLY valid JSON — no markdown, no commentary, no extra text."""

_READING_ACADEMIC = """Create a complete IELTS Academic Reading passage and questions. Topic hint: {topic}

Return JSON:
{{
  "passage_title": "...",
  "passage": "...(600-750 words, formal academic style, complex ideas)...",
  "questions": [
    {{"order":1,"text":"...statement...","question_type":"tfng","correct_answer":"TRUE","options":[{{"key":"TRUE","text":"TRUE"}},{{"key":"FALSE","text":"FALSE"}},{{"key":"NOT GIVEN","text":"NOT GIVEN"}}],"explanation":"..."}},
    ... (5 more tfng),
    {{"order":7,"text":"The author argues that ___ has increased significantly.","question_type":"gap_fill","correct_answer":"exact phrase from passage","options":[],"explanation":"..."}},
    ... (4 more gap_fill),
    {{"order":12,"text":"What is the main purpose of the passage?","question_type":"mcq","correct_answer":"B","options":[{{"key":"A","text":"..."}},{{"key":"B","text":"..."}},{{"key":"C","text":"..."}},{{"key":"D","text":"..."}}],"explanation":"..."}},
    {{"order":13,...mcq...}},{{"order":14,...mcq...}}
  ]
}}
Rules:
- 6 TRUE/FALSE/NOT GIVEN questions (orders 1-6)
- 5 gap-fill (orders 7-11): answers must be exact 1-3 word phrases from the passage
- 3 MCQ (orders 12-14): one clearly correct answer
- All 14 questions must have non-empty correct_answer"""

_READING_GENERAL = """Create an IELTS General Training Reading section. Topic hint: {topic}
Include ONE short text (200-250 words, e.g. advertisement, notice, letter) and ONE longer text (400-450 words, e.g. article, report).

Return JSON:
{{
  "passage_title": "...",
  "passage": "...(short text first, then longer text, total 600-700 words)...",
  "questions": [
    (5 tfng for short text, 8 gap_fill/mcq for longer text — 13 total)
  ]
}}"""

_LISTENING_SECTION = """Create an IELTS Listening section transcript and questions. Context: {topic}. Section type: {listen_type}.

Return JSON:
{{
  "section_title": "...",
  "audio_script": "...(full spoken conversation/monologue transcript, 300-400 words)...",
  "questions": [
    {{"order":1,"text":"...","question_type":"gap_fill","correct_answer":"exact spoken word(s)","options":[],"explanation":"..."}},
    ... (mix of 6 gap_fill and 4 mcq, orders 1-10)
  ]
}}
Rules:
- gap_fill answers must be 1-3 words actually spoken in the audio_script
- MCQ must have 3 options (A/B/C)"""

_WRITING_TASKS = """Create IELTS Writing Task 1 and Task 2 for {variant} IELTS. Topic area: {topic}

Return JSON:
{{
  "task1": {{
    "title": "Writing Task 1: ...",
    "instruction": "...(describe the {chart_type} below. Summarise the main features and make comparisons. Write at least 150 words.)...",
    "data_description": "...(describe what the chart/graph shows: specific numbers, labels, years — enough for a student to write about it without seeing the actual image)...",
    "sample_answer_notes": "...(key points a good answer should cover)..."
  }},
  "task2": {{
    "title": "Writing Task 2: ...",
    "question": "...(clear IELTS-style essay question, {essay_type} type)...",
    "instruction": "Write at least 250 words."
  }}
}}"""

_SPEAKING_PARTS = """Create IELTS Speaking Part 1, 2, and 3 questions. Topic: {topic}

Return JSON:
{{
  "part1_questions": [
    {{"order":1,"text":"...personal question...","explanation":"Tip: speak 2-4 sentences, use present tense"}},
    {{"order":2,...}},
    {{"order":3,...}}
  ],
  "part2_card": {{
    "order":1,
    "text":"Describe {cue_card_topic}. You should say:\\n• ...\\n• ...\\n• ...\\nand explain ...",
    "explanation":"Prepare 1 minute, speak 1-2 minutes. Use past tense."
  }},
  "part3_questions": [
    {{"order":1,"text":"...abstract/analytical question related to topic...","explanation":"40-60 seconds. Use hedging: I think, It seems..."}},
    {{"order":2,...}},
    {{"order":3,...}}
  ]
}}"""

import random

_TOPICS_ACADEMIC = [
    "climate change and renewable energy", "urbanisation and migration",
    "artificial intelligence and employment", "ocean conservation",
    "the psychology of learning", "space exploration economics",
    "biodiversity loss", "digital privacy and surveillance",
    "the future of healthcare", "sustainable agriculture",
    "cultural heritage preservation", "water scarcity",
]
_TOPICS_GENERAL = [
    "community volunteering", "workplace wellbeing", "public transport improvements",
    "local tourism", "library services", "recycling programmes",
    "neighbourhood safety", "adult education", "sports facilities",
]
_CHART_TYPES = ["bar chart", "line graph", "pie chart", "table", "process diagram", "map"]
_ESSAY_TYPES = ["discuss both views and give your opinion", "to what extent do you agree or disagree",
                "what are the causes and what solutions can be offered",
                "what are the advantages and disadvantages"]
_LISTEN_TYPES = [
    ("social", "Two people discussing a community event"),
    ("campus", "A student enquiring about university services"),
    ("academic", "A university lecture on a scientific topic"),
    ("workplace", "A job training session for new staff"),
]
_CUE_CARDS = [
    "a time you helped someone", "a memorable journey you took",
    "a skill you would like to learn", "an important decision you made",
    "a person who has influenced you", "a place you would like to visit",
]


def generate_ielts_exam(
    section_type: str,
    variant: str = 'academic',
    topic: str = '',
    model: str = 'gpt-4o',
) -> dict:
    """
    Generate a complete IELTS exam section (or full mock test).

    section_type: 'reading' | 'writing' | 'listening' | 'speaking' | 'full'
    variant: 'academic' | 'general'
    topic: optional topic hint (auto-selected if empty)
    Returns a dict matching seed JSON structure (exam + sections + questions).
    """
    topic = topic.strip() or random.choice(
        _TOPICS_ACADEMIC if variant == 'academic' else _TOPICS_GENERAL
    )
    variant_label = 'Academic' if variant == 'academic' else 'General Training'

    sections = []
    if section_type == 'reading':
        sections = _gen_reading(topic, variant, model)
    elif section_type == 'writing':
        sections = _gen_writing(topic, variant, model)
    elif section_type == 'listening':
        sections = _gen_listening(topic, model)
    elif section_type == 'speaking':
        sections = _gen_speaking(topic, model)
    elif section_type == 'full':
        sections = (
            _gen_listening(topic, model) +
            _gen_reading(topic, variant, model) +
            _gen_writing(topic, variant, model) +
            _gen_speaking(topic, model)
        )

    section_label = {
        'reading': 'Reading', 'writing': 'Writing',
        'listening': 'Listening', 'speaking': 'Speaking', 'full': 'Full Mock',
    }.get(section_type, section_type.title())

    return {
        "title": f"IELTS {variant_label} — {section_label} ({topic[:40]})",
        "exam_type": "mock" if section_type == 'full' else section_type,
        "price": 0,
        "duration_minutes": {"full": 170, "reading": 60, "writing": 60, "listening": 30, "speaking": 14}.get(section_type, 60),
        "is_active": False,
        "description": f"[cambridge] AI tomonidan yaratilgan IELTS {variant_label} {section_label} testi. Mavzu: {topic}",
        "sections": sections,
        "ai_metadata": {"variant": variant, "topic": topic, "section_type": section_type, "model": model},
    }


def _call_ai(prompt: str, model: str, max_tokens: int = 3000) -> dict:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _GENERATOR_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def _gen_reading(topic: str, variant: str, model: str) -> list:
    template = _READING_ACADEMIC if variant == 'academic' else _READING_GENERAL
    data = _call_ai(template.format(topic=topic), model, max_tokens=3500)
    questions = _normalise_questions(data.get("questions", []))
    return [{
        "title": f"Reading — {data.get('passage_title', 'Passage')}",
        "section_type": "reading",
        "order": 1,
        "duration_minutes": 60,
        "content": f"<div style='line-height:1.8;font-size:14px'><h3>{data.get('passage_title','')}</h3><p>{data.get('passage','').replace(chr(10),'</p><p>')}</p></div>",
        "questions": questions,
    }]


def _gen_writing(topic: str, variant: str, model: str) -> list:
    chart = random.choice(_CHART_TYPES)
    essay = random.choice(_ESSAY_TYPES)
    data = _call_ai(_WRITING_TASKS.format(variant=variant.title(), topic=topic, chart_type=chart, essay_type=essay), model, max_tokens=1500)
    t1 = data.get("task1", {})
    t2 = data.get("task2", {})
    return [
        {
            "title": t1.get("title", "Writing Task 1"),
            "section_type": "writing",
            "order": 1,
            "duration_minutes": 20,
            "content": f"<div style='line-height:1.8'><h3>Writing Task 1</h3><p>{t1.get('instruction','')}</p><div style='background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:16px;margin:12px 0;font-size:13px'>{t1.get('data_description','')}</div></div>",
            "questions": [{"order": 1, "text": f"Describe the {chart} below. Write at least 150 words.\n\n{t1.get('data_description','')}", "question_type": "writing_task", "correct_answer": "", "options": [], "explanation": t1.get("sample_answer_notes", ""), "word_limit": 150}],
        },
        {
            "title": t2.get("title", "Writing Task 2"),
            "section_type": "writing",
            "order": 2,
            "duration_minutes": 40,
            "content": f"<div style='line-height:1.8'><h3>Writing Task 2</h3><p>{t2.get('question','')}</p><p><strong>{t2.get('instruction','Write at least 250 words.')}</strong></p></div>",
            "questions": [{"order": 1, "text": t2.get("question", ""), "question_type": "writing_task", "correct_answer": "", "options": [], "explanation": "", "word_limit": 250}],
        },
    ]


def _gen_listening(topic: str, model: str) -> list:
    listen_type = random.choice(_LISTEN_TYPES)
    data = _call_ai(_LISTENING_SECTION.format(topic=topic, listen_type=listen_type[1]), model, max_tokens=2500)
    questions = _normalise_questions(data.get("questions", []))
    script = data.get("audio_script", "")
    content = f"<div style='line-height:1.8'><h3>{data.get('section_title', 'Listening')}</h3><p><strong>Topshiriq:</strong> Quyidagi audio transkriptni o'qing va savollarga javob bering.</p><details style='margin-top:12px'><summary style='cursor:pointer;font-size:13px;color:#888'>📄 Audio transkriptni ko'rish (amaliyot uchun)</summary><div style='margin-top:8px;padding:12px;background:rgba(255,255,255,.04);border-radius:8px;font-size:13px;line-height:1.7;white-space:pre-wrap'>{script}</div></details></div>"
    return [{
        "title": f"Listening — {data.get('section_title', 'Section')}",
        "section_type": "listening",
        "order": 1,
        "duration_minutes": 30,
        "content": content,
        "questions": questions,
    }]


def _gen_speaking(topic: str, model: str) -> list:
    cue = random.choice(_CUE_CARDS)
    data = _call_ai(_SPEAKING_PARTS.format(topic=topic, cue_card_topic=cue), model, max_tokens=1500)
    sections = []
    p1_qs = _normalise_questions(data.get("part1_questions", []))
    sections.append({"title": "Speaking — Part 1: Introduction", "section_type": "speaking", "order": 1, "duration_minutes": 5, "content": "<div><h3>Speaking Part 1</h3><p>Answer each question naturally. Aim for 2–4 sentences per answer.</p></div>", "questions": p1_qs})
    card = data.get("part2_card", {})
    sections.append({"title": "Speaking — Part 2: Long Turn", "section_type": "speaking", "order": 2, "duration_minutes": 4, "content": "<div><h3>Speaking Part 2</h3><p>Prepare 1 minute, then speak for 1–2 minutes.</p></div>", "questions": [{"order": 1, "text": card.get("text", ""), "question_type": "short_answer", "correct_answer": "", "options": [], "explanation": card.get("explanation", ""), "word_limit": 0}]})
    p3_qs = _normalise_questions(data.get("part3_questions", []))
    sections.append({"title": "Speaking — Part 3: Discussion", "section_type": "speaking", "order": 3, "duration_minutes": 5, "content": "<div><h3>Speaking Part 3</h3><p>Give analytical, extended answers. Aim for 40–60 seconds each.</p></div>", "questions": p3_qs})
    return sections


def _normalise_questions(raw: list) -> list:
    """Ensure every question dict has the fields the loader expects."""
    result = []
    for i, q in enumerate(raw, start=1):
        if not isinstance(q, dict):
            continue
        qtype = q.get("question_type", "gap_fill")
        if qtype == "short_answer" and "explanation" not in q:
            q["explanation"] = ""
        result.append({
            "order": q.get("order", i),
            "text": str(q.get("text", "")),
            "question_type": qtype,
            "correct_answer": str(q.get("correct_answer", "")),
            "options": q.get("options", []),
            "explanation": str(q.get("explanation", "")),
            "word_limit": int(q.get("word_limit", 0)),
        })
    return result


def _fallback_writing_eval(text: str) -> dict:
    """Word-count based fallback when AI is unavailable."""
    words = len(text.split()) if text else 0
    if words >= 350:
        band = 6.5
    elif words >= 300:
        band = 6.0
    elif words >= 250:
        band = 5.5
    elif words >= 200:
        band = 5.0
    elif words >= 150:
        band = 4.5
    elif words >= 100:
        band = 4.0
    else:
        band = 3.5
    return {
        "band": band,
        "task_achievement": band,
        "coherence_cohesion": band,
        "lexical_resource": band,
        "grammatical_accuracy": band,
        "strengths": [],
        "improvements": ["So'zlar sonini ko'paytirishga harakat qiling (250+ so'z tavsiya etiladi)"],
        "feedback": f"Esse {words} so'zdan iborat. AI baholash vaqtincha mavjud emas.",
        "ai_graded": False,
    }
