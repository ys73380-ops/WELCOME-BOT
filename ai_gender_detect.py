import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

try:
    from groq import Groq
    _API_KEY = os.getenv("GROQ_API_KEY", "")
    if _API_KEY:
        _CLIENT = Groq(api_key=_API_KEY)
        _AI_AVAILABLE = True
    else:
        _CLIENT = None
        _AI_AVAILABLE = False
except ImportError:
    _CLIENT = None
    _AI_AVAILABLE = False

MODEL = "llama-3.1-8b-instant"

SYSTEM_PROMPT = """You are an expert Indian name gender classifier.
Given a person's name, respond with EXACTLY one word only:
  male   — clearly masculine name
  female — clearly feminine name
  neutral — unisex, ambiguous, or gaming tag"""

@lru_cache(maxsize=4096)
def _cached_detect(name_key: str) -> str:
    if not _AI_AVAILABLE or not _CLIENT:
        return _fallback_detect(name_key)
    try:
        response = _CLIENT.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": name_key},
            ],
            max_tokens=5,
            temperature=0.0,
        )
        result = response.choices[0].message.content.strip().lower()
        for word in result.split():
            if word in ("male", "female", "neutral"):
                return word
        return _fallback_detect(name_key)
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return _fallback_detect(name_key)

def detect_gender_ai(name: str) -> str:
    if not name or not name.strip():
        return "neutral"
    key = name.strip()
    return _cached_detect(key)

_FEMALE_SURNAMES = {'kaur', 'devi', 'bai', 'ben', 'bhen'}
_MALE_SURNAMES   = {'singh', 'kumar', 'sharma', 'pandey', 'tiwari', 'mishra', 'yadav', 'verma'}
_FEMALE_NAMES = {
    'priya','neha','pooja','anjali','kavita','sunita','rekha','meena',
    'divya','ritu','sona','komal','deepika','nisha','asha','shreya',
    'khushi','ishita','tanvi','jyoti','radha','seema','ananya','kajal',
    'fatima','ayesha','zainab','sana','noor','zara','rubina','reshma',
}
_MALE_NAMES = {
    'rahul','raj','amit','rohan','arjun','vikram','deepak','sanjay',
    'vikas','mohit','sunil','rakesh','ravi','ankit','arun','harish',
    'dinesh','nitin','yogesh','gaurav','rohit','manish','ajay','akash',
    'varun','harsh','himanshu','piyush','parth','mohammad','imran',
}

def _fallback_detect(name: str) -> str:
    words = [w.lower() for w in name.split() if w.isalpha()]
    for w in words:
        if w in _FEMALE_SURNAMES: return "female"
    for w in words:
        if w in _MALE_SURNAMES: return "male"
    for w in words:
        if w in _FEMALE_NAMES: return "female"
        if w in _MALE_NAMES: return "male"
    return "neutral"
