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
Note: pronunciation score should be estimated from written features (word choice, complexity). Be strict and realistic. If the transcript is very short or irrelevant, give a very low band (1.0-3.0). Do not give high scores for minimal effort. Answer the overall feedback in Uzbek.
IMPORTANT: A silent or empty transcript MUST result in a Band 0.0. A few words (under 10) should not score above 2.0. Be as critical as a real IELTS examiner. Only give 6.5+ for truly advanced responses."""

_WRITING_EVAL_BASE = """You are an expert IELTS examiner. Evaluate the following IELTS {task_label} strictly.
Return ONLY a valid JSON object with this exact structure (no markdown, no extra text):
{{
  "band": <float 1.0-9.0 in 0.5 steps>,
  "task_achievement": <float 1.0-9.0 in 0.5 steps>,
  "coherence_cohesion": <float 1.0-9.0 in 0.5 steps>,
  "lexical_resource": <float 1.0-9.0 in 0.5 steps>,
  "grammatical_accuracy": <float 1.0-9.0 in 0.5 steps>,
  "strengths": [<string>, <string>],
  "improvements": [<string>, <string>, <string>],
  "feedback": "<2-3 sentence overall feedback in Uzbek language>"
}}
{task_rules}
Be strict and realistic. An empty essay MUST score 0.0. Be very strict with grammar and vocabulary."""

_TASK1_RULES = "Task 1: Minimum 150 words. A very short response (<50 words) MUST NOT score above 3.0. Less than 150 words: max 5.0. Evaluate: overview accuracy, key feature selection, data referencing."
_TASK2_RULES = "Task 2: Minimum 250 words. A very short essay (<50 words) MUST NOT score above 3.0. Less than 150 words: max 5.0. Less than 250 words: max 6.5. Evaluate: argument development, position clarity, example quality."


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


def evaluate_writing(text: str, task_num: int = 2) -> dict:
    """
    Evaluate an IELTS Writing Task (1 or 2) using GPT-4o-mini.
    task_num=1 → Task 1 criteria; task_num=2 → Task 2 criteria.
    Returns a dict with band scores and feedback, or falls back to word-count scoring on error.
    """
    if not text or not text.strip():
        return _fallback_writing_eval("", task_num)

    is_task1 = task_num == 1
    prompt = _WRITING_EVAL_BASE.format(
        task_label="Writing Task 1 (report/letter)" if is_task1 else "Writing Task 2 (essay)",
        task_rules=_TASK1_RULES if is_task1 else _TASK2_RULES,
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Text to evaluate:\n\n{text[:3000]}"},
            ],
            temperature=0.3,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
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
        return _fallback_writing_eval(text, task_num)


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
        text = transcript.text or ""
        return text.strip()
    except Exception as e:
        return f"[Transcription error: {e}]"


def evaluate_speaking(transcript: str, question: str = "") -> dict:
    """
    Evaluate an IELTS Speaking response from its transcript.
    Returns dict with band scores and feedback, or fallback on error.
    """
    if not transcript or not str(transcript).strip() or str(transcript).startswith("[Transcription error"):
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
            "word_count": int(float(data.get("word_count") or len(transcript.split()))),
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
    if words == 0: band = 0.0
    elif words < 20: band = 2.0
    elif words < 50: band = 4.0
    else: band = 5.0
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

_GENERATOR_SYSTEM = """You are a Senior IELTS Examiner and Content Developer for Cambridge University Press. 
Your task is to generate AUTHENTIC, high-level IELTS exam materials.

CORE OPERATING PRINCIPLES:
1. FACTUAL ACCURACY: You must double-check all facts, data, and historical information. Do not hallucinate.
2. LOGICAL CONSISTENCY: Ensure that the correct answer is unambiguously correct based ON THE TEXT provided.
3. DISTRACTOR QUALITY: Distractors must be 'plausible'—meaning they should be mentioned in the text but incorrect in the context of the specific question.
4. VARIETY & DISTRIBUTION: 
   - 20% Easy (Direct information)
   - 40% Medium (Paraphrased information)
   - 40% Hard (Logical inference, tone analysis, subtle nuances)
5. SELF-VERIFICATION: Before outputting JSON, mentally verify every question against the passage to ensure there is zero ambiguity."""

_READING_ACADEMIC = """Create a 900-word IELTS Academic Reading passage on: {topic}

Requirements:
- Tone: Analytical, sophisticated, academic.
- Content: Include conflicting viewpoints, data-driven analysis, and complex arguments.

JSON Structure:
{{
  "passage_title": "...",
  "passage": "...",
  "questions": [
    {{"order":1,"text":"...","question_type":"tfng","correct_answer":"NOT GIVEN","options":[{{"key":"TRUE","text":"TRUE"}},{{"key":"FALSE","text":"FALSE"}},{{"key":"NOT GIVEN","text":"NOT GIVEN"}}],"explanation":"Detailed logical derivation..."}},
    ...
    {{"order":12,"text":"...","question_type":"mcq","correct_answer":"C","options":[{{"key":"A","text":"Logical trap A"}},{{"key":"B","text":"Logical trap B"}},{{"key":"C","text":"Nuanced correct answer"}},{{"key":"D","text":"Logical trap D"}],"explanation":"..."}}
  ],
  "key_vocabulary": [
    {{"word": "word1", "definition": "English definition", "uzbek": "o'zbekcha ma'nosi", "example": "example sentence from passage"}},
    ... (10-12 advanced words from the text)
  ]
}}
Items: 6 TFNG, 5 Gap-fill, 3 MCQ. Level: C1-C2."""

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

_LISTENING_SECTION = """Create an IELTS Listening {listen_type} transcript and 10 questions. Topic: {topic}

Logic Requirements:
- SELF-CORRECTION: Speakers should change their mind or correct details (e.g., changing a date, time, or name).
- AMBIGUITY: Multiple plausible answers mentioned, but only one is correct based on careful listening to modifiers.

JSON Structure:
{{
  "section_title": "...",
  "audio_script": "...(800-1000 words transcript with natural spoken markers: 'actually', 'mind you', 'Wait, that's not right...')...",
  "questions": [
    {{"order":1,"text":"...","question_type":"gap_fill","correct_answer":"...","options":[],"explanation":"..."}}
  ]
}}"""

_WRITING_TASKS = """Create IELTS Writing Task 1 and Task 2 for {variant} IELTS. Topic area: {topic}

IMPORTANT RULES:
1. If variant is 'Academic': Task 1 MUST be a visual data description (e.g., 'The graph shows...', 'The chart displays...').
2. If variant is 'General': Task 1 MUST be a letter (e.g., 'Write a letter to...', 'Dear Sir/Madam...').
3. Task 2 is always an essay.

Return JSON:
{{
  "task1": {{
    "title": "...", 
    "instruction": "...", 
    "data_description": "FOR ACADEMIC: Detailed description of the visual data (numbers, trends, axes) for DALL-E image generation. FOR GENERAL: Background context for the letter.",
    "model_answer": "A Band 9.0 model answer (at least 150 words). STRUCTURE: Introduction/Overview, Body Paragraphs, and Conclusion (if applicable)."
  }},
  "task2": {{
    "title": "...", 
    "question": "...", 
    "instruction": "...",
    "model_answer": "A Band 9.0 model answer (at least 250 words). STRUCTURE: Introduction (Hook/Thesis), Body Paragraphs (PEEL method), and Conclusion (Summary)."
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
):
    """
    Generator that yields (percentage, message, final_data).
    """
    yield 5, "Mavzu tahlil qilinmoqda..."
    topic = (topic or "").strip() or random.choice(
        _TOPICS_ACADEMIC if variant == 'academic' else _TOPICS_GENERAL
    )
    variant_label = 'Academic' if variant == 'academic' else 'General Training'

    sections = []
    if section_type == 'reading':
        for p, m, data in _gen_reading(topic, variant, model):
            if data: sections = data
            else: yield 5 + p * 0.9, m
    elif section_type == 'writing':
        yield 10, "Writing topshiriqlari yaratilmoqda..."
        sections = _gen_writing(topic, variant, model)
    elif section_type == 'listening':
        for p, m, data in _gen_listening(topic, model):
            if data: sections = data
            else: yield 5 + p * 0.9, m
    elif section_type == 'speaking':
        yield 10, "Speaking savollari yaratilmoqda..."
        sections = _gen_speaking(topic, model)
    elif section_type == 'full':
        # Simplified for brevity, usually calls others
        yield 10, "Listening bo'limi yaratilmoqda..."
        for p, m, data in _gen_listening(topic, model):
            if data: sections.extend(data)
            else: yield 10 + p * 0.2, m

        yield 30, "Reading bo'limi yaratilmoqda..."
        for p, m, data in _gen_reading(topic, variant, model):
            if data: sections.extend(data)
            else: yield 30 + p * 0.3, m

        yield 60, "Writing bo'limi yaratilmoqda..."
        sections.extend(_gen_writing(topic, variant, model))
        
        yield 80, "Speaking bo'limi yaratilmoqda..."
        sections.extend(_gen_speaking(topic, model))

    yield 95, "Test strukturasi yakunlanmoqda..."

    section_label = {
        'reading': 'Reading', 'writing': 'Writing',
        'listening': 'Listening', 'speaking': 'Speaking', 'full': 'Full Mock',
    }.get(section_type, section_type.title())

    final_data = {
        "title": f"IELTS {variant_label} — {section_label} ({topic[:40]})",
        "exam_type": "mock" if section_type == 'full' else section_type,
        "price": 0,
        "duration_minutes": {"full": 170, "reading": 60, "writing": 60, "listening": 30, "speaking": 14}.get(section_type, 60),
        "is_active": False,
        "description": f"[cambridge] AI tomonidan yaratilgan IELTS {variant_label} {section_label} testi. Mavzu: {topic}",
        "sections": sections,
        "ai_metadata": {"variant": variant, "topic": topic, "section_type": section_type, "model": model},
    }
    yield 100, "Tayyor!", final_data


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


def _generate_audio(text: str, voice: str = "alloy") -> bytes:
    """Generate audio bytes using OpenAI TTS."""
    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text[:4000] # OpenAI TTS limit per request
        )
        return response.content
    except Exception as e:
        print(f"TTS Error: {e}")
        return None


def _generate_image(prompt: str) -> str:
    """Generate image URL using OpenAI DALL-E 3."""
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=f"A professional, clean, academic IELTS writing task 1 chart. Style: minimal, data visualization, white background. Content: {prompt}",
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return response.data[0].url
    except Exception as e:
        print(f"Image Gen Error: {e}")
        return None


def _gen_reading(topic: str, variant: str, model: str):
    template = _READING_ACADEMIC if variant == 'academic' else _READING_GENERAL
    all_sections = []
    for i in range(1, 4):
        yield i * 33 - 15, f"Reading Passage {i} yaratilmoqda...", None
        data = _call_ai(template.format(topic=f"{topic} (Passage {i})"), model, max_tokens=3500)
        questions = _normalise_questions(data.get("questions", []))
        all_sections.append({
            "title": f"Reading Passage {i}: {data.get('passage_title', 'Untitled')}",
            "section_type": "reading",
            "order": i,
            "duration_minutes": 20,
            "content": f"<div style='line-height:1.8;font-size:14px'><h3>{data.get('passage_title','')}</h3><p>{data.get('passage','').replace(chr(10),'</p><p>')}</p></div>",
            "questions": questions,
            "extra_data": {"key_vocabulary": data.get("key_vocabulary", [])}
        })
    yield 100, "Reading tayyor", all_sections


def _gen_writing(topic: str, variant: str, model: str) -> list:
    chart = random.choice(_CHART_TYPES)
    essay = random.choice(_ESSAY_TYPES)
    data = _call_ai(_WRITING_TASKS.format(variant=variant.title(), topic=topic, chart_type=chart, essay_type=essay), model, max_tokens=1500)
    t1 = data.get("task1", {})
    t2 = data.get("task2", {})
    
    # Generate chart image for Academic Task 1
    image_url = None
    if variant == 'academic':
        image_url = _generate_image(t1.get("data_description", f"A {chart} about {topic}"))

    # Question text based on variant
    if variant == 'academic':
        q1_text = f"Describe the {chart} below. Write at least 150 words.\n\n{t1.get('data_description','')}"
    else:
        q1_text = f"Write the letter described on the left. Write at least 150 words.\n\n{t1.get('data_description','')}"

    return [
        {
            "title": t1.get("title", "Writing Task 1"),
            "section_type": "writing",
            "order": 1,
            "duration_minutes": 20,
            "content": f"<div style='line-height:1.8'><h3>Writing Task 1</h3><p>{t1.get('instruction','')}</p><div style='background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:16px;margin:12px 0;font-size:13px'>{t1.get('data_description','')}</div></div>",
            "image_url": image_url,
            "questions": [{
                "order": 1, 
                "text": q1_text, 
                "question_type": "writing_task", 
                "correct_answer": "", 
                "options": [], 
                "explanation": "Official Band 9.0 Sample Answer for Writing Task 1", 
                "model_answer": t1.get("model_answer", ""),
                "word_limit": 150
            }],
        },
        {
            "title": t2.get("title", "Writing Task 2"),
            "section_type": "writing",
            "order": 2,
            "duration_minutes": 40,
            "content": f"<div style='line-height:1.8'><h3>Writing Task 2</h3><p>{t2.get('question','')}</p><p><strong>{t2.get('instruction','Write at least 250 words.')}</strong></p></div>",
            "questions": [{
                "order": 1, 
                "text": t2.get("question", ""), 
                "question_type": "writing_task", 
                "correct_answer": "", 
                "options": [], 
                "explanation": "Official Band 9.0 Sample Answer for Writing Task 2", 
                "model_answer": t2.get("model_answer", ""),
                "word_limit": 250
            }],
        },
    ]


def _gen_listening(topic: str, model: str):
    all_sections = []
    for i in range(1, 5):
        yield i * 25 - 10, f"Listening Section {i} yaratilmoqda...", None
        listen_type = _LISTEN_TYPES[i-1] if i <= len(_LISTEN_TYPES) else random.choice(_LISTEN_TYPES)
        data = _call_ai(_LISTENING_SECTION.format(topic=topic, listen_type=listen_type[1]), model, max_tokens=2500)
        questions = _normalise_questions(data.get("questions", []))
        script = data.get("audio_script", "")
        
        # Generate real audio
        voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        audio_bytes = _generate_audio(script, voice=random.choice(voices))

        content = f"<div style='line-height:1.8'><h3>Listening Section {i}: {data.get('section_title', 'Untitled')}</h3><p><strong>Topshiriq:</strong> Quyidagi audioni eshiting va savollarga javob bering.</p></div>"
        
        all_sections.append({
            "title": f"Listening Section {i}: {data.get('section_title', 'Untitled')}",
            "section_type": "listening",
            "order": i,
            "duration_minutes": 8,
            "content": content,
            "questions": questions,
            "audio_bytes": audio_bytes, # Pass bytes to view for saving
            "extra_data": {"key_vocabulary": data.get("key_vocabulary", [])}
        })
    yield 100, "Listening tayyor", all_sections


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
        if not isinstance(q, dict): continue
        qtype = q.get("question_type", "gap_fill")
        
        # Fix empty MCQ options
        options = q.get("options", [])
        if qtype == "mcq" and (not options or len(options) < 2):
            # Emergency fallback if AI failed to provide options
            options = [{"key": "A", "text": "Option A"}, {"key": "B", "text": "Option B"}, {"key": "C", "text": "Option C"}, {"key": "D", "text": "Option D"}]
        
        # Fix empty question text
        qtext = str(q.get("text", "")).strip()
        if not qtext:
            qtext = f"Quyidagi bo'sh joyni to'ldiring (Savol {i})" if qtype == "gap_fill" else f"Savol matni mavjud emas ({i})"
        
        result.append({
            "order": q.get("order", i),
            "text": qtext,
            "question_type": qtype,
            "correct_answer": str(q.get("correct_answer", "")),
            "options": options,
            "explanation": str(q.get("explanation", "")),
            "word_limit": int(q.get("word_limit", 0)),
        })
    return result


def _fallback_writing_eval(text: str, task_num: int = 2) -> dict:
    """Word-count based fallback when AI is unavailable."""
    words = len(text.split()) if text else 0
    min_words = 150 if task_num == 1 else 250
    if words == 0: band = 0.0
    elif words < 50: band = 2.0
    elif words < 100: band = 3.5
    elif words < min_words // 2: band = 4.5
    elif words < min_words: band = 5.0
    elif words < min_words + 50: band = 5.5
    elif words < min_words + 100: band = 6.0
    else: band = 6.5
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
