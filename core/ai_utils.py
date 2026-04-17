import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """Siz AbExam platformasining AI yordamchisisiz. Foydalanuvchilarga IELTS imtihoniga tayyorlanishda, 
lug'at boyligini oshirishda va platformadan foydalanishda yordam berasiz. 
Javoblarni har doim o'zbek tilida bering. Qisqa va aniq javob bering."""


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
