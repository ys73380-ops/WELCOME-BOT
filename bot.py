"""
╔══════════════════════════════════════════════════════════════╗
║                🌹 PREMIUM WELCOME BOT                        ║
║  • Sirf 2 config commands: /set_male  aur  /set_female      ║
║  • Ek hi command se message set + video add (multiple)      ║
║  • /connect se group connect karo DM config ke liye         ║
╚══════════════════════════════════════════════════════════════╝

🔥 COMMANDS:

  /connect     — Group mein use karo, DM config link milega
  /set_male    — Male message set + video add (DM mein)
  /set_female  — Female message set + video add (DM mein)
  /listmedia   — Kitne media hain dekho
  /clearmedia  — Media clear karo (male/female/all)
  /preview     — Test karo
  /settings    — Current config dekho
  /setbuttons  — Inline buttons set karo
  /reset       — Sab settings reset karo
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
    ChatMemberHandler, ContextTypes
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
    if not text:
        return ""
    return _ESC_RE.sub(r'\\\1', str(text))

# ──────────────────────────────────────────────────────────────
#  STORAGE
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
#  GENDER DETECTION (unchanged, working)
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

async def _groq_detect(first: str, last: str, username: str) -> Optional[str]:
    if not GROQ_API_KEY:
        return None
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
    except Exception as e:
        log.warning(f"Groq exception: {e}")
    return None

_MALE = {
    "aarav","aditya","akash","akshay","ajay","amit","ankit","arjun","ayush",
    "deepak","gaurav","harsh","karan","kunal","manish","mohit","nikhil","pankaj",
    "rahul","raj","ravi","rohit","sachin","shubham","suraj","varun","vikas","vishal",
    "adam","alex","anthony","daniel","david","james","john","michael","robert","william",
    "ahmed","ali","bilal","hamza","hassan","ibrahim","muhammad","omar","usman","yusuf",
    "andrei","boris","dmitri","ivan","nikolai","sergei","viktor",
}
_FEMALE = {
    "aarti","anjali","ankita","anita","anushka","divya","diya","geeta","kavita","kavya",
    "kiran","komal","meera","neha","nidhi","nikita","nisha","pooja","preeti","priya",
    "riya","sakshi","shilpa","shruti","simran","sneha","sonia","tanvi",
    "abigail","amelia","ava","chloe","emily","emma","isabella","mia","olivia","sophia",
    "amina","aisha","fatima","khadija","maryam","noor","zainab",
    "anna","elena","maria","natasha","olga","tatyana",
}

def _namedb_detect(first: str, last: str) -> Optional[str]:
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

async def detect_gender(uid: int, first: str, last: str = "",
                        username: str = "") -> Tuple[str, str]:
    cached = await gender_cache_get(uid)
    if cached:
        return (cached[0], "cache")
    g = await _groq_detect(first, last, username)
    if g:
        await gender_cache_set(uid, g, 0.97)
        return (g, "groq")
    g = _namedb_detect(first, last)
    if g:
        await gender_cache_set(uid, g, 0.85)
        return (g, "namedb")
    if username:
        g = _namedb_detect(username, "")
        if g:
            await gender_cache_set(uid, g, 0.80)
            return (g, "namedb")
    if first:
        fname = re.sub(r'[^a-z]', '', first.lower())
        if fname.endswith(('a', 'i', 'ee', 'ya', 'na', 'ra', 'ka', 'ta')):
            g = "female"
        else:
            g = "male"
        await gender_cache_set(uid, g, 0.65)
        return (g, "guess")
    await gender_cache_set(uid, "male", 0.5)
    return ("male", "guess")

# ──────────────────────────────────────────────────────────────
#  DEFAULT TEMPLATES
# ──────────────────────────────────────────────────────────────
DEFAULT_MALE_MSG = (
    "🌟 *Welcome bhai, {name}\\!* 🌟\n\n"
    "┌──────────────────────────┐\n"
    "│ 👤 *{name}*\n"
    "│ 🆔 {username}\n"
    "│ 📅 {date}  ⏰ {time}\n"
    "│ 👥 Member \\#{member\\_count}\n"
    "└──────────────────────────┘\n\n"
    "💪 *{group}* mein aapka swagat hai\\!\n"
    "Rules zaroor padh lena bhai 🔥"
)

DEFAULT_FEMALE_MSG = (
    "🌸 *Welcome, {name}\\!* 🌸\n\n"
    "┌──────────────────────────┐\n"
    "│ 👤 *{name}*\n"
    "│ 🆔 {username}\n"
    "│ 📅 {date}  ⏰ {time}\n"
    "│ 👥 Member \\#{member\\_count}\n"
    "└──────────────────────────┘\n\n"
    "💐 *{group}* mein aapka swagat hai\\!\n"
    "Rules zaroor padh lena ✨"
)

_METHOD_TAG = {
    "groq":    "🤖 Groq AI",
    "namedb":  "📚 Name DB",
    "cache":   "💾 Cached",
    "guess":   "🎲 Pattern",
}

# ──────────────────────────────────────────────────────────────
#  RENDER MESSAGE
# ──────────────────────────────────────────────────────────────
async def render(text_template: str, user, group: str, gid: int,
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
    result = text_template
    for k, v in subs.items():
        result = result.replace(k, v)
    return result

# ──────────────────────────────────────────────────────────────
#  CORE: SEND WELCOME
# ──────────────────────────────────────────────────────────────
async def send_welcome(context: ContextTypes.DEFAULT_TYPE,
                       chat_id: int, user, gender: str,
                       group_name: str, method: str) -> None:
    cfg = await load(chat_id)

    text = cfg.get(f"{gender}_msg")
    if not text:
        text = DEFAULT_MALE_MSG if gender == "male" else DEFAULT_FEMALE_MSG

    try:
        count = await context.bot.get_chat_member_count(chat_id)
    except Exception:
        count = 0

    final = await render(text, user, group_name, chat_id, count, gender, method)

    markup = None
    if cfg.get("buttons"):
        try:
            buttons = json.loads(cfg["buttons"])
            kb = []
            for row in buttons:
                r = []
                for b in row:
                    if b[1] == "url":
                        r.append(InlineKeyboardButton(b[0], url=b[2]))
                    elif b[1] == "callback":
                        r.append(InlineKeyboardButton(b[0], callback_data=b[2]))
                if r:
                    kb.append(r)
            markup = InlineKeyboardMarkup(kb) if kb else None
        except Exception:
            pass

    pool = list(cfg.get(f"{gender}_media", []))
    if pool:
        item = random.choice(pool)
        mid, mtype = item["id"], item["type"]
        try:
            if mtype == "video":
                await context.bot.send_video(chat_id, video=mid, caption=final,
                                             parse_mode=ParseMode.MARKDOWN_V2, reply_markup=markup)
            elif mtype == "photo":
                await context.bot.send_photo(chat_id, photo=mid, caption=final,
                                             parse_mode=ParseMode.MARKDOWN_V2, reply_markup=markup)
            elif mtype == "gif":
                await context.bot.send_animation(chat_id, animation=mid, caption=final,
                                                 parse_mode=ParseMode.MARKDOWN_V2, reply_markup=markup)
            log.info(f"✅ Welcome ({gender}/{method}) → {user.full_name} in {chat_id}")
            return
        except TelegramError as e:
            log.error(f"Media send failed: {e} — sending text only")

    try:
        await context.bot.send_message(chat_id, text=final,
                                       parse_mode=ParseMode.MARKDOWN_V2, reply_markup=markup,
                                       disable_web_page_preview=True)
    except TelegramError:
        plain = re.sub(r'[_*\[\]()~`>#+\-=|{}.!\\]', '', final)
        await context.bot.send_message(chat_id, text=plain, reply_markup=markup)
    log.info(f"✅ Welcome text ({gender}/{method}) → {user.full_name} in {chat_id}")

# ──────────────────────────────────────────────────────────────
#  DM CONNECTION SESSION (user -> group_id)
# ──────────────────────────────────────────────────────────────
_connected_groups: Dict[int, int] = {}  # user_id -> group_id

async def get_connected_group(user_id: int) -> Optional[int]:
    return _connected_groups.get(user_id)

async def set_connected_group(user_id: int, group_id: int):
    _connected_groups[user_id] = group_id
    # Also store in Redis if available
    r = await _get_redis()
    if r:
        try:
            await r.setex(f"conn:{user_id}", 86400 * 7, str(group_id))
        except Exception:
            pass

# ──────────────────────────────────────────────────────────────
#  COMMANDS
# ──────────────────────────────────────────────────────────────

async def cmd_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group mein use karo – DM link bhejega"""
    chat = update.effective_chat
    user_id = update.effective_user.id

    # Only works in groups
    if chat.type == "private":
        await update.message.reply_text(esc("❌ Ye command group mein use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return

    # Check if user is admin
    try:
        member = await context.bot.get_chat_member(chat.id, user_id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await update.message.reply_text(esc("❌ Sirf admin hi connect kar sakta hai."), parse_mode=ParseMode.MARKDOWN_V2)
            return
    except TelegramError:
        await update.message.reply_text(esc("❌ Admin check failed."), parse_mode=ParseMode.MARKDOWN_V2)
        return

    group_id = chat.id
    bot_username = (await context.bot.get_me()).username
    deep_link = f"https://t.me/{bot_username}?start=connect_{group_id}"

    await update.message.reply_text(
        esc(f"🔗 *Connect to DM*\n\n"
            f"Group: {chat.title}\n"
            f"Group ID: `{group_id}`\n\n"
            f"👇 Is link pe click kar aur DM mein setup kar:\n\n"
            f"{deep_link}\n\n"
            f"DM mein jaake /set_male ya /set_female use kar. Group ID nahi dena padega."),
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deep link connect_<group_id>"""
    user_id = update.effective_user.id
    args = context.args

    if args and args[0].startswith("connect_"):
        # Deep link: /start connect_-100123456789
        try:
            group_id = int(args[0].split("_", 1)[1])
            await set_connected_group(user_id, group_id)
            await update.message.reply_text(
                esc(f"✅ Connected to group ID: `{group_id}`\n\n"
                    f"Ab DM mein bina group ID diye /set_male ya /set_female use kar sakte ho.\n"
                    f"Video add karne ke liye kisi video pe reply karke /set_male bhejo.\n\n"
                    f"Commands: /set_male, /set_female, /listmedia, /clearmedia, /preview, /settings, /setbuttons, /reset"),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        except (ValueError, IndexError):
            pass

    # Normal /start
    await update.message.reply_text(
        esc("🌹 *Welcome Bot* — Simple Setup\n\n"
            "**Pehle group mein /connect use karo.**\n"
            "Phir DM mein aake ye commands use kar:\n\n"
            "▪ /set_male — male message + video add\n"
            "▪ /set_female — female message + video add\n"
            "▪ /listmedia — media count\n"
            "▪ /clearmedia — clear media\n"
            "▪ /preview — test welcome\n"
            "▪ /settings — current config\n"
            "▪ /setbuttons — inline buttons\n"
            "▪ /reset — delete all settings\n\n"
            "Variables: {name}, {username}, {mention}, {group}, {member_count}, {date}, {time}, {gender_emoji}"),
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def set_gender_config(update: Update, context: ContextTypes.DEFAULT_TYPE, gender: str):
    """DM mein config set karna, connected group use karega"""
    user_id = update.effective_user.id
    chat = update.effective_chat

    # Only works in DM
    if chat.type != "private":
        await update.message.reply_text(esc("❌ Ye command DM mein use karo. Pehle group mein /connect karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return

    group_id = await get_connected_group(user_id)
    if not group_id:
        await update.message.reply_text(
            esc("❌ Koi group connected nahi hai.\n\n"
                "Pehle group mein jaake /connect use karo, phir yahan aao."),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # Get text from command arguments or reply message
    text = " ".join(context.args) if context.args else ""
    if not text and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or update.message.reply_to_message.caption or "").strip()

    # Check for media in reply (video, photo, gif)
    reply = update.message.reply_to_message
    media_id = None
    media_type = None
    if reply:
        if reply.video:
            media_id, media_type = reply.video.file_id, "video"
        elif reply.photo:
            media_id, media_type = reply.photo[-1].file_id, "photo"
        elif reply.animation:
            media_id, media_type = reply.animation.file_id, "gif"

    actions = []
    if media_id:
        cfg = await load(group_id)
        pool = cfg.get(f"{gender}_media", [])
        pool.append({"id": media_id, "type": media_type})
        await set_val(group_id, f"{gender}_media", pool)
        actions.append(f"✅ {gender.title()} {media_type} add ho gaya (total: {len(pool)})")

    if text:
        await set_val(group_id, f"{gender}_msg", text)
        actions.append(f"✅ {gender.title()} welcome message save ho gaya")

    if not actions:
        await update.message.reply_text(
            esc(f"📝 {gender.title()} Configuration\n\n"
                f"Message set karne ke liye: `/set_{gender} Your message here`\n"
                f"Video add karne ke liye: video pe reply karke `/set_{gender}` bhejo.\n\n"
                f"Variables: {{name}}, {{username}}, {{group}}, {{member_count}}, etc.\n\n"
                f"Connected group ID: `{group_id}`"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    await update.message.reply_text("\n".join(actions))

async def cmd_set_male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_gender_config(update, context, "male")

async def cmd_set_female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_gender_config(update, context, "female")

async def cmd_listmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text(esc("❌ DM mein use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    user_id = update.effective_user.id
    group_id = await get_connected_group(user_id)
    if not group_id:
        await update.message.reply_text(esc("❌ Pehle /connect use karo group mein."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    cfg = await load(group_id)
    mm = len(cfg.get("male_media", []))
    fm = len(cfg.get("female_media", []))
    await update.message.reply_text(esc(f"📂 Media List\n\n👦 Male: {mm} items\n👧 Female: {fm} items"), parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_clearmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text(esc("❌ DM mein use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    user_id = update.effective_user.id
    group_id = await get_connected_group(user_id)
    if not group_id:
        await update.message.reply_text(esc("❌ Pehle /connect use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    if not context.args:
        await update.message.reply_text(esc("Usage: /clearmedia male / female / all"), parse_mode=ParseMode.MARKDOWN_V2)
        return
    which = context.args[0].lower()
    cfg = await load(group_id)
    if which == "male":
        cfg["male_media"] = []
    elif which == "female":
        cfg["female_media"] = []
    elif which == "all":
        cfg["male_media"] = []
        cfg["female_media"] = []
    else:
        await update.message.reply_text(esc("Use: male / female / all"), parse_mode=ParseMode.MARKDOWN_V2)
        return
    await dump(group_id, cfg)
    await update.message.reply_text(esc(f"🗑 {which.title()} media clear ho gaya"), parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text(esc("❌ DM mein use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    user_id = update.effective_user.id
    group_id = await get_connected_group(user_id)
    if not group_id:
        await update.message.reply_text(esc("❌ Pehle /connect use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    chat = await context.bot.get_chat(group_id)
    group_name = chat.title or "Group"
    class FakeUser:
        full_name = "Test User"
        first_name = "Test"
        last_name = ""
        username = "testuser"
        id = 123456789
    fu = FakeUser()
    await update.message.reply_text(esc("🔍 Sending preview..."), parse_mode=ParseMode.MARKDOWN_V2)
    await asyncio.sleep(0.5)
    await send_welcome(context, group_id, fu, "male", group_name, "cache")
    await asyncio.sleep(1)
    await send_welcome(context, group_id, fu, "female", group_name, "cache")

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text(esc("❌ DM mein use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    user_id = update.effective_user.id
    group_id = await get_connected_group(user_id)
    if not group_id:
        await update.message.reply_text(esc("❌ Pehle /connect use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    cfg = await load(group_id)
    chat = await context.bot.get_chat(group_id)
    mm = len(cfg.get("male_media", []))
    fm = len(cfg.get("female_media", []))
    await update.message.reply_text(
        esc(f"⚙️ Settings — {chat.title}\n\n"
            f"Male message: {'✅' if cfg.get('male_msg') else '❌ (default)'}\n"
            f"Female message: {'✅' if cfg.get('female_msg') else '❌ (default)'}\n"
            f"Male media: {mm} items\n"
            f"Female media: {fm} items\n"
            f"Buttons: {'✅' if cfg.get('buttons') else '❌'}\n"
            f"Groq AI: {'✅ Active' if GROQ_API_KEY else '❌ No API key'}"),
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def cmd_setbuttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text(esc("❌ DM mein use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    user_id = update.effective_user.id
    group_id = await get_connected_group(user_id)
    if not group_id:
        await update.message.reply_text(esc("❌ Pehle /connect use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    raw = " ".join(context.args) if context.args else ""
    if not raw and update.message.reply_to_message:
        raw = update.message.reply_to_message.text or ""
    if not raw:
        await update.message.reply_text(
            esc("🔘 Buttons Setup\n\nFormat:\n`Label | https://link.com || Label2 | https://link2.com`\nNew line = new row, `||` = same row\n\nExample:\n`📜 Rules | https://t.me/rules || 📢 Channel | https://t.me/ch`"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    rows = []
    for line in raw.strip().split("\n"):
        if not line.strip():
            continue
        row = []
        for chunk in line.split("||"):
            if "|" not in chunk:
                continue
            label, _, value = chunk.partition("|")
            label = label.strip()
            value = value.strip()
            kind = "url" if value.startswith("http") else "callback"
            row.append([label, kind, value])
        if row:
            rows.append(row)
    if not rows:
        await update.message.reply_text(esc("❌ Invalid format! Use: Label | URL"), parse_mode=ParseMode.MARKDOWN_V2)
        return
    await set_val(group_id, "buttons", json.dumps(rows))
    total = sum(len(r) for r in rows)
    await update.message.reply_text(esc(f"✅ {len(rows)} rows, {total} buttons saved!"), parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text(esc("❌ DM mein use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    user_id = update.effective_user.id
    group_id = await get_connected_group(user_id)
    if not group_id:
        await update.message.reply_text(esc("❌ Pehle /connect use karo."), parse_mode=ParseMode.MARKDOWN_V2)
        return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes, reset everything", callback_data=f"reset|{group_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
    ]])
    await update.message.reply_text(
        esc("⚠️ Reset all settings?\n\nMessages, media, buttons will be deleted. This cannot be undone."),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=kb
    )

# ──────────────────────────────────────────────────────────────
#  NEW MEMBER HANDLER (unchanged)
# ──────────────────────────────────────────────────────────────
async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r = update.chat_member
    old = r.old_chat_member.status
    new = r.new_chat_member.status
    if new not in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        return
    if old not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED):
        return
    user = r.new_chat_member.user
    if user.is_bot:
        return
    chat = update.effective_chat
    log.info(f"👤 New member: {user.full_name} [{user.id}] in '{chat.title}'")
    gender, method = await detect_gender(
        uid=user.id,
        first=user.first_name or "",
        last=user.last_name or "",
        username=user.username or "",
    )
    log.info(f"🔍 Gender: {gender} via {method}")
    await send_welcome(context, chat.id, user, gender, chat.title or "Group", method)

# ──────────────────────────────────────────────────────────────
#  CALLBACK HANDLER
# ──────────────────────────────────────────────────────────────
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    if data.startswith("reset|"):
        gid = int(data.split("|")[1])
        await wipe(gid)
        await q.edit_message_text(esc("✅ All settings deleted for this group."), parse_mode=ParseMode.MARKDOWN_V2)
    elif data == "cancel":
        try:
            await q.message.delete()
        except Exception:
            pass
    await q.answer()

# ──────────────────────────────────────────────────────────────
#  ERROR HANDLER
# ──────────────────────────────────────────────────────────────
async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.error(f"Error: {context.error} | Update: {update}")

# ──────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        print("\n❌ BOT_TOKEN environment variable not set!\n")
        return
    Path(SETTINGS_FILE).touch(exist_ok=True)
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("connect", cmd_connect))
    app.add_handler(CommandHandler("set_male", cmd_set_male))
    app.add_handler(CommandHandler("set_female", cmd_set_female))
    app.add_handler(CommandHandler("listmedia", cmd_listmedia))
    app.add_handler(CommandHandler("clearmedia", cmd_clearmedia))
    app.add_handler(CommandHandler("preview", cmd_preview))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("setbuttons", cmd_setbuttons))
    app.add_handler(CommandHandler("reset", cmd_reset))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(ChatMemberHandler(on_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_error_handler(on_error)

    log.info("🌹 Premium Welcome Bot starting...")
    print("\n" + "=" * 50)
    print("  🌹 PREMIUM WELCOME BOT RUNNING")
    print("  ✅ /connect in group → DM link")
    print("  ✅ DM mein bina group ID config")
    print("  ✅ Sirf 2 commands: /set_male & /set_female")
    print("=" * 50 + "\n")

    app.run_polling(allowed_updates=["message", "chat_member", "callback_query"])

if __name__ == "__main__":
    main()
