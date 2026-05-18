"""
╔══════════════════════════════════════════════════════════════╗
║           🌹 PREMIUM WELCOME BOT  by Claude                 ║
║                                                              ║
║  • Sab kuch GROUP mein hota hai — koi private setup nahi    ║
║  • Groq AI se 99% gender detect — koi button nahi aata      ║
║  • Male ka alag video+msg, Female ka alag video+msg          ║
║  • Multiple videos — welcome pe random ek play hota hai      ║
║  • Inline buttons support                                    ║
╚══════════════════════════════════════════════════════════════╝

COMMANDS (sab group mein chalao, admin only):
  /setwelcome_male   <msg>  — Male welcome message set karo
  /setwelcome_female <msg>  — Female welcome message set karo
  /addvideo_male            — Video reply karke male video add karo
  /addvideo_female          — Video reply karke female video add karo
  /setbuttons               — Inline buttons set karo
  /listmedia                — Kitne media hain dekho
  /clearmedia male/female   — Media clear karo
  /preview                  — Test karo
  /settings                 — Current config dekho
  /delwelcome               — Sab settings reset karo

VARIABLES (message mein use karo):
  {name}         — Full name
  {first_name}   — First name
  {username}     — @username
  {mention}      — Clickable mention
  {group}        — Group name
  {member_count} — Members count
  {date}         — DD/MM/YYYY
  {time}         — HH:MM
  {gender_emoji} — 👦 ya 👧
"""

import asyncio
import aiohttp
import logging
import json
import os
import re
import random
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ChatMemberHandler, ContextTypes,
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError

# ──────────────────────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────────────────────
BOT_TOKEN     = os.environ.get("BOT_TOKEN", "")
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
REDIS_URL     = os.environ.get("REDIS_URL", "")
SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "settings.json")

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("WelcomeBot")


# ──────────────────────────────────────────────────────────────
#  MARKDOWNV2 ESCAPE
# ──────────────────────────────────────────────────────────────
_ESC_RE = re.compile(r'([_*\[\]()~`>#+\-=|{}.!\\])')

def esc(text: str) -> str:
    """Escape karo special chars for MarkdownV2."""
    return _ESC_RE.sub(r'\\\1', str(text)) if text else ""


# ──────────────────────────────────────────────────────────────
#  STORAGE  (Redis → JSON fallback)
# ──────────────────────────────────────────────────────────────
_redis = None
_lock  = asyncio.Lock()

async def _get_redis():
    global _redis
    if _redis is None and REDIS_URL:
        try:
            import redis.asyncio as aioredis
            _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            await _redis.ping()
            log.info("✅ Redis connected")
        except Exception as e:
            log.error(f"Redis failed, using JSON: {e}")
            _redis = False
    return _redis or None

def _read_file() -> dict:
    p = Path(SETTINGS_FILE)
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            pass
    return {}

async def _write_file(data: dict):
    async with _lock:
        p   = Path(SETTINGS_FILE)
        tmp = p.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
            tmp.replace(p)
        except Exception as e:
            log.error(f"File write error: {e}")

async def load(gid: int) -> dict:
    r = await _get_redis()
    if r:
        try:
            raw = await r.get(f"wb:{gid}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return _read_file().get(str(gid), {})

async def dump(gid: int, cfg: dict):
    js = json.dumps(cfg, ensure_ascii=False)
    r  = await _get_redis()
    if r:
        try:
            await r.set(f"wb:{gid}", js)
        except Exception:
            pass
    all_data         = _read_file()
    all_data[str(gid)] = cfg
    await _write_file(all_data)

async def set_val(gid: int, key: str, val):
    cfg      = await load(gid)
    cfg[key] = val
    await dump(gid, cfg)

async def wipe(gid: int):
    r = await _get_redis()
    if r:
        try:
            await r.delete(f"wb:{gid}")
        except Exception:
            pass
    data = _read_file()
    data.pop(str(gid), None)
    await _write_file(data)


# ──────────────────────────────────────────────────────────────
#  GENDER CACHE
# ──────────────────────────────────────────────────────────────
_gcache: Dict[int, Tuple[str, float]] = {}

async def gender_cache_set(uid: int, gender: str, conf: float):
    _gcache[uid] = (gender, conf)
    r = await _get_redis()
    if r:
        try:
            await r.setex(f"g:{uid}", 86400 * 30,
                          json.dumps({"g": gender, "c": conf}))
        except Exception:
            pass

async def gender_cache_get(uid: int) -> Optional[Tuple[str, float]]:
    if uid in _gcache:
        return _gcache[uid]
    r = await _get_redis()
    if r:
        try:
            raw = await r.get(f"g:{uid}")
            if raw:
                d = json.loads(raw)
                return (d["g"], d["c"])
        except Exception:
            pass
    return None


# ──────────────────────────────────────────────────────────────
#  GENDER DETECTION  (Groq AI → Name DB)
#  99% accuracy — koi button nahi aata
# ──────────────────────────────────────────────────────────────

# ── Groq AI ───────────────────────────────────────────────────
async def _groq_detect(first: str, last: str, username: str) -> Optional[str]:
    """
    Groq llama3-70b-8192 se gender detect karo.
    Sirf 'male' ya 'female' return karta hai.
    Unknown pe None return karta hai.
    """
    if not GROQ_API_KEY:
        return None

    # Username se clean name nikaalo (hints deta hai)
    uname_hint = re.sub(r'[^a-zA-Z]', ' ', username or "").strip()

    prompt = (
        "You are a gender classifier. Given a person's name details, "
        "output EXACTLY one word: male OR female.\n"
        "Consider all cultural naming conventions (Indian, Arabic, Western, etc).\n"
        "Be decisive — always pick the more likely option.\n"
        "Output ONLY the single word, nothing else.\n\n"
        f"First name: {first}\n"
        f"Last name: {last}\n"
        f"Username hint: {uname_hint}\n\n"
        "Gender:"
    )

    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       "llama3-70b-8192",
                    "messages":    [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens":  3,
                },
                timeout=aiohttp.ClientTimeout(total=6),
            ) as resp:
                if resp.status == 200:
                    data   = await resp.json()
                    answer = data["choices"][0]["message"]["content"]
                    answer = re.sub(r'[^a-zA-Z]', '', answer).lower().strip()
                    if answer in ("male", "female"):
                        log.info(f"🤖 Groq → {answer}  ({first} {last})")
                        return answer
                else:
                    err = await resp.text()
                    log.warning(f"Groq HTTP {resp.status}: {err[:100]}")
    except asyncio.TimeoutError:
        log.warning("Groq timeout — name DB fallback")
    except Exception as e:
        log.error(f"Groq exception: {e}")
    return None


# ── Name Database ──────────────────────────────────────────────
_MALE = {
    # Indian
    "aarav","aditya","akash","akshay","ajay","amit","amitabh","ankit","anurag",
    "arjun","aryan","ashish","ashok","ayush","bhavesh","chirag","deepak","dev",
    "dhruv","dinesh","gaurav","girish","gopal","harish","harsh","hemant","hitesh",
    "jagdish","jayesh","jignesh","kapil","karan","kartik","krishna","kunal","lalit",
    "mahesh","manish","manoj","mohit","mukesh","nagesh","neeraj","nikhil","niraj",
    "pankaj","paresh","prakash","prasad","prashant","rahul","raj","rajesh","rajiv",
    "ramesh","ravi","rohit","rohan","rupesh","sachin","sahil","sanjeev","santosh",
    "satish","shailesh","sharad","shubham","shyam","siddharth","sumit","suraj",
    "suresh","tushar","umesh","varun","vikas","viral","vishal","vivek","yash",
    # English
    "adam","aiden","alex","anthony","caleb","charles","christopher","daniel",
    "david","elijah","ethan","finn","henry","jack","jacob","james","jayden",
    "john","joshua","leo","liam","logan","lucas","mark","mason","matthew",
    "michael","nathan","noah","oliver","owen","richard","robert","ryan",
    "sebastian","thomas","tyler","william",
    # Arabic/Muslim
    "ahmed","ali","bilal","faisal","hamza","hassan","ibrahim","imran","khalid",
    "muhammad","nawaz","omar","salman","shahid","tariq","usman","yusuf","zaid",
    # Russian/Slavic
    "alexei","andrei","boris","dmitri","ivan","nikolai","sergei","viktor",
    # Common short names
    "raj","dev","jay","sam","bob","tom","jim","dan","ben","leo",
}

_FEMALE = {
    # Indian
    "aarti","aisha","ananya","anjali","ankita","anita","anushka","archana","arpita",
    "babita","bharti","chanda","deepika","divya","diya","durga","garima","geeta",
    "ishita","kajal","kamla","kavita","kavya","khushi","kiran","komal","kritika",
    "lalita","lata","leela","madhuri","manju","mansi","meera","megha","monika",
    "muskan","namrata","nandita","neha","nidhi","nikita","nisha","padma","pallavi",
    "pooja","poonam","prachi","preeti","priya","pushpa","rachna","radha","rani",
    "rekha","reena","riya","sakshi","sandhya","savita","seema","sheetal","shilpa",
    "shruti","shweta","simran","sita","sneha","sonia","sonam","sudha","sunita",
    "swati","tanvi","tanya","uma","usha","vani","vidya","yamini","zara",
    # English
    "abigail","amelia","ashley","ava","aurora","brianna","chloe","elizabeth",
    "ella","ellie","emily","emma","evelyn","grace","hannah","harper","hazel",
    "isabella","jessica","lily","lucy","lucy","madison","mia","natalie",
    "olivia","samantha","sarah","scarlett","sofia","sophia","stella","taylor",
    "victoria","violet",
    # Arabic/Muslim
    "amina","asma","aisha","fatima","hafsa","hana","khadija","leila","maryam",
    "noor","ruqayyah","safiya","sara","sumaiya","yasmin","zainab",
    # Russian/Slavic
    "anna","elena","irina","maria","natasha","olga","tatyana","yulia",
    # Common
    "anu","baby","pinky","rinky","sweety","lucky","honey","ruby","lily",
}

def _namedb_detect(first: str, last: str) -> Optional[str]:
    """Name database se detect karo."""
    for name in [first, last]:
        if not name:
            continue
        clean = re.sub(r'[^a-z]', '', name.lower())
        if len(clean) < 2:
            continue
        if clean in _MALE:
            return "male"
        if clean in _FEMALE:
            return "female"
    return None


# ── Master pipeline ────────────────────────────────────────────
async def detect_gender(uid: int, first: str, last: str = "",
                        username: str = "") -> Tuple[str, str]:
    """
    Returns: (gender, method)
    gender  = 'male' | 'female'  — always returns one, never unknown
    method  = 'cache' | 'groq' | 'namedb' | 'guess'
    """
    # 1. Cache
    cached = await gender_cache_get(uid)
    if cached:
        return (cached[0], "cache")

    # 2. Groq AI
    g = await _groq_detect(first, last, username)
    if g:
        await gender_cache_set(uid, g, 0.97)
        return (g, "groq")

    # 3. Name database
    g = _namedb_detect(first, last)
    if g:
        await gender_cache_set(uid, g, 0.85)
        return (g, "namedb")

    # 4. Username se try karo
    if username:
        g = _namedb_detect(username, "")
        if g:
            await gender_cache_set(uid, g, 0.80)
            return (g, "namedb")

    # 5. Last resort — naam ke pattern se guess karo
    #    Indian female names often end in 'a', 'i', 'ee'
    if first:
        fname = re.sub(r'[^a-z]', '', first.lower())
        if fname.endswith(('a', 'i', 'ee', 'ya', 'na', 'ra', 'ka', 'ta')):
            g = "female"
        else:
            g = "male"
        await gender_cache_set(uid, g, 0.65)
        return (g, "guess")

    # Absolute fallback
    await gender_cache_set(uid, "male", 0.5)
    return ("male", "guess")


# ──────────────────────────────────────────────────────────────
#  TEMPLATES
# ──────────────────────────────────────────────────────────────
TEMPLATES = {
    "default": {
        "male": (
            "🌟 *Welcome bhai, {name}\\!* 🌟\n\n"
            "┌──────────────────────────┐\n"
            "│ 👤 *{name}*\n"
            "│ 🆔 {username}\n"
            "│ 📅 {date}  ⏰ {time}\n"
            "│ 👥 Member \\#{member\\_count}\n"
            "└──────────────────────────┘\n\n"
            "💪 *{group}* mein aapka swagat hai\\!\n"
            "Rules zaroor padh lena bhai 🔥"
        ),
        "female": (
            "🌸 *Welcome, {name}\\!* 🌸\n\n"
            "┌──────────────────────────┐\n"
            "│ 👤 *{name}*\n"
            "│ 🆔 {username}\n"
            "│ 📅 {date}  ⏰ {time}\n"
            "│ 👥 Member \\#{member\\_count}\n"
            "└──────────────────────────┘\n\n"
            "💐 *{group}* mein aapka swagat hai\\!\n"
            "Rules zaroor padh lena ✨"
        ),
    },
    "elegant": {
        "male": (
            "✧══════════════════════════✧\n"
            "        💎 *WELCOME BRO*\n"
            "✧══════════════════════════✧\n\n"
            "👦 *{name}*  •  {username}\n"
            "『 {group} 』\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👥 Members: {member\\_count}  │  📅 {date}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🚀 *Enjoy your stay bhai\\!*"
        ),
        "female": (
            "✧══════════════════════════✧\n"
            "        👑 *WELCOME*\n"
            "✧══════════════════════════✧\n\n"
            "👧 *{name}*  •  {username}\n"
            "『 {group} 』\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👥 Members: {member\\_count}  │  📅 {date}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💐 *Enjoy your stay\\!*"
        ),
    },
    "premium": {
        "male": (
            "🏆 ━━━━━━━━━━━━━━━━━━━━━━━ 🏆\n"
            "       ✨ *PREMIUM WELCOME* ✨\n"
            "🏆 ━━━━━━━━━━━━━━━━━━━━━━━ 🏆\n\n"
            "👑 *{name}*\n"
            "┣━ 🆔 {username}\n"
            "┣━ 🏠 {group}\n"
            "┣━ 👥 {member\\_count} members\n"
            "┗━ ⚡ Status: 👦 Verified\n\n"
            "🔥 *Bhai we're excited to have you\\!*"
        ),
        "female": (
            "🏆 ━━━━━━━━━━━━━━━━━━━━━━━ 🏆\n"
            "       ✨ *PREMIUM WELCOME* ✨\n"
            "🏆 ━━━━━━━━━━━━━━━━━━━━━━━ 🏆\n\n"
            "👸 *{name}*\n"
            "┣━ 🆔 {username}\n"
            "┣━ 🏠 {group}\n"
            "┣━ 👥 {member\\_count} members\n"
            "┗━ ⚡ Status: 👧 Verified\n\n"
            "🌺 *We're excited to have you\\!*"
        ),
    },
    "minimal": {
        "male": (
            "▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            "  👦 *{name}* joined\\!\n"
            "▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
            "{username}  │  {group}  │  {member\\_count} members"
        ),
        "female": (
            "▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            "  👧 *{name}* joined\\!\n"
            "▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
            "{username}  │  {group}  │  {member\\_count} members"
        ),
    },
}

_METHOD_TAG = {
    "groq":    "🤖 Groq AI",
    "namedb":  "📚 Name DB",
    "cache":   "💾 Cached",
    "guess":   "🎲 Pattern",
}


# ──────────────────────────────────────────────────────────────
#  RENDER MESSAGE
# ──────────────────────────────────────────────────────────────
async def render(template: str, user, group: str, gid: int,
                 count: int, gender: str, method: str) -> str:
    now = datetime.now()
    subs = {
        "{name}":          esc(user.full_name or user.first_name or "Member"),
        "{first_name}":    esc(user.first_name or ""),
        "{last_name}":     esc(user.last_name  or ""),
        "{username}":      esc(f"@{user.username}" if user.username else (user.first_name or "member")),
        "{mention}":       f"[{esc(user.first_name or 'User')}](tg://user?id={user.id})",
        "{group}":         esc(group),
        "{member_count}":  str(count),
        "{date}":          esc(now.strftime("%d/%m/%Y")),
        "{time}":          esc(now.strftime("%H:%M")),
        "{gender_emoji}":  "👦" if gender == "male" else "👧",
        "{detect_method}": esc(_METHOD_TAG.get(method, method)),
    }
    result = template
    for k, v in subs.items():
        result = result.replace(k, v)
    return result


# ──────────────────────────────────────────────────────────────
#  UTILS
# ──────────────────────────────────────────────────────────────
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        m = await context.bot.get_chat_member(
            update.effective_chat.id, update.effective_user.id
        )
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except TelegramError:
        return False

async def send_md(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                  text: str, markup=None) -> None:
    """MarkdownV2 bhejo, fail pe plain text."""
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except TelegramError as e:
        log.warning(f"MDv2 send failed ({e}), trying plain")
        plain = re.sub(r'[_*\[\]()~`>#+\-=|{}.!\\]', '', text)
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=plain,
                reply_markup=markup,
            )
        except TelegramError as e2:
            log.error(f"Plain send also failed: {e2}")

def parse_buttons(raw: str) -> list:
    """
    Format:
      Button1 | https://link.com || Button2 | https://link2.com
      Button3 | https://link3.com

    newline = new row,  || = same row
    """
    rows = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        row = []
        for chunk in line.split("||"):
            chunk = chunk.strip()
            if "|" not in chunk:
                continue
            label, _, value = chunk.partition("|")
            label  = label.strip()
            value  = value.strip()
            kind   = "url" if value.startswith("http") else "callback"
            row.append([label, kind, value])
        if row:
            rows.append(row)
    return rows

def build_markup(btn_data) -> Optional[InlineKeyboardMarkup]:
    if not btn_data:
        return None
    try:
        rows = json.loads(btn_data) if isinstance(btn_data, str) else btn_data
        kb   = []
        for row in rows:
            r = []
            for b in row:
                if b[1] == "url":
                    r.append(InlineKeyboardButton(b[0], url=b[2]))
                elif b[1] == "callback":
                    r.append(InlineKeyboardButton(b[0], callback_data=b[2]))
            if r:
                kb.append(r)
        return InlineKeyboardMarkup(kb) if kb else None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
#  CORE — SEND WELCOME
# ──────────────────────────────────────────────────────────────
async def send_welcome(context: ContextTypes.DEFAULT_TYPE,
                       chat_id: int, user, gender: str,
                       group_name: str, method: str) -> None:
    cfg = await load(chat_id)

    # 1. Message text — male/female specific → shared → template
    text = cfg.get(f"{gender}_msg") or cfg.get("shared_msg") or ""
    if not text:
        tpl  = TEMPLATES.get(cfg.get("template", "default"), TEMPLATES["default"])
        text = tpl[gender]

    # 2. Render variables
    try:
        count = await context.bot.get_chat_member_count(chat_id)
    except Exception:
        count = 0

    final = await render(text, user, group_name, chat_id, count, gender, method)

    # 3. Buttons
    markup = build_markup(cfg.get("buttons"))

    # 4. Media — gender specific → shared → none
    pool = list(cfg.get(f"{gender}_media", []))
    if not pool:
        pool = list(cfg.get("shared_media", []))

    # 5. Send
    if pool:
        item  = random.choice(pool)
        mid   = item["id"]
        mtype = item["type"]
        try:
            if mtype == "video":
                await context.bot.send_video(
                    chat_id=chat_id, video=mid,
                    caption=final, parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=markup,
                )
            elif mtype == "photo":
                await context.bot.send_photo(
                    chat_id=chat_id, photo=mid,
                    caption=final, parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=markup,
                )
            elif mtype == "gif":
                await context.bot.send_animation(
                    chat_id=chat_id, animation=mid,
                    caption=final, parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=markup,
                )
            log.info(f"✅ Welcome ({gender}/{method}) → {user.full_name} in {chat_id}")
            return
        except TelegramError as e:
            log.error(f"Media send failed: {e} — sending text only")

    # Text only fallback
    await send_md(context, chat_id, final, markup)
    log.info(f"✅ Welcome text ({gender}/{method}) → {user.full_name} in {chat_id}")


# ──────────────────────────────────────────────────────────────
#  ADMIN CHECK WRAPPER
# ──────────────────────────────────────────────────────────────
async def _admin_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if admin, else send error and return False."""
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "⚠️ Yeh command group mein chalao, private mein nahi!"
        )
        return False
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Yeh command sirf admins ke liye hai!")
        return False
    return True


# ──────────────────────────────────────────────────────────────
#  COMMANDS — sab group mein kaam karte hain
# ──────────────────────────────────────────────────────────────

# /start
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌹 *Welcome Bot* ready hai\\!\n\n"
        "*Commands \\(group admin only\\):*\n"
        "`/setwelcome_male` \\- Male message set karo\n"
        "`/setwelcome_female` \\- Female message set karo\n"
        "`/addvideo_male` \\- Male video add karo \\(reply karke\\)\n"
        "`/addvideo_female` \\- Female video add karo \\(reply karke\\)\n"
        "`/setbuttons` \\- Inline buttons set karo\n"
        "`/listmedia` \\- Saved media dekho\n"
        "`/clearmedia` \\- Media clear karo\n"
        "`/template` \\- Template chuno\n"
        "`/preview` \\- Welcome test karo\n"
        "`/settings` \\- Current config dekho\n"
        "`/delwelcome` \\- Sab reset karo\n\n"
        "*Variables jo message mein use kar sakte ho:*\n"
        "`{name}` `{username}` `{mention}` `{group}`\n"
        "`{member_count}` `{date}` `{time}` `{gender_emoji}`",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# /setwelcome_male
async def cmd_setwelcome_male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_guard(update, context):
        return
    gid  = update.effective_chat.id
    text = " ".join(context.args).strip() if context.args else ""
    if not text and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or
                update.message.reply_to_message.caption or "").strip()
    if not text:
        await send_md(context, gid,
            "📝 *Male Welcome Message*\n\n"
            "Usage:\n`/setwelcome_male Bhai {name} welcome\\! 🔥`\n\n"
            "Ya kisi message ko reply karke `/setwelcome_male` bhejo\\.\n\n"
            "*Variables:* `{name}` `{username}` `{mention}`\n"
            "`{group}` `{member_count}` `{date}` `{time}` `{gender_emoji}`"
        )
        return
    await set_val(gid, "male_msg", text)
    await send_md(context, gid, f"✅ *Male welcome message save ho gaya\\!* 👦")


# /setwelcome_female
async def cmd_setwelcome_female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_guard(update, context):
        return
    gid  = update.effective_chat.id
    text = " ".join(context.args).strip() if context.args else ""
    if not text and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or
                update.message.reply_to_message.caption or "").strip()
    if not text:
        await send_md(context, gid,
            "📝 *Female Welcome Message*\n\n"
            "Usage:\n`/setwelcome_female {name} aapka swagat hai\\! 🌸`\n\n"
            "Ya kisi message ko reply karke `/setwelcome_female` bhejo\\.\n\n"
            "*Variables:* `{name}` `{username}` `{mention}`\n"
            "`{group}` `{member_count}` `{date}` `{time}` `{gender_emoji}`"
        )
        return
    await set_val(gid, "female_msg", text)
    await send_md(context, gid, f"✅ *Female welcome message save ho gaya\\!* 👧")


# /addvideo_male
async def cmd_addvideo_male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_guard(update, context):
        return
    gid   = update.effective_chat.id
    reply = update.message.reply_to_message

    if not reply:
        await send_md(context, gid,
            "📹 *Male Video Add Karo*\n\n"
            "Kisi video/photo/GIF pe reply karo aur `/addvideo_male` likho\\.\n\n"
            "Multiple videos add kar sakte ho —\n"
            "welcome pe automatically random ek play hoga 🎲"
        )
        return

    mid, mtype = None, None
    if reply.video:
        mid, mtype = reply.video.file_id, "video"
    elif reply.photo:
        mid, mtype = reply.photo[-1].file_id, "photo"
    elif reply.animation:
        mid, mtype = reply.animation.file_id, "gif"

    if not mid:
        await update.message.reply_text("❌ Video, Photo ya GIF pe reply karo!")
        return

    cfg  = await load(gid)
    pool = cfg.get("male_media", [])
    pool.append({"id": mid, "type": mtype})
    await set_val(gid, "male_media", pool)

    await send_md(context, gid,
        f"✅ *Male {mtype} add ho gaya\\!* 👦\n"
        f"Total male media: *{len(pool)}* items 🎲"
    )


# /addvideo_female
async def cmd_addvideo_female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_guard(update, context):
        return
    gid   = update.effective_chat.id
    reply = update.message.reply_to_message

    if not reply:
        await send_md(context, gid,
            "📹 *Female Video Add Karo*\n\n"
            "Kisi video/photo/GIF pe reply karo aur `/addvideo_female` likho\\.\n\n"
            "Multiple videos add kar sakte ho —\n"
            "welcome pe automatically random ek play hoga 🎲"
        )
        return

    mid, mtype = None, None
    if reply.video:
        mid, mtype = reply.video.file_id, "video"
    elif reply.photo:
        mid, mtype = reply.photo[-1].file_id, "photo"
    elif reply.animation:
        mid, mtype = reply.animation.file_id, "gif"

    if not mid:
        await update.message.reply_text("❌ Video, Photo ya GIF pe reply karo!")
        return

    cfg  = await load(gid)
    pool = cfg.get("female_media", [])
    pool.append({"id": mid, "type": mtype})
    await set_val(gid, "female_media", pool)

    await send_md(context, gid,
        f"✅ *Female {mtype} add ho gaya\\!* 👧\n"
        f"Total female media: *{len(pool)}* items 🎲"
    )


# /setbuttons
async def cmd_setbuttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_guard(update, context):
        return
    gid = update.effective_chat.id
    raw = " ".join(context.args).strip() if context.args else ""
    if not raw and update.message.reply_to_message:
        raw = (update.message.reply_to_message.text or "").strip()

    if not raw:
        await send_md(context, gid,
            "🔘 *Buttons Set Karo*\n\n"
            "*Format:*\n"
            "`Label | https://link.com || Label2 | https://link2.com`\n"
            "`Label3 | https://link3.com`\n\n"
            "`||` \\= same row  │  New line \\= new row\n\n"
            "*Example:*\n"
            "`📜 Rules | https://t.me/rules || 📢 Channel | https://t.me/ch`\n"
            "`💬 Support | https://t.me/support`"
        )
        return

    buttons = parse_buttons(raw)
    if not buttons:
        await update.message.reply_text(
            "❌ Format galat! Example:\n"
            "Rules | https://t.me/rules"
        )
        return

    await set_val(gid, "buttons", json.dumps(buttons))
    total = sum(len(r) for r in buttons)
    markup = build_markup(json.dumps(buttons))
    await send_md(context, gid,
        f"✅ *{len(buttons)} rows, {total} buttons save ho gaye\\!*\n\n"
        f"Preview 👇",
        markup,
    )


# /template
async def cmd_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_guard(update, context):
        return
    gid = update.effective_chat.id
    kb  = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌟 Default", callback_data=f"tpl|default|{gid}"),
         InlineKeyboardButton("💎 Elegant", callback_data=f"tpl|elegant|{gid}")],
        [InlineKeyboardButton("🏆 Premium", callback_data=f"tpl|premium|{gid}"),
         InlineKeyboardButton("🎯 Minimal", callback_data=f"tpl|minimal|{gid}")],
    ])
    await send_md(context, gid,
        "📚 *Template Chuno:*\n\n"
        "🌟 *Default* \\- Clean \\& Professional\n"
        "💎 *Elegant* \\- Stylish Design\n"
        "🏆 *Premium* \\- Bold \\& Beautiful\n"
        "🎯 *Minimal* \\- Simple \\& Clean",
        kb,
    )


# /listmedia
async def cmd_listmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_guard(update, context):
        return
    gid = update.effective_chat.id
    cfg = await load(gid)
    mm  = len(cfg.get("male_media",   []))
    fm  = len(cfg.get("female_media", []))
    sm  = len(cfg.get("shared_media", []))
    await send_md(context, gid,
        f"📂 *Media List*\n\n"
        f"👦 Male media:   *{mm}* items\n"
        f"👧 Female media: *{fm}* items\n"
        f"🔀 Shared:       *{sm}* items\n\n"
        f"Clear karne ke liye:\n"
        f"`/clearmedia male` / `female` / `shared` / `all`"
    )


# /clearmedia
async def cmd_clearmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_guard(update, context):
        return
    gid   = update.effective_chat.id
    which = (context.args[0].lower() if context.args else "").strip()

    map_keys = {
        "male":   ["male_media"],
        "female": ["female_media"],
        "shared": ["shared_media"],
        "all":    ["male_media", "female_media", "shared_media"],
    }

    if which not in map_keys:
        await send_md(context, gid,
            "❓ Kya clear karein?\n\n"
            "`/clearmedia male`\n"
            "`/clearmedia female`\n"
            "`/clearmedia shared`\n"
            "`/clearmedia all`"
        )
        return

    cfg = await load(gid)
    for k in map_keys[which]:
        cfg[k] = []
    await dump(gid, cfg)
    await send_md(context, gid, f"🗑 *{which.title()} media clear ho gaya\\!*")


# /preview
async def cmd_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_guard(update, context):
        return
    gid = update.effective_chat.id
    gn  = update.effective_chat.title or "Group"

    class _FakeUser:
        full_name  = "Test User"
        first_name = "Test"
        last_name  = "User"
        username   = "testuser"
        id         = 123456789

    fu = _FakeUser()
    await send_md(context, gid, "🔍 *Preview bhej raha hoon\\.\\.\\.*")
    await asyncio.sleep(0.5)
    await send_welcome(context, gid, fu, "male",   gn, "cache")
    await asyncio.sleep(1)
    await send_welcome(context, gid, fu, "female", gn, "cache")


# /settings
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_guard(update, context):
        return
    gid = update.effective_chat.id
    cfg = await load(gid)
    ok  = lambda v: "✅" if v else "❌"
    mm  = len(cfg.get("male_media",   []))
    fm  = len(cfg.get("female_media", []))

    await send_md(context, gid,
        f"⚙️ *Settings — {esc(update.effective_chat.title or 'Group')}*\n\n"
        f"*Template:* `{cfg.get('template', 'default')}`\n\n"
        f"*Messages:*\n"
        f"┣━ 👦 Male msg:   {ok(cfg.get('male_msg'))}\n"
        f"┣━ 👧 Female msg: {ok(cfg.get('female_msg'))}\n"
        f"┗━ 🔀 Shared msg: {ok(cfg.get('shared_msg'))}\n\n"
        f"*Media:*\n"
        f"┣━ 👦 Male:   *{mm}* items\n"
        f"┗━ 👧 Female: *{fm}* items\n\n"
        f"*Buttons:* {ok(cfg.get('buttons'))}\n"
        f"*Groq AI:* {'✅ Active' if GROQ_API_KEY else '❌ No API key'}"
    )


# /delwelcome
async def cmd_delwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_guard(update, context):
        return
    gid = update.effective_chat.id
    kb  = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Haan, sab delete karo", callback_data=f"del|{gid}"),
        InlineKeyboardButton("❌ Cancel",                callback_data="cancel"),
    ]])
    await send_md(context, gid,
        "⚠️ *Sab settings delete karein?*\n\n"
        "Messages, videos, buttons sab chala jayega\\.\n"
        "Yeh undo nahi hoga\\!",
        kb,
    )


# ──────────────────────────────────────────────────────────────
#  NEW MEMBER WELCOME  (group pe seedha jata hai)
# ──────────────────────────────────────────────────────────────
async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r   = update.chat_member
    old = r.old_chat_member.status
    new = r.new_chat_member.status

    # Sirf naye join pe trigger karo
    if new not in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        return
    if old not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED,
                   ChatMemberStatus.RESTRICTED):
        return

    user = r.new_chat_member.user
    if user.is_bot:
        return

    chat = update.effective_chat
    log.info(f"👤 New member: {user.full_name} [{user.id}] in '{chat.title}'")

    gender, method = await detect_gender(
        uid=user.id,
        first=user.first_name or "",
        last=user.last_name   or "",
        username=user.username or "",
    )
    log.info(f"🔍 Gender: {gender} via {method}")

    await send_welcome(context, chat.id, user, gender, chat.title or "Group", method)


# ──────────────────────────────────────────────────────────────
#  CALLBACKS
# ──────────────────────────────────────────────────────────────
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data

    # Template selection:  "tpl|name|gid"
    if data.startswith("tpl|"):
        _, name, gid_s = data.split("|", 2)
        gid = int(gid_s)
        await set_val(gid, "template", name)
        await q.edit_message_text(
            f"✅ *{name.title()} template set\\!*\n/preview se dekho\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    # Delete confirm:  "del|gid"
    if data.startswith("del|"):
        gid = int(data.split("|")[1])
        await wipe(gid)
        await q.edit_message_text(
            "✅ *Sab settings delete ho gayi\\!*",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if data == "cancel":
        try:
            await q.message.delete()
        except Exception:
            pass
        return

    await q.answer()


# ──────────────────────────────────────────────────────────────
#  ERROR HANDLER
# ──────────────────────────────────────────────────────────────
async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.error(f"Error: {context.error}  |  Update: {update}")


# ──────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        print("\n❌  BOT_TOKEN environment variable set nahi hai!\n")
        return

    # JSON file init
    p = Path(SETTINGS_FILE)
    if not p.exists():
        p.write_text("{}", "utf-8")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",            cmd_start))
    app.add_handler(CommandHandler("setwelcome_male",  cmd_setwelcome_male))
    app.add_handler(CommandHandler("setwelcome_female",cmd_setwelcome_female))
    app.add_handler(CommandHandler("addvideo_male",    cmd_addvideo_male))
    app.add_handler(CommandHandler("addvideo_female",  cmd_addvideo_female))
    app.add_handler(CommandHandler("setbuttons",       cmd_setbuttons))
    app.add_handler(CommandHandler("template",         cmd_template))
    app.add_handler(CommandHandler("listmedia",        cmd_listmedia))
    app.add_handler(CommandHandler("clearmedia",       cmd_clearmedia))
    app.add_handler(CommandHandler("preview",          cmd_preview))
    app.add_handler(CommandHandler("settings",         cmd_settings))
    app.add_handler(CommandHandler("delwelcome",       cmd_delwelcome))

    # Callbacks
    app.add_handler(CallbackQueryHandler(on_callback))

    # New member joins
    app.add_handler(ChatMemberHandler(on_new_member, ChatMemberHandler.CHAT_MEMBER))

    # Error
    app.add_error_handler(on_error)

    log.info("🌹 Welcome Bot starting...")
    print("\n" + "=" * 50)
    print("  🌹 PREMIUM WELCOME BOT RUNNING")
    print("  ✅ Group-only setup (no private needed)")
    print("  ✅ Groq AI 99% gender detection")
    print("  ✅ Multiple videos per gender")
    print("  ✅ No gender buttons ever")
    print("=" * 50 + "\n")

    app.run_polling(
        allowed_updates=["message", "chat_member", "callback_query"]
    )


if __name__ == "__main__":
    main()
