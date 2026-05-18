"""
╔══════════════════════════════════════════════════════════════════╗
║              🌹 PREMIUM WELCOME BOT                 
║   Multiple Videos · Gender-Split · Template+Video Combo         
║             ║
╚══════════════════════════════════════════════════════════════════╝

FEATURES:
✅ Multiple videos set kar sakte ho (male/female alag alag)
✅ Template message + video combo
✅ Male ko uska video+msg, Female ko uska video+msg
✅ Random video pick from list
✅ Inline buttons support
"""

import asyncio
import aiohttp
import logging
import json
import os
import re
import random
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaVideo, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ChatMemberHandler, ContextTypes, MessageHandler, filters
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError

# ============================================================
#  ENV
# ============================================================
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
REDIS_URL    = os.environ.get("REDIS_URL", "")
SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "bot_settings.json")

logging.basicConfig(
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# ============================================================
#  MARKDOWN ESCAPE (MarkdownV2)
# ============================================================
def esc(text: str) -> str:
    if not text:
        return ""
    # Escape all MarkdownV2 special chars
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', str(text))


# ============================================================
#  STORAGE  (Redis primary, JSON fallback)
# ============================================================
_redis_conn = None
_json_lock  = asyncio.Lock()

async def _get_redis():
    global _redis_conn
    if _redis_conn is None and REDIS_URL:
        try:
            import redis.asyncio as aioredis
            _redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
            await _redis_conn.ping()
            logger.info("✅ Redis connected")
        except Exception as e:
            logger.error(f"Redis failed: {e}")
            _redis_conn = False
    return _redis_conn if _redis_conn else None

def _load_json() -> dict:
    p = Path(SETTINGS_FILE)
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            pass
    return {}

async def _save_json(data: dict):
    async with _json_lock:
        p   = Path(SETTINGS_FILE)
        tmp = p.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
            tmp.replace(p)
        except OSError as e:
            logger.error(f"JSON save error: {e}")

async def get_settings(gid: int) -> dict:
    key = f"wb:{gid}"
    r   = await _get_redis()
    if r:
        try:
            raw = await r.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return _load_json().get(str(gid), {})

async def save_settings(gid: int, settings: dict):
    key = f"wb:{gid}"
    js  = json.dumps(settings, ensure_ascii=False)
    r   = await _get_redis()
    if r:
        try:
            await r.set(key, js)
        except Exception:
            pass
    all_s         = _load_json()
    all_s[str(gid)] = settings
    await _save_json(all_s)
    logger.info(f"[{gid}] Settings saved ✅")

async def set_key(gid: int, key: str, value):
    s       = await get_settings(gid)
    s[key]  = value
    await save_settings(gid, s)

async def delete_all(gid: int):
    r = await _get_redis()
    if r:
        try:
            await r.delete(f"wb:{gid}")
        except Exception:
            pass
    all_s = _load_json()
    all_s.pop(str(gid), None)
    await _save_json(all_s)


# ============================================================
#  GENDER CACHE
# ============================================================
_gcache: Dict[int, dict] = {}

async def cache_gender(uid: int, gender: str, conf: float):
    _gcache[uid] = {"gender": gender, "confidence": conf}
    r = await _get_redis()
    if r:
        try:
            await r.setex(f"gender:{uid}", 86400 * 30,
                          json.dumps({"gender": gender, "confidence": conf}))
        except Exception:
            pass

async def get_cached_gender(uid: int) -> Optional[Tuple[str, float]]:
    if uid in _gcache:
        return (_gcache[uid]["gender"], _gcache[uid]["confidence"])
    r = await _get_redis()
    if r:
        try:
            raw = await r.get(f"gender:{uid}")
            if raw:
                d = json.loads(raw)
                return (d["gender"], d["confidence"])
        except Exception:
            pass
    return None


# ============================================================
#  GENDER DETECTION  (Groq AI → Name DB → Ask)
# ============================================================

async def detect_via_groq(first: str, last: str = "", username: str = "") -> Optional[Tuple[str, float]]:
    """Groq llama3-70b se gender detect karo — perfect accuracy."""
    if not GROQ_API_KEY:
        return None

    # Strict prompt — sirf male/female/unknown return kare
    prompt = f"""You are a gender detection system.
Your ONLY job: given a person's name, return exactly one word — either "male" or "female" or "unknown".

Rules:
- If you are 80%+ confident → return "male" or "female"
- If you are not sure → return "unknown"
- Return ONLY the single word. No punctuation, no explanation.

First name: {first}
Last name: {last}
Username (hint): {username}

Answer:"""

    try:
        async with aiohttp.ClientSession() as s:
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json",
            }
            payload = {
                "model":       "llama3-70b-8192",
                "messages":    [{"role": "user", "content": prompt}],
                "temperature": 0.0,   # deterministic
                "max_tokens":  5,
            }
            async with s.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status == 200:
                    data   = await resp.json()
                    answer = data["choices"][0]["message"]["content"].strip().lower()
                    # Clean any extra punctuation just in case
                    answer = re.sub(r'[^a-z]', '', answer)
                    if answer in ("male", "female"):
                        logger.info(f"🤖 Groq → {answer} for '{first} {last}'")
                        return (answer, 0.95)
                    elif answer == "unknown":
                        return None
                else:
                    body = await resp.text()
                    logger.error(f"Groq HTTP {resp.status}: {body[:200]}")
    except asyncio.TimeoutError:
        logger.warning("Groq timeout")
    except Exception as e:
        logger.error(f"Groq error: {e}")
    return None

# Comprehensive name databases
MALE_NAMES = {
    # Indian
    "aarav","aditya","akash","amit","ankit","arjun","aryan","ayush","deepak","dev",
    "dhruv","gaurav","harsh","kartik","karan","kunal","manish","mohit","nikhil",
    "rahul","raj","rajesh","ravi","rohit","rohan","sachin","sahil","shubham","sumit",
    "suraj","varun","vikas","vivek","yash","siddharth","vishal","abhishek","ajay",
    "akshay","amitabh","anurag","ashish","ashok","bhavesh","chirag","dinesh","girish",
    "gopal","harish","hemant","hitesh","jagdish","jayesh","jignesh","kapil","krishna",
    "lalit","mahesh","manoj","mukesh","nagesh","neeraj","niraj","pankaj","paresh",
    "prakash","prasad","prashant","rajiv","ramesh","rupesh","sanjeev","santosh",
    "satish","shailesh","sharad","shyam","suresh","tushar","umesh","vinod","viral",
    # English/Western
    "james","john","robert","michael","william","david","richard","thomas","charles",
    "christopher","daniel","matthew","anthony","mark","liam","noah","oliver","elijah",
    "lucas","mason","logan","ethan","aiden","ryan","jacob","tyler","jack","jayden",
    "leo","henry","owen","sebastian","finn","caleb","joshua","nathan","adam","alex",
    # Arabic/Muslim
    "ali","muhammad","omar","hassan","ibrahim","ahmed","khalid","tariq","yusuf",
    "bilal","hamza","usman","zaid","faisal","nawaz","imran","salman","shahid",
    # Other
    "viktor","ivan","nikolai","boris","dmitri","andrei","sergei","alexei",
}

FEMALE_NAMES = {
    # Indian
    "aisha","ananya","anjali","ankita","anushka","arpita","deepika","divya","garima",
    "ishita","kajal","kavya","khushi","komal","kritika","mansi","megha","meera",
    "muskan","namrata","neha","nikita","nisha","pallavi","pooja","priya","riya",
    "sakshi","sandhya","shruti","simran","sneha","sonam","tanvi","tanya","vidya",
    "zara","diya","prachi","swati","madhuri","sunita","savita","babita","shilpa",
    "preeti","aarti","sonia","rekha","seema","reena","sheetal","kavita","lalita",
    "archana","usha","geeta","lata","manju","pushpa","radha","sita","durga",
    "kiran","anita","nidhi","shweta","monika","poonam","rachna","sudha","uma",
    "vani","yamini","bharti","chanda","kamla","leela","nandita","padma","rani",
    # English/Western
    "sarah","emily","emma","olivia","ava","sophia","isabella","mia","amelia",
    "harper","evelyn","abigail","elizabeth","sofia","ella","grace","chloe","lily",
    "hannah","natalie","samantha","jessica","ashley","brianna","taylor","madison",
    "victoria","scarlett","aurora","hazel","violet","ellie","stella","lucy",
    # Arabic/Muslim
    "fatima","maryam","amina","hana","sara","leila","yasmin","noor","aisha",
    "khadija","zainab","ruqayyah","sumaiya","asma","hafsa","safiya","umm",
    # Other
    "maria","elena","anna","irina","natasha","olga","tatyana","yulia",
}

async def detect_via_namedb(full_name: str) -> Optional[Tuple[str, float]]:
    """Name database se detect karo."""
    if not full_name:
        return None
    # Check each word in the name
    for part in full_name.lower().split():
        clean = re.sub(r'[^a-z]', '', part)
        if len(clean) < 2:
            continue
        if clean in MALE_NAMES:
            return ("male", 0.82)
        if clean in FEMALE_NAMES:
            return ("female", 0.82)
    return None

async def detect_gender(uid: int, first: str, last: str = "", username: str = "") -> Tuple[str, float, str]:
    """
    Master gender detection pipeline:
    Cache → Groq AI → Name DB → Ask User
    Returns: (gender, confidence, method)
    """
    # 1. Cache check
    cached = await get_cached_gender(uid)
    if cached:
        logger.info(f"💾 Cache hit: {cached[0]} for uid={uid}")
        return (cached[0], cached[1], "cache")

    # 2. Groq AI (best accuracy)
    result = await detect_via_groq(first, last, username)
    if result:
        await cache_gender(uid, result[0], result[1])
        return (result[0], result[1], "groq_ai")

    # 3. Name database fallback
    full = f"{first} {last}".strip()
    result = await detect_via_namedb(full)
    if result:
        await cache_gender(uid, result[0], result[1])
        return (result[0], result[1], "name_db")

    # 4. Unknown → bot will ask user
    return ("unknown", 0.0, "none")


# ============================================================
#  TEMPLATES  (gender-split)
# ============================================================
TEMPLATES = {
    "default": {
        "male": (
            "🌟 *Welcome to {group}, {name}\\!*\n\n"
            "┌──────────────────────┐\n"
            "│ 👤 {name}\n"
            "│ 🆔 {username}\n"
            "│ 📅 {date} │ ⏰ {time}\n"
            "│ 👥 Member \\#{member_count}\n"
            "└──────────────────────┘\n\n"
            "💪 *Bro, welcome aboard\\!*\n"
            "Rules padh lo aur enjoy karo 🔥"
        ),
        "female": (
            "🌸 *Welcome to {group}, {name}\\!*\n\n"
            "┌──────────────────────┐\n"
            "│ 👤 {name}\n"
            "│ 🆔 {username}\n"
            "│ 📅 {date} │ ⏰ {time}\n"
            "│ 👥 Member \\#{member_count}\n"
            "└──────────────────────┘\n\n"
            "💐 *Aapka swagat hai\\!*\n"
            "Rules padh lo aur enjoy karo ✨"
        ),
    },
    "elegant": {
        "male": (
            "✧══════════════════════════✧\n"
            "        💎 *WELCOME BRO* 💎\n"
            "✧══════════════════════════✧\n\n"
            "👦 *{name}* has joined\\!\n"
            "    {username}\n\n"
            "『 {group} 』\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 Members: {member_count}\n"
            "🤖 Detected: {detect_method}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🚀 *Enjoy your stay, bhai\\!*"
        ),
        "female": (
            "✧══════════════════════════✧\n"
            "        👑 *WELCOME* 👑\n"
            "✧══════════════════════════✧\n\n"
            "👧 *{name}* has joined\\!\n"
            "    {username}\n\n"
            "『 {group} 』\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 Members: {member_count}\n"
            "🤖 Detected: {detect_method}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "💐 *Enjoy your stay\\!*"
        ),
    },
    "premium": {
        "male": (
            "🏆 ━━━━━━━━━━━━━━━━━━━━━━ 🏆\n"
            "      ✨ *PREMIUM WELCOME* ✨\n"
            "🏆 ━━━━━━━━━━━━━━━━━━━━━━ 🏆\n\n"
            "👑 *{name}* 👑\n"
            "┣━ 📝 {username}\n"
            "┣━ 🏠 {group}\n"
            "┣━ 👥 {member_count} members\n"
            "┗━ ⭐ Status: 👦 Male • Verified\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔥 *Bhai, we're excited to have you\\!*"
        ),
        "female": (
            "🏆 ━━━━━━━━━━━━━━━━━━━━━━ 🏆\n"
            "      ✨ *PREMIUM WELCOME* ✨\n"
            "🏆 ━━━━━━━━━━━━━━━━━━━━━━ 🏆\n\n"
            "👸 *{name}* 👸\n"
            "┣━ 📝 {username}\n"
            "┣━ 🏠 {group}\n"
            "┣━ 👥 {member_count} members\n"
            "┗━ ⭐ Status: 👧 Female • Verified\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌺 *We're excited to have you\\!*"
        ),
    },
    "minimal": {
        "male": (
            "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            "  👦 *{name}* joined\\!\n"
            "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
            "{username} │ {group} │ {member_count} members"
        ),
        "female": (
            "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            "  👧 *{name}* joined\\!\n"
            "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
            "{username} │ {group} │ {member_count} members"
        ),
    },
}

METHOD_BADGE = {
    "groq_ai":  "🤖 Groq AI",
    "name_db":  "📚 Name DB",
    "cache":    "💾 Cached",
    "user_selected": "✅ Self Selected",
}

async def render(template: str, user, group_name: str, gid: int,
                 member_count: int, gender: str, method: str) -> str:
    now = datetime.now()
    repl = {
        "{name}":          esc(user.full_name or user.first_name or "Member"),
        "{first_name}":    esc(user.first_name or ""),
        "{last_name}":     esc(user.last_name  or ""),
        "{username}":      esc(f"@{user.username}" if user.username else (user.first_name or "member")),
        "{mention}":       f"[{esc(user.first_name or 'User')}](tg://user?id={user.id})",
        "{group}":         esc(group_name),
        "{group_id}":      str(gid),
        "{member_count}":  str(member_count),
        "{date}":          esc(now.strftime("%d/%m/%Y")),
        "{time}":          esc(now.strftime("%H:%M")),
        "{gender_emoji}":  "👦" if gender == "male" else "👧",
        "{detect_method}": esc(METHOD_BADGE.get(method, method)),
    }
    result = template
    for k, v in repl.items():
        result = result.replace(k, v)
    return result


# ============================================================
#  UTILS
# ============================================================
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE,
                   gid: int = None) -> bool:
    uid = update.effective_user.id
    cid = gid or update.effective_chat.id
    try:
        m = await context.bot.get_chat_member(cid, uid)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except TelegramError:
        return False

async def safe_send(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str,
                    reply_markup=None, pm=ParseMode.MARKDOWN_V2):
    try:
        return await context.bot.send_message(
            chat_id=chat_id, text=text,
            parse_mode=pm, reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except TelegramError as e:
        logger.warning(f"MDv2 failed ({e}), fallback plain")
        clean = re.sub(r'[_*\[\]()~`>#+\-=|{}.!\\]', '', text)
        try:
            return await context.bot.send_message(
                chat_id=chat_id, text=clean, reply_markup=reply_markup
            )
        except TelegramError as e2:
            logger.error(f"Plain send failed too: {e2}")
    return None

def get_gid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        return (context.user_data.get("active_group_id"),
                context.user_data.get("active_group_name", "Group"))
    return (chat.id, chat.title or "Group")

def build_markup(buttons_raw) -> Optional[InlineKeyboardMarkup]:
    if not buttons_raw:
        return None
    try:
        data = json.loads(buttons_raw) if isinstance(buttons_raw, str) else buttons_raw
        kb   = []
        for row in data:
            kr = []
            for btn in row:
                if btn[1] == "url":
                    kr.append(InlineKeyboardButton(btn[0], url=btn[2]))
                elif btn[1] == "callback":
                    kr.append(InlineKeyboardButton(btn[0], callback_data=btn[2]))
            if kr:
                kb.append(kr)
        return InlineKeyboardMarkup(kb) if kb else None
    except Exception:
        return None


# ============================================================
#  CORE: SEND WELCOME
# ============================================================
async def send_welcome(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                       user, gender: str, group_name: str, method: str):
    """
    Gender ke hisaab se:
    - Custom msg (male_msg / female_msg) ya template
    - Multiple videos list se random pick
    - Buttons attach
    """
    s = await get_settings(chat_id)

    # ── 1. Message text ──────────────────────────────────────
    if gender == "male":
        custom_msg = s.get("male_msg", "")
    else:
        custom_msg = s.get("female_msg", "")

    if not custom_msg:
        # fallback: shared custom or template
        custom_msg = s.get("custom_msg", "")

    if not custom_msg:
        tpl_name = s.get("template", "default")
        tpl      = TEMPLATES.get(tpl_name, TEMPLATES["default"])
        custom_msg = tpl.get(gender, tpl["male"])   # male fallback if needed

    # ── 2. Member count ───────────────────────────────────────
    try:
        member_count = await context.bot.get_chat_member_count(chat_id)
    except Exception:
        member_count = 0

    final_text = await render(custom_msg, user, group_name, chat_id,
                               member_count, gender, method)

    # ── 3. Buttons ────────────────────────────────────────────
    markup = build_markup(s.get("buttons"))

    # ── 4. Videos / photos ───────────────────────────────────
    # Per-gender video list  →  random pick
    if gender == "male":
        media_list  = s.get("male_videos",  [])   # list of {id, type}
        media_list += s.get("male_photos",  [])
    else:
        media_list  = s.get("female_videos", [])
        media_list += s.get("female_photos", [])

    # Fallback: shared media
    if not media_list:
        media_list = s.get("shared_media", [])

    chosen = random.choice(media_list) if media_list else None

    # ── 5. Send ───────────────────────────────────────────────
    sent = False
    if chosen:
        mid   = chosen["id"]
        mtype = chosen["type"]
        try:
            if mtype == "video":
                await context.bot.send_video(
                    chat_id=chat_id, video=mid,
                    caption=final_text, parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=markup
                )
                sent = True
            elif mtype == "photo":
                await context.bot.send_photo(
                    chat_id=chat_id, photo=mid,
                    caption=final_text, parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=markup
                )
                sent = True
            elif mtype == "gif":
                await context.bot.send_animation(
                    chat_id=chat_id, animation=mid,
                    caption=final_text, parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=markup
                )
                sent = True
        except TelegramError as e:
            logger.error(f"Media send failed: {e}")

    if not sent:
        await safe_send(context, chat_id, final_text, reply_markup=markup)

    logger.info(f"✅ Welcome sent → {user.full_name} ({gender}) in {chat_id}")


# ============================================================
#  COMMANDS
# ============================================================

# ── /start ─────────────────────────────────────────────────
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u  = update.effective_user
    n  = esc(u.first_name or "Dost")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Templates",   callback_data="show_templates")],
        [InlineKeyboardButton("📖 Guide",        callback_data="help_guide"),
         InlineKeyboardButton("⚙️ Setup",        callback_data="setup_guide")],
    ])
    await safe_send(context, update.effective_chat.id,
        f"┌──────────────────────┐\n"
        f"│   🌹 *WELCOME BOT*   │\n"
        f"└──────────────────────┘\n\n"
        f"✨ *Namaste, {n}\\!* ✨\n\n"
        f"*Features:*\n"
        f"┣━ 🎨 4 Premium Templates\n"
        f"┣━ 📹 Multiple Videos per Gender\n"
        f"┣━ 🔘 Inline Buttons\n"
        f"*Commands:*\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃ /connect \\- Group connect karo\n"
        f"┃ /template \\- Template chuno\n"
        f"┃ /add \\- Male video+MSG add\n"
        f"┃ /add \\- Female video add\n"
        f"┃ /listmedia \\- Saved media dekho\n"
        f"┃ /clearmedia \\- Media clear karo\n"
        f"┃ /setmore \\- or video+msg set karo\n"
        f"┃ /preview \\- Test karo\n"
        f"┃ /settings \\- Current settings\n"
        f"┃ /delete \\- Sab delete karo\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"💡 *Start with:* /connect → /template → /addvideo\\_male",
        reply_markup=kb,
    )


# ── /connect ───────────────────────────────────────────────
async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn  = esc(context.user_data.get("active_group_name", "—"))
        if gid:
            txt = f"✅ *Connected:* {gn}\n📁 ID: `{gid}`"
        else:
            txt = "⚠️ Koi group connect nahi hai\\.\nPehle group mein /connect chalaao\\."
        return await safe_send(context, chat.id, f"🔗 *Connection Status*\n\n{txt}")

    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins use kar sakte hain!")

    context.user_data["active_group_id"]   = chat.id
    context.user_data["active_group_name"] = chat.title
    me = await context.bot.get_me()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🤖 DM mein Open karo", url=f"https://t.me/{me.username}")]])
    await safe_send(context, chat.id,
        f"✅ *{esc(chat.title)}* connected\\!\n📁 ID: `{chat.id}`\n\nDM mein configure karo 👆",
        reply_markup=kb,
    )


# ── /template ──────────────────────────────────────────────
async def template_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, _ = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle group mein /connect chalaao\\!")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌟 Default", callback_data=f"tpl_default_{gid}"),
         InlineKeyboardButton("💎 Elegant", callback_data=f"tpl_elegant_{gid}")],
        [InlineKeyboardButton("🏆 Premium", callback_data=f"tpl_premium_{gid}"),
         InlineKeyboardButton("🎯 Minimal", callback_data=f"tpl_minimal_{gid}")],
        [InlineKeyboardButton("❌ Cancel",   callback_data="cancel")],
    ])
    await safe_send(context, chat.id,
        "┌──────────────────────┐\n"
        "│   📚 *TEMPLATES*     │\n"
        "└──────────────────────┘\n\n"
        "*Template chuno:*\n\n"
        "🌟 *Default* \\- Clean \\& Professional\n"
        "💎 *Elegant* \\- Stylish Design\n"
        "🏆 *Premium* \\- Bold \\& Beautiful\n"
        "🎯 *Minimal* \\- Simple \\& Clean\n\n"
        "Select karo — preview /preview se dekho\\!",
        reply_markup=kb,
    )


# ── /setwelcome (shared) ────────────────────────────────────
async def setwelcome_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, gn = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    text = " ".join(context.args) if context.args else ""
    if not text and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or
                update.message.reply_to_message.caption or "")

    if not text:
        return await safe_send(context, chat.id,
            f"📝 *Shared Welcome Message*\n\n"
            f"Group: *{esc(gn)}*\n\n"
            f"*Usage:* `/setwelcome Apna msg yahan`\n\n"
            f"*Variables:*\n"
            f"`{{name}}` \\- Full name\n"
            f"`{{username}}` \\- Username\n"
            f"`{{group}}` \\- Group name\n"
            f"`{{member\\_count}}` \\- Members count\n"
            f"`{{date}}` \\- Date\n"
            f"`{{time}}` \\- Time\n"
            f"`{{gender\\_emoji}}` \\- 👦/👧\n"
            f"`{{detect\\_method}}` \\- AI method\n\n"
            f"*Note:* Male/female alag karna ho to\n"
            f"/setwelcome\\_male aur /setwelcome\\_female use karo\\!"
        )

    await set_key(gid, "custom_msg", text)
    await safe_send(context, chat.id,
        f"✅ *Shared welcome msg saved\\!*\n\n"
        f"Preview:\n_{esc(text[:300])}_"
    )


# ── /setwelcome_male ───────────────────────────────────────
async def setwelcome_male_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, gn = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    text = " ".join(context.args) if context.args else ""
    if not text and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or
                update.message.reply_to_message.caption or "")

    if not text:
        return await safe_send(context, chat.id,
            "📝 *Male Welcome Message*\n\n"
            "*Usage:* `/setwelcome_male Bhai welcome\\! 🔥`\n\n"
            "Yeh message sirf male members ko jayega\\!"
        )

    await set_key(gid, "male_msg", text)
    await safe_send(context, chat.id,
        f"✅ *Male welcome msg saved\\!* 👦\n\n_{esc(text[:300])}_"
    )


# ── /setwelcome_female ─────────────────────────────────────
async def setwelcome_female_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, gn = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    text = " ".join(context.args) if context.args else ""
    if not text and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or
                update.message.reply_to_message.caption or "")

    if not text:
        return await safe_send(context, chat.id,
            "📝 *Female Welcome Message*\n\n"
            "*Usage:* `/setwelcome_female Aapka swagat hai\\! 🌸`\n\n"
            "Yeh message sirf female members ko jayega\\!"
        )

    await set_key(gid, "female_msg", text)
    await safe_send(context, chat.id,
        f"✅ *Female welcome msg saved\\!* 👧\n\n_{esc(text[:300])}_"
    )


# ── /addvideo_male  (multiple videos support) ──────────────
async def addvideo_male_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, _ = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    reply = update.message.reply_to_message
    if not reply:
        return await safe_send(context, chat.id,
            "📹 *Male Video Add karo*\n\n"
            "Kisi video/photo/GIF ko reply karo `/addvideo_male` se\\.\n\n"
            "Multiple videos add kar sakte ho — "
            "welcome pe random ek play hoga\\! 🎲"
        )

    mid, mtype = None, None
    if reply.video:
        mid, mtype = reply.video.file_id, "video"
    elif reply.photo:
        mid, mtype = reply.photo[-1].file_id, "photo"
    elif reply.animation:
        mid, mtype = reply.animation.file_id, "gif"

    if not mid:
        return await safe_send(context, chat.id, "❌ Video, photo ya GIF reply karo\\!")

    s    = await get_settings(gid)
    lst  = s.get("male_videos", []) if mtype == "video" else s.get("male_photos", [])
    key  = "male_videos" if mtype == "video" else "male_photos"
    lst.append({"id": mid, "type": mtype})
    await set_key(gid, key, lst)

    total = len(s.get("male_videos", [])) + len(s.get("male_photos", [])) + 1
    await safe_send(context, chat.id,
        f"✅ *Male {mtype} saved\\!* 👦\n\n"
        f"Total male media: *{total}* items\n"
        f"Welcome pe random ek play hoga 🎲"
    )


# ── /addvideo_female  (multiple videos support) ────────────
async def addvideo_female_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, _ = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    reply = update.message.reply_to_message
    if not reply:
        return await safe_send(context, chat.id,
            "📹 *Female Video Add karo*\n\n"
            "Kisi video/photo/GIF ko reply karo `/addvideo_female` se\\.\n\n"
            "Multiple videos add kar sakte ho — "
            "welcome pe random ek play hoga\\! 🎲"
        )

    mid, mtype = None, None
    if reply.video:
        mid, mtype = reply.video.file_id, "video"
    elif reply.photo:
        mid, mtype = reply.photo[-1].file_id, "photo"
    elif reply.animation:
        mid, mtype = reply.animation.file_id, "gif"

    if not mid:
        return await safe_send(context, chat.id, "❌ Video, photo ya GIF reply karo\\!")

    s    = await get_settings(gid)
    key  = "female_videos" if mtype == "video" else "female_photos"
    lst  = s.get(key, [])
    lst.append({"id": mid, "type": mtype})
    await set_key(gid, key, lst)

    total = len(s.get("female_videos", [])) + len(s.get("female_photos", [])) + 1
    await safe_send(context, chat.id,
        f"✅ *Female {mtype} saved\\!* 👧\n\n"
        f"Total female media: *{total}* items\n"
        f"Welcome pe random ek play hoga 🎲"
    )


# ── /addvideo (shared fallback) ────────────────────────────
async def addvideo_shared_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, _ = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    reply = update.message.reply_to_message
    if not reply:
        return await safe_send(context, chat.id,
            "📹 *Shared Video Add karo*\n\n"
            "Reply karo `/addvideo` se\\.\n"
            "Yeh dono male \\& female ko jayega jab gender\\_specific na ho\\."
        )

    mid, mtype = None, None
    if reply.video:
        mid, mtype = reply.video.file_id, "video"
    elif reply.photo:
        mid, mtype = reply.photo[-1].file_id, "photo"
    elif reply.animation:
        mid, mtype = reply.animation.file_id, "gif"

    if not mid:
        return await safe_send(context, chat.id, "❌ Video, photo ya GIF reply karo\\!")

    s   = await get_settings(gid)
    lst = s.get("shared_media", [])
    lst.append({"id": mid, "type": mtype})
    await set_key(gid, "shared_media", lst)

    await safe_send(context, chat.id,
        f"✅ *Shared {mtype} saved\\!*\n\n"
        f"Total shared media: *{len(lst)}* items"
    )


# ── /listmedia ─────────────────────────────────────────────
async def listmedia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, gn = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    s = await get_settings(gid)
    mv  = s.get("male_videos",   [])
    mp  = s.get("male_photos",   [])
    fv  = s.get("female_videos", [])
    fp  = s.get("female_photos", [])
    sh  = s.get("shared_media",  [])

    lines = (
        f"┌──────────────────────┐\n"
        f"│   📂 *MEDIA LIST*    │\n"
        f"│   {esc(gn)}\n"
        f"└──────────────────────┘\n\n"
        f"👦 *Male Media:*\n"
        f"┣━ 🎬 Videos: *{len(mv)}*\n"
        f"┗━ 🖼 Photos/GIF: *{len(mp)}*\n\n"
        f"👧 *Female Media:*\n"
        f"┣━ 🎬 Videos: *{len(fv)}*\n"
        f"┗━ 🖼 Photos/GIF: *{len(fp)}*\n\n"
        f"🔀 *Shared \\(fallback\\):*\n"
        f"┗━ 📁 Items: *{len(sh)}*\n\n"
        f"_/clearmedia male/female/shared se clear karo_"
    )
    await safe_send(context, chat.id, lines)


# ── /clearmedia ────────────────────────────────────────────
async def clearmedia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, _ = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    which = context.args[0].lower() if context.args else ""
    if which == "male":
        await set_key(gid, "male_videos", [])
        await set_key(gid, "male_photos", [])
        await safe_send(context, chat.id, "🗑 *Male media cleared\\!* 👦")
    elif which == "female":
        await set_key(gid, "female_videos", [])
        await set_key(gid, "female_photos", [])
        await safe_send(context, chat.id, "🗑 *Female media cleared\\!* 👧")
    elif which == "shared":
        await set_key(gid, "shared_media", [])
        await safe_send(context, chat.id, "🗑 *Shared media cleared\\!*")
    elif which == "all":
        await set_key(gid, "male_videos",   [])
        await set_key(gid, "male_photos",   [])
        await set_key(gid, "female_videos", [])
        await set_key(gid, "female_photos", [])
        await set_key(gid, "shared_media",  [])
        await safe_send(context, chat.id, "🗑 *Sab media cleared\\!*")
    else:
        await safe_send(context, chat.id,
            "❓ *Kya clear karein?*\n\n"
            "`/clearmedia male`\n"
            "`/clearmedia female`\n"
            "`/clearmedia shared`\n"
            "`/clearmedia all`"
        )


# ── /setbuttons ────────────────────────────────────────────
async def setbuttons_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage:
      /setbuttons
        Button1 | https://link1.com
        Button2 | https://link2.com || Button3 | https://link3.com

    || = same row
    Newline = new row
    """
    chat = update.effective_chat
    gid, _ = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    raw = " ".join(context.args) if context.args else ""
    if not raw and update.message.reply_to_message:
        raw = update.message.reply_to_message.text or ""

    if not raw:
        return await safe_send(context, chat.id,
            "🔘 *Buttons Set Karo*\n\n"
            "*Format:*\n"
            "`/setbuttons`\n"
            "`Rules | https://t.me/... || Channel | https://t.me/...`\n"
            "`Support | https://t.me/...`\n\n"
            "`||` \\= same row mein\n"
            "New line \\= new row\n\n"
            "*Example:*\n"
            "`📜 Rules | https://t.me/rules || 📢 Channel | https://t.me/ch`\n"
            "`💬 Support | https://t.me/support`"
        )

    # Parse
    buttons = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        row     = []
        chunks  = line.split("||")
        for chunk in chunks:
            chunk = chunk.strip()
            if "|" not in chunk:
                continue
            parts = chunk.split("|", 1)
            label = parts[0].strip()
            value = parts[1].strip()
            kind  = "url" if value.startswith("http") else "callback"
            row.append([label, kind, value])
        if row:
            buttons.append(row)

    if not buttons:
        return await safe_send(context, chat.id,
            "❌ Format galat hai\\! Example:\n"
            "`Rules | https://t.me/rules`"
        )

    await set_key(gid, "buttons", json.dumps(buttons))

    # Preview
    kb = build_markup(json.dumps(buttons))
    await safe_send(context, chat.id,
        f"✅ *{len(buttons)} rows, {sum(len(r) for r in buttons)} buttons saved\\!*\n\n"
        f"Aisa dikhega welcome mein 👇",
        reply_markup=kb,
    )


# ── /preview ───────────────────────────────────────────────
async def preview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, gn = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    class FakeUser:
        full_name  = "Test User"
        first_name = "Test"
        last_name  = "User"
        username   = "testuser"
        id         = 123456789

    for gender, label in [("male", "👦 MALE"), ("female", "👧 FEMALE")]:
        await send_welcome(context, chat.id, FakeUser(), gender, gn, "cache")
        await asyncio.sleep(0.8)


# ── /settings ──────────────────────────────────────────────
async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, gn = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    s  = await get_settings(gid)
    ok = lambda v: "✅" if v else "❌"

    mv = len(s.get("male_videos",   [])) + len(s.get("male_photos",   []))
    fv = len(s.get("female_videos", [])) + len(s.get("female_photos", []))
    sh = len(s.get("shared_media",  []))

    await safe_send(context, chat.id,
        f"┌──────────────────────┐\n"
        f"│    ⚙️ *SETTINGS*     │\n"
        f"│    {esc(gn)}\n"
        f"└──────────────────────┘\n\n"
        f"*Template:* `{s.get('template', 'default')}`\n\n"
        f"*Messages:*\n"
        f"┣━ Shared msg: {ok(s.get('custom_msg'))}\n"
        f"┣━ Male msg:   {ok(s.get('male_msg'))}\n"
        f"┗━ Female msg: {ok(s.get('female_msg'))}\n\n"
        f"*Media:*\n"
        f"┣━ 👦 Male media:   *{mv}* items\n"
        f"┣━ 👧 Female media: *{fv}* items\n"
        f"┗━ 🔀 Shared:       *{sh}* items\n\n"
        f"*Buttons:* {ok(s.get('buttons'))}\n"
        f"*Groq AI:* {'✅ Active' if GROQ_API_KEY else '❌ No key'}\n\n"
        f"_/preview se test karo_"
    )


# ── /delete ────────────────────────────────────────────────
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    gid, _ = get_gid(update, context)
    if chat.type != "private" and not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admins!")
    if not gid:
        return await safe_send(context, chat.id, "⚠️ Pehle /connect chalaao\\!")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Haan, sab delete karo", callback_data=f"del_confirm_{gid}")],
        [InlineKeyboardButton("❌ Cancel",                callback_data="cancel")],
    ])
    await safe_send(context, chat.id,
        "⚠️ *Sab settings delete karein?*\n\n"
        "Isme shamil hai:\n"
        "• Welcome messages\n"
        "• Sab videos/photos\n"
        "• Buttons\n"
        "• Template\n\n"
        "Yeh action undo nahi hoga\\!",
        reply_markup=kb,
    )


# ============================================================
#  WELCOME TRIGGER  (new member join)
# ============================================================
async def greet_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r   = update.chat_member
    old = r.old_chat_member.status
    new = r.new_chat_member.status

    # Only truly new joins
    joined_statuses  = (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)
    left_statuses    = (ChatMemberStatus.LEFT,   ChatMemberStatus.BANNED,
                        ChatMemberStatus.RESTRICTED)

    if not (new in joined_statuses and old in left_statuses):
        return

    user = r.new_chat_member.user
    chat = update.effective_chat

    if user.is_bot:
        return

    gn = chat.title or "Group"
    logger.info(f"👤 New member: {user.full_name} in {gn}")

    gender, confidence, method = await detect_gender(
        uid=user.id,
        first=user.first_name or "",
        last=user.last_name   or "",
        username=user.username or "",
    )

    logger.info(f"🔍 Gender result: {gender} ({confidence:.0%}) via {method}")

    if gender != "unknown" and confidence >= 0.7:
        await send_welcome(context, chat.id, user, gender, gn, method)
    else:
        # Ask user to select gender
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("👦 Main Male Hoon",   callback_data=f"gsel_male_{user.id}_{chat.id}"),
            InlineKeyboardButton("👧 Main Female Hoon", callback_data=f"gsel_female_{user.id}_{chat.id}"),
        ]])
        await safe_send(context, chat.id,
            f"┌──────────────────────┐\n"
            f"│   👋 *WELCOME\\!* 👋   │\n"
            f"└──────────────────────┘\n\n"
            f"*{esc(user.first_name or 'User')}*, personalized welcome ke liye\n"
            f"apna gender select karo 👇",
            reply_markup=kb,
        )


# ── Gender selection callback ──────────────────────────────
async def gender_select_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q      = update.callback_query
    await q.answer()

    parts  = q.data.split("_")   # gsel_male_UID_CID
    if len(parts) < 4:
        return

    gender = parts[1]
    uid    = int(parts[2])
    cid    = int(parts[3])

    if update.effective_user.id != uid:
        return await q.answer("❌ Yeh button tumhare liye nahi!", show_alert=True)

    await cache_gender(uid, gender, 1.0)

    try:
        user = (await context.bot.get_chat_member(cid, uid)).user
    except TelegramError:
        user = update.effective_user

    try:
        gn = (await context.bot.get_chat(cid)).title or "Group"
    except TelegramError:
        gn = "Group"

    try:
        await q.message.delete()
    except TelegramError:
        pass

    await send_welcome(context, cid, user, gender, gn, "user_selected")


# ============================================================
#  CALLBACK HANDLER
# ============================================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data

    if data == "cancel":
        try:
            await q.message.delete()
        except Exception:
            pass
        return

    if data == "show_templates":
        await q.message.delete()
        return await template_cmd(update, context)

    if data == "help_guide":
        await q.message.delete()
        return await safe_send(context, q.message.chat.id,
            "┌──────────────────────┐\n"
            "│   📖 *GUIDE*         │\n"
            "└──────────────────────┘\n\n"
            "*Variables:*\n"
            "`{name}` \\- Full name\n"
            "`{username}` \\- @username\n"
            "`{group}` \\- Group name\n"
            "`{member_count}` \\- Members\n"
            "`{date}` \\- DD/MM/YYYY\n"
            "`{time}` \\- HH:MM\n"
            "`{gender_emoji}` \\- 👦/👧\n"
            "`{detect_method}` \\- AI method\n\n"
            "*Workflow:*\n"
            "1\\. /connect group mein\n"
            "2\\. /template chuno\n"
            "3\\. /setwelcome\\_male male msg\n"
            "4\\. /setwelcome\\_female female msg\n"
            "5\\. /addvideo\\_male \\(multiple ok\\)\n"
            "6\\. /addvideo\\_female \\(multiple ok\\)\n"
            "7\\. /setbuttons links\n"
            "8\\. /preview test karo\n"
            "9\\. 🎉 Done\\!"
        )

    if data == "setup_guide":
        await q.message.delete()
        return await safe_send(context, q.message.chat.id,
            "┌──────────────────────┐\n"
            "│   ⚙️ *SETUP GUIDE*   │\n"
            "└──────────────────────┘\n\n"
            "*Step 1:* Bot ko group mein admin banao\n"
            "*Step 2:* Group mein `/connect` chalaao\n"
            "*Step 3:* DM mein wapas aao\n"
            "*Step 4:* `/template` se design chuno\n"
            "*Step 5:* Male/female videos add karo\n"
            "*Step 6:* `/preview` se test karo\n\n"
            "🎉 *Done\\!* New members ko welcome jayega\\!"
        )

    if data.startswith("tpl_"):
        parts    = data.split("_")
        tpl_name = parts[1]
        gid      = int(parts[2])
        await set_key(gid, "template", tpl_name)
        await q.edit_message_text(
            f"✅ *{tpl_name.title()} template set\\!*\n\n"
            f"Ab /preview se dekho kaise dikhega\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if data.startswith("del_confirm_"):
        gid = int(data.split("_")[2])
        await delete_all(gid)
        await q.edit_message_text(
            "✅ *Sab settings delete ho gayi\\!*",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return


# ============================================================
#  ERROR HANDLER
# ============================================================
async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")


# ============================================================
#  MAIN
# ============================================================
def main():
    if not BOT_TOKEN:
        print("\n" + "="*55)
        print("  ❌ BOT_TOKEN environment variable set nahi hai!")
        print("="*55 + "\n")
        return

    # Ensure settings file exists
    p = Path(SETTINGS_FILE)
    if not p.exists():
        p.write_text("{}", encoding="utf-8")

    app = Application.builder().token(BOT_TOKEN).build()

    # ── Commands ──────────────────────────────────────────
    app.add_handler(CommandHandler("start",            start_cmd))
    app.add_handler(CommandHandler("connect",          connect_cmd))
    app.add_handler(CommandHandler("template",         template_cmd))

    # Welcome messages
    app.add_handler(CommandHandler("setwelcome",       setwelcome_cmd))
    app.add_handler(CommandHandler("setwelcome_male",  setwelcome_male_cmd))
    app.add_handler(CommandHandler("setwelcome_female",setwelcome_female_cmd))

    # Media management
    app.add_handler(CommandHandler("addvideo_male",    addvideo_male_cmd))
    app.add_handler(CommandHandler("addvideo_female",  addvideo_female_cmd))
    app.add_handler(CommandHandler("addvideo",         addvideo_shared_cmd))
    app.add_handler(CommandHandler("listmedia",        listmedia_cmd))
    app.add_handler(CommandHandler("clearmedia",       clearmedia_cmd))

    # Buttons / preview / settings
    app.add_handler(CommandHandler("setbuttons",       setbuttons_cmd))
    app.add_handler(CommandHandler("preview",          preview_cmd))
    app.add_handler(CommandHandler("settings",         settings_cmd))
    app.add_handler(CommandHandler("showset",          settings_cmd))   # alias
    app.add_handler(CommandHandler("delete",           delete_cmd))

    # ── Callbacks ─────────────────────────────────────────
    # Gender selection FIRST (specific pattern)
    app.add_handler(CallbackQueryHandler(gender_select_cb,  pattern=r"^gsel_"))
    # General callbacks
    app.add_handler(CallbackQueryHandler(callback_handler,
        pattern=r"^(cancel|show_templates|help_guide|setup_guide|tpl_|del_confirm_)"))

    # ── Chat member join ──────────────────────────────────
    app.add_handler(ChatMemberHandler(greet_member, ChatMemberHandler.CHAT_MEMBER))

    # ── Error ─────────────────────────────────────────────
    app.add_error_handler(error_handler)

    logger.info("🌹 PREMIUM WELCOME BOT - Starting...")
    print("\n" + "="*55)
    print("  🌹 WELCOME BOT RUNNING!")
    print("  ✅ Multiple videos per gender")
    print("  ✅ Groq AI gender detection")
    print("  ✅ Template + Video combo")
    print("  ✅ Male/Female split messages")
    print("  ✅ Random video picker")
    print("="*55 + "\n")

    app.run_polling(allowed_updates=["message", "chat_member", "callback_query"])


if __name__ == "__main__":
    main()
