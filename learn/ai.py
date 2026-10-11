"""AI helpers for the English course: conversation tutor and short-writing feedback."""
import json
import logging

from core.ai_utils import _HOT_PATH_TIMEOUT, client

logger = logging.getLogger(__name__)

SCENARIOS = {
    'free': {
        'title_uz': "Erkin suhbat", 'icon': 'message-circle',
        'desc_uz': "Istalgan mavzuda gaplashing — AI xatolaringizni yumshoq tuzatadi.",
        'role': "a friendly English conversation partner. Talk about anything the learner brings up.",
        'opener': "Hi! I'm your English practice partner. How are you today?",
    },
    'cafe': {
        'title_uz': "Kafeda buyurtma", 'icon': 'coffee',
        'desc_uz': "Ofitsiant bilan gaplashib, ovqat va ichimlik buyurtma qiling.",
        'role': "a waiter at a busy London café. Take the learner's order, suggest items, tell prices, and ask how they will pay.",
        'opener': "Good morning! Welcome to Riverside Café. What can I get for you today?",
    },
    'travel': {
        'title_uz': "Aeroport va mehmonxona", 'icon': 'plane',
        'desc_uz': "Ro'yxatdan o'tish, mehmonxona bron qilish, yo'l so'rash.",
        'role': "a hotel receptionist in Manchester. Help the learner check in, answer questions about the room, breakfast and directions.",
        'opener': "Good evening and welcome to the Northern Hotel. Do you have a reservation with us?",
    },
    'interview': {
        'title_uz': "Ish suhbati", 'icon': 'briefcase',
        'desc_uz': "Ish beruvchi savollariga javob berib, intervyuga tayyorlaning.",
        'role': "a polite HR manager interviewing the learner for a job they want. Ask one typical interview question at a time.",
        'opener': "Thank you for coming in today. To start, could you tell me a little about yourself?",
    },
    'ielts1': {
        'title_uz': "IELTS Speaking Part 1", 'icon': 'mic',
        'desc_uz': "Haqiqiy imtihondagidek: uy, ish/o'qish, hobbilar haqida savollar.",
        'role': ("an IELTS Speaking examiner running Part 1. Ask short questions about familiar topics "
                 "(home, work or study, hometown, hobbies), one at a time, and encourage extended answers (2-3 sentences)."),
        'opener': "Good afternoon. My name is Sarah. Can you tell me your full name, please? And what do you do — do you work or are you a student?",
    },
    'ielts3': {
        'title_uz': "IELTS Speaking Part 3", 'icon': 'brain',
        'desc_uz': "Abstrakt mavzularda fikr bildirish va asoslash mashqi.",
        'role': ("an IELTS Speaking examiner running Part 3. Ask one abstract discussion question at a time "
                 "(society, technology, education, environment) and push the learner to justify and compare."),
        'opener': "Let's talk about technology and education. Do you think online learning will ever replace traditional classrooms?",
    },
}

TUTOR_PROMPT = """You are {role}
The learner is an Uzbek speaker learning English at CEFR level {level}.

Rules:
- Stay in role. Reply in natural, simple English suited to level {level}: 1-3 short sentences, then ONE question that keeps the conversation going.
- Never switch to Uzbek in "reply".
- Check the learner's LAST message for grammar, word-choice or spelling mistakes that matter. Ignore missing capitals/punctuation and tiny typos.
- If there is a real mistake, give the corrected sentence and a very short explanation in Uzbek (1 sentence).
- Optionally suggest ONE useful, more natural phrase they could use (with Uzbek meaning).

Return ONLY JSON:
{{"reply": "<your in-role reply>",
  "correction": null or {{"corrected": "<learner's sentence, corrected>", "explain_uz": "<short explanation in Uzbek>"}},
  "tip": null or {{"phrase": "<useful English phrase>", "uz": "<Uzbek meaning>"}}}}"""

WRITE_PROMPT = """You are a kind, precise English teacher for Uzbek learners at CEFR level {level}.
Task given to the learner: "{task}"
Check the learner's short text. Focus on errors that matter at this level; do not rewrite their ideas.

Return ONLY JSON:
{{"score": <int 0-100: how well the text completes the task with accurate English for level {level}>,
  "corrected": "<the learner's text with minimal corrections>",
  "mistakes": [{{"wrong": "<fragment>", "right": "<fixed fragment>", "why_uz": "<short reason in Uzbek>"}}],
  "praise_uz": "<one sentence in Uzbek about what was good>",
  "next_uz": "<one concrete tip in Uzbek for the next step>"}}
At most 5 mistakes. If the text is empty or not English, score 0."""


def _clean_history(history):
    out = []
    for m in (history or [])[-12:]:
        if not isinstance(m, dict):
            continue
        role = m.get('role')
        content = str(m.get('content', ''))[:1000]
        if role in ('user', 'assistant') and content:
            out.append({'role': role, 'content': content})
    return out


def tutor_reply(scenario_key, level, message, history):
    scenario = SCENARIOS.get(scenario_key, SCENARIOS['free'])
    messages = [{'role': 'system', 'content': TUTOR_PROMPT.format(role=scenario['role'], level=level or 'B1')}]
    messages += _clean_history(history)
    messages.append({'role': 'user', 'content': message[:1000]})
    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini', messages=messages, temperature=0.7, max_tokens=400,
            response_format={'type': 'json_object'}, timeout=_HOT_PATH_TIMEOUT,
        )
        data = json.loads(response.choices[0].message.content)
    except Exception:
        logger.exception('tutor_reply failed')
        return None
    correction = data.get('correction') if isinstance(data.get('correction'), dict) else None
    tip = data.get('tip') if isinstance(data.get('tip'), dict) else None
    return {
        'reply': str(data.get('reply', '')).strip(),
        'correction': correction if correction and correction.get('corrected') else None,
        'tip': tip if tip and tip.get('phrase') else None,
    }


def check_writing(task, text, level):
    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': WRITE_PROMPT.format(level=level, task=task[:500])},
                {'role': 'user', 'content': text[:2000]},
            ],
            temperature=0.3, max_tokens=700,
            response_format={'type': 'json_object'}, timeout=_HOT_PATH_TIMEOUT,
        )
        data = json.loads(response.choices[0].message.content)
    except Exception:
        logger.exception('check_writing failed')
        return None
    try:
        score = max(0, min(100, int(data.get('score', 0))))
    except (TypeError, ValueError):
        score = 0
    mistakes = [m for m in data.get('mistakes', []) if isinstance(m, dict)][:5]
    return {
        'score': score,
        'corrected': str(data.get('corrected', '')),
        'mistakes': mistakes,
        'praise_uz': str(data.get('praise_uz', '')),
        'next_uz': str(data.get('next_uz', '')),
    }
