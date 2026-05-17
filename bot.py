"""
╔══════════════════════════════════════════════════════════════╗
║       🌹 PREMIUM WELCOME BOT                                
║   Professional Welcome System · Gender Detection             
║   Custom Templates · Media Support · Buttons                 
╚══════════════════════════════════════════════════════════════╝

FEATURES LIKE ROSE BOT:
✅ Beautiful formatted borders
✅ Multiple media types (video/photo/GIF)
✅ Inline buttons for rules/channels
✅ Premium templates library
✅ Gender-based personalization
✅ Preview system
"""

import asyncio
import aiohttp
import logging
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from datetime import datetime
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ChatMemberHandler, ContextTypes, MessageHandler, filters
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError

# ============= ENVIRONMENT VARIABLES =============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
REDIS_URL = os.environ.get("REDIS_URL", "")
SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "bot_settings.json")

# ============= LOGGING =============
logging.basicConfig(
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# ============= HELPER FUNCTIONS =============
def esc(text: str) -> str:
    if not text:
        return text
    return (text
        .replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("~", "\\~")
        .replace("|", "\\|")
        .replace(">", "\\>")
        .replace("#", "\\#")
        .replace("-", "\\-")
        .replace("+", "\\+")
        .replace("=", "\\=")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace(".", "\\.")
        .replace("!", "\\!"))

def format_border(text: str, border_char: str = "★", title: str = "WELCOME") -> str:
    """Create beautiful bordered message like Rose bot"""
    lines = text.split('\n')
    max_len = max(len(re.sub(r'\*.*?\*', '', line)) for line in lines) + 4
    border = border_char * min(max_len, 40)
    
    result = f"┌{border}┐\n"
    result += f"│  ✨ {title} ✨  │\n"
    result += f"├{border}┤\n"
    for line in lines:
        padding = (max_len - len(re.sub(r'\*.*?\*', '', line))) // 2
        result += f"│{' ' * padding}{line}{' ' * padding}│\n"
    result += f"└{border}┘"
    return result

# ============= REDIS + JSON STORAGE =============
_redis_conn = None
_json_lock = asyncio.Lock()

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
    path = Path(SETTINGS_FILE)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

async def _save_json(data: dict):
    async with _json_lock:
        path = Path(SETTINGS_FILE)
        try:
            tmp = path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except OSError as e:
            logger.error(f"JSON save error: {e}")

async def get_group_settings(group_id: int) -> dict:
    gid = str(group_id)
    r = await _get_redis()
    if r:
        try:
            raw = await r.get(f"wb:{gid}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return _load_json().get(gid, {})

async def set_group_key(group_id: int, key: str, value):
    gid = str(group_id)
    r = await _get_redis()
    settings = {}
    if r:
        try:
            raw = await r.get(f"wb:{gid}")
            if raw:
                settings = json.loads(raw)
        except Exception:
            pass
    if not settings:
        settings = _load_json().get(gid, {})

    settings[key] = value
    js = json.dumps(settings, ensure_ascii=False)

    if r:
        try:
            await r.set(f"wb:{gid}", js)
        except Exception:
            pass
    all_s = _load_json()
    all_s[gid] = settings
    await _save_json(all_s)
    logger.info(f"[{gid}] Saved {key}")

async def delete_group_key(group_id: int, key: str = None):
    gid = str(group_id)
    r = await _get_redis()

    if key:
        s = await get_group_settings(group_id)
        s.pop(key, None)
        if not s:
            if r:
                try: await r.delete(f"wb:{gid}")
                except: pass
            all_s = _load_json()
            all_s.pop(gid, None)
            await _save_json(all_s)
        else:
            js = json.dumps(s, ensure_ascii=False)
            if r:
                try: await r.set(f"wb:{gid}", js)
                except: pass
            all_s = _load_json()
            all_s[gid] = s
            await _save_json(all_s)
    else:
        if r:
            try: await r.delete(f"wb:{gid}")
            except: pass
        all_s = _load_json()
        all_s.pop(gid, None)
        await _save_json(all_s)


# ============= GENDER CACHE =============
_gender_cache: Dict[int, Dict] = {}

async def cache_gender(user_id: int, gender: str, confidence: float):
    _gender_cache[user_id] = {
        "gender": gender,
        "confidence": confidence,
        "timestamp": asyncio.get_event_loop().time()
    }
    r = await _get_redis()
    if r:
        try:
            await r.setex(f"gender:{user_id}", 86400 * 30, json.dumps({
                "gender": gender, "confidence": confidence
            }))
        except:
            pass

async def get_cached_gender(user_id: int) -> Optional[Tuple[str, float]]:
    if user_id in _gender_cache:
        cached = _gender_cache[user_id]
        return (cached["gender"], cached["confidence"])
    r = await _get_redis()
    if r:
        try:
            data = await r.get(f"gender:{user_id}")
            if data:
                d = json.loads(data)
                return (d["gender"], d["confidence"])
        except:
            pass
    return None


# ============= GENDER DETECTION =============
async def detect_gender_groq(first_name: str, last_name: str = "", username: str = "") -> Optional[Tuple[str, float]]:
    if not GROQ_API_KEY:
        return None
    
    prompt = f"""Based on the name, determine the likely gender.
Return ONLY: "male" or "female".
Only answer if confidence > 80%.

Name: {first_name} {last_name}
Username: {username}

Gender:"""

    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "llama3-70b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 10
            }
            
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    gender = result["choices"][0]["message"]["content"].strip().lower()
                    if gender in ["male", "female"]:
                        logger.info(f"GROQ detected: {gender} for {first_name}")
                        return (gender, 0.95)
    except Exception as e:
        logger.error(f"GROQ API error: {e}")
    return None

# Name database
MALE_NAMES = {"aarav","aditya","akash","amit","ankit","arjun","aryan","ayush","deepak","dev","dhruv","gaurav","harsh","kartik","karan","kunal","manish","mohit","nikhil","rahul","raj","rajesh","ravi","rohit","rohan","sachin","sahil","shubham","sumit","suraj","varun","vikas","vivek","yash","james","john","robert","michael","william","david","richard","thomas","charles","christopher","daniel","matthew","anthony","mark","liam","noah","oliver","elijah","lucas","mason","ali","muhammad","omar","hassan","ibrahim","ahmed"}
FEMALE_NAMES = {"aisha","ananya","anjali","ankita","anushka","arpita","deepika","divya","garima","ishita","kajal","kavya","khushi","komal","kritika","mansi","megha","meera","muskan","namrata","neha","nikita","nisha","pallavi","pooja","priya","riya","sakshi","sandhya","shruti","simran","sneha","sonam","tanvi","tanya","vidya","zara","diya","sarah","emily","emma","olivia","ava","sophia","isabella","mia","amelia","harper","evelyn","abigail","elizabeth","sofia","ella","grace","chloe","fatima","maryam","amina","hana","sara","leila","yasmin","noor"}

async def detect_gender_name(name: str) -> Optional[Tuple[str, float]]:
    if not name:
        return None
    clean = re.sub(r"[^a-zA-Z]", "", name).lower()
    if len(clean) < 2:
        return None
    if clean in MALE_NAMES:
        return ("male", 0.85)
    if clean in FEMALE_NAMES:
        return ("female", 0.85)
    return None

async def detect_gender_master(user_id: int, first_name: str, last_name: str = "", username: str = "") -> Tuple[str, float, str]:
    cached = await get_cached_gender(user_id)
    if cached:
        return (cached[0], cached[1], "cache")
    
    result = await detect_gender_groq(first_name, last_name, username)
    if result:
        gender, confidence = result
        await cache_gender(user_id, gender, confidence)
        return (gender, confidence, "groq_ai")
    
    result = await detect_gender_name(f"{first_name} {last_name}")
    if result:
        gender, confidence = result
        await cache_gender(user_id, gender, confidence)
        return (gender, confidence, "name_database")
    
    return ("unknown", 0.0, "none")


# ============= PROFESSIONAL TEMPLATES (ROSE BOT STYLE) =============
PROFESSIONAL_TEMPLATES = {
    "default": {
        "male": "🌟 *Welcome to {group}, {name}!* 🌟\n\n"
                "┌─────────────────────┐\n"
                "│ 👤 Name: {name}      │\n"
                "│ 🆔 Username: {username} │\n"
                "│ 📅 Joined: {date}    │\n"
                "└─────────────────────┘\n\n"
                "✨ *About our community:*\n"
                "• {member_count}+ Active Members\n"
                "• Daily Discussions\n"
                "• Helpful Environment\n\n"
                "💫 *Make sure to read rules!*",
        "female": "🌟 *Welcome to {group}, {name}!* 🌟\n\n"
                  "┌─────────────────────┐\n"
                  "│ 👤 Name: {name}      │\n"
                  "│ 🆔 Username: {username} │\n"
                  "│ 📅 Joined: {date}    │\n"
                  "└─────────────────────┘\n\n"
                  "✨ *About our community:*\n"
                  "• {member_count}+ Active Members\n"
                  "• Daily Discussions\n"
                  "• Helpful Environment\n\n"
                  "💫 *Make sure to read rules!*"
    },
    "elegant": {
        "male": "✧══════════════════════════✧\n"
                "         💎 *WELCOME* 💎\n"
                "✧══════════════════════════✧\n\n"
                "     *{name}* has joined!\n"
                "     ✨ @{username} ✨\n\n"
                "『 {group} 』\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📊 Members: {member_count}\n"
                "🎯 Type: Premium Community\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🌸 *Enjoy your stay!* 🌸",
        "female": "✧══════════════════════════✧\n"
                  "         💎 *WELCOME* 💎\n"
                  "✧══════════════════════════✧\n\n"
                  "     *{name}* has joined!\n"
                  "     ✨ @{username} ✨\n\n"
                  "『 {group} 』\n"
                  "━━━━━━━━━━━━━━━━━━━━━━\n"
                  "📊 Members: {member_count}\n"
                  "🎯 Type: Premium Community\n"
                  "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                  "🌸 *Enjoy your stay!* 🌸"
    },
    "premium": {
        "male": "🏆 ━━━━━━━━━━━━━━━━━━━━ 🏆\n"
                "         ✨ *PREMIUM WELCOME* ✨\n"
                "🏆 ━━━━━━━━━━━━━━━━━━━━ 🏆\n\n"
                "👑 *{name}* 👑\n"
                "┣━ 📝 Username: {username}\n"
                "┣━ 🏠 Group: {group}\n"
                "┣━ 👥 Members: {member_count}\n"
                "┗━ ⭐ Status: {gender_emoji} Verified\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎉 *We're excited to have you!* 🎉",
        "female": "🏆 ━━━━━━━━━━━━━━━━━━━━ 🏆\n"
                  "         ✨ *PREMIUM WELCOME* ✨\n"
                  "🏆 ━━━━━━━━━━━━━━━━━━━━ 🏆\n\n"
                  "👑 *{name}* 👑\n"
                  "┣━ 📝 Username: {username}\n"
                  "┣━ 🏠 Group: {group}\n"
                  "┣━ 👥 Members: {member_count}\n"
                  "┗━ ⭐ Status: {gender_emoji} Verified\n\n"
                  "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                  "🎉 *We're excited to have you!* 🎉"
    },
    "minimal": {
        "male": "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
                "      ✦ {name} ✦\n"
                "         joined\n"
                "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
                "┌ @{username} ┐\n"
                "│ {group} │\n"
                "└ {member_count} members ┘",
        "female": "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
                  "      ✦ {name} ✦\n"
                  "         joined\n"
                  "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
                  "┌ @{username} ┐\n"
                  "│ {group} │\n"
                  "└ {member_count} members ┘"
    }
}

# ============= MESSAGE RENDERER =============
async def render_welcome_message(template: str, user, group_name: str, group_id: int, member_count: int, gender: str) -> str:
    now = datetime.now()
    
    replacements = {
        "{name}": esc(user.full_name or user.first_name or "Member"),
        "{first_name}": esc(user.first_name or ""),
        "{last_name}": esc(user.last_name or ""),
        "{username}": esc(f"@{user.username}" if user.username else user.first_name or "member"),
        "{mention}": f"[{esc(user.first_name or 'User')}](tg://user?id={user.id})",
        "{group}": esc(group_name),
        "{group_id}": str(group_id),
        "{member_count}": str(member_count),
        "{date}": now.strftime("%d/%m/%Y"),
        "{time}": now.strftime("%H:%M:%S"),
        "{gender_emoji}": "👦" if gender == "male" else "👧",
        "{random_emoji}": ["🎉", "✨", "🌟", "💫", "🚀", "💪", "🔥", "⭐"][now.second % 8],
    }
    
    result = template
    for key, value in replacements.items():
        result = result.replace(key, value)
    
    return result

async def is_admin(update, context, group_id=None) -> bool:
    uid = update.effective_user.id
    cid = group_id or update.effective_chat.id
    try:
        m = await context.bot.get_chat_member(cid, uid)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except TelegramError:
        return False

async def safe_send(context, chat_id, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN):
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except TelegramError as e:
        clean = re.sub(r'[*_`\[\]()~>#+=|{}.!-]', '', text)
        try:
            await context.bot.send_message(chat_id=chat_id, text=clean, reply_markup=reply_markup)
        except:
            pass


# ============= COMMAND HANDLERS =============
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    n = esc(u.first_name or "Dost")
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Templates", callback_data="show_templates")],
        [InlineKeyboardButton("📖 Guide", callback_data="help_premium"),
         InlineKeyboardButton("⚙️ Setup", callback_data="setup_guide")]
    ])
    
    await safe_send(context, update.effective_chat.id,
        f"┌─────────────────────┐\n"
        f"│  🌹 *WELCOME BOT*  │\n"
        f"│     Premium v4.0    │\n"
        f"└─────────────────────┘\n\n"
        f"✨ *Namaste, {n}!* ✨\n\n"
        f"*Features:*\n"
        f"┣━ 🤖 AI Gender Detection\n"
        f"┣━ 🎨 Premium Templates\n"
        f"┣━ 📹 Media Support\n"
        f"┣━ 🔘 Inline Buttons\n"
        f"┗━ ⚡ Fast & Reliable\n\n"
        f"*Commands:*\n"
        f"┏━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃ /connect - Connect Group\n"
        f"┃ /template - Set Template\n"
        f"┃ /setvdi+msg-male\n"
        f"┃ /setvid+msg-female\n"
        f"┃ /setbuttons - Add Buttons\n"
        f"┃ /preview - Test Message\n"
        f"┃ /settings - View Settings\n"
        f"┗━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"💡 *Tip:* Use /template to start!",
        reply_markup=kb
    )

async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = esc(context.user_data.get("active_group_name", "—"))
        if gid:
            txt = f"✅ *Connected:* {gn}\n📁 ID: `{gid}`"
        else:
            txt = "⚠️ No group connected.\n_Run /connect in your group first._"
        await safe_send(context, chat.id, f"🔗 *Status*\n\n{txt}")
        return
    
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Admin only!")
    
    context.user_data["active_group_id"] = chat.id
    context.user_data["active_group_name"] = chat.title
    me = await context.bot.get_me()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🤖 Open DM", url=f"https://t.me/{me.username}")]])
    await safe_send(context, chat.id,
        f"✅ *{esc(chat.title)}* connected!\n📁 ID: `{chat.id}`\n\nConfigure in DM 👆",
        reply_markup=kb
    )

async def template_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set professional template"""
    chat = update.effective_chat
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Run /connect in your group first!")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Admin only!")
        gid = chat.id
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌟 Default", callback_data=f"template_default_{gid}"),
         InlineKeyboardButton("💎 Elegant", callback_data=f"template_elegant_{gid}")],
        [InlineKeyboardButton("🏆 Premium", callback_data=f"template_premium_{gid}"),
         InlineKeyboardButton("🎯 Minimal", callback_data=f"template_minimal_{gid}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])
    
    await safe_send(context, chat.id,
        "┌─────────────────────┐\n"
        "│  📚 *TEMPLATES*    │\n"
        "│   Rose Bot Style    │\n"
        "└─────────────────────┘\n\n"
        "*Choose a template:*\n\n"
        "🌟 *Default* - Clean & Professional\n"
        "💎 *Elegant* - Stylish Design\n"
        "🏆 *Premium* - Bold & Beautiful\n"
        "🎯 *Minimal* - Simple & Clean\n\n"
        "Preview available after selection!",
        reply_markup=kb
    )

async def setwelcome_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set custom welcome message"""
    chat = update.effective_chat
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = context.user_data.get("active_group_name", "Group")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Run /connect in your group first!")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Admin only!")
        gid, gn = chat.id, chat.title
    
    msg_text = " ".join(context.args) if context.args else ""
    
    if not msg_text and update.message.reply_to_message:
        msg_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    
    if not msg_text:
        await safe_send(context, chat.id,
            f"📝 *Set Welcome Message*\n\n"
            f"Group: *{esc(gn)}*\n\n"
            f"*Usage:* `/setwelcome Your message here`\n\n"
            f"*Variables:*\n"
            f"`{{name}}` - User's name\n"
            f"`{{username}}` - Username\n"
            f"`{{group}}` - Group name\n"
            f"`{{member_count}}` - Members count\n"
            f"`{{date}}` - Current date\n"
            f"`{{gender_emoji}}` - 👦/👧\n\n"
            f"*Example:*\n"
            f"`/setwelcome Welcome {{name}}! 🎉`")
        return
    
    await set_group_key(gid, "custom_welcome_msg", msg_text)
    await safe_send(context, chat.id, f"✅ *Welcome message saved!*\n\nPreview:\n{msg_text[:200]}")

async def setmedia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set welcome media (video/photo/GIF)"""
    chat = update.effective_chat
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Run /connect in your group first!")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Admin only!")
        gid = chat.id
    
    reply = update.message.reply_to_message
    if not reply:
        await safe_send(context, chat.id,
            "📹 *Set Welcome Media*\n\n"
            "*Usage:* Reply to a video/photo/GIF with:\n"
            "`/setmedia`\n\n"
            "Supported: Video, Photo, Animation (GIF)")
        return
    
    media_id = None
    media_type = None
    
    if reply.video:
        media_id = reply.video.file_id
        media_type = "video"
    elif reply.photo:
        media_id = reply.photo[-1].file_id
        media_type = "photo"
    elif reply.animation:
        media_id = reply.animation.file_id
        media_type = "gif"
    
    if media_id:
        await set_group_key(gid, "welcome_media_id", media_id)
        await set_group_key(gid, "welcome_media_type", media_type)
        await safe_send(context, chat.id, f"✅ *{media_type.upper()} saved as welcome media!*")
    else:
        await safe_send(context, chat.id, "❌ Reply to a video, photo, or GIF!")

async def setbuttons_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set inline buttons for welcome message"""
    chat = update.effective_chat
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Run /connect in your group first!")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Admin only!")
        gid = chat.id
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Rules", callback_data="show_rules"),
         InlineKeyboardButton("📢 Channel", url="https://t.me/your_channel")],
        [InlineKeyboardButton("💬 Support", url="https://t.me/your_support"),
         InlineKeyboardButton("🎮 Games", callback_data="show_games")]
    ])
    
    await set_group_key(gid, "welcome_buttons", json.dumps([
        [["📜 Rules", "callback", "show_rules"], ["📢 Channel", "url", "https://t.me/your_channel"]],
        [["💬 Support", "url", "https://t.me/your_support"], ["🎮 Games", "callback", "show_games"]]
    ]))
    
    await safe_send(context, chat.id,
        "✅ *Buttons configured!*\n\n"
        "*Current buttons:*\n"
        "• Rules (Inline)\n"
        "• Channel (Link)\n"
        "• Support (Link)\n"
        "• Games (Inline)\n\n"
        "Use /preview to see how it looks!")

async def preview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Preview welcome message"""
    chat = update.effective_chat
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = context.user_data.get("active_group_name", "Group")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Run /connect in your group first!")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Admin only!")
        gid, gn = chat.id, chat.title
    
    settings = await get_group_settings(gid)
    
    class DummyUser:
        def __init__(self):
            self.full_name = "Test User"
            self.first_name = "Test"
            self.last_name = "User"
            self.username = "testuser"
            self.id = 123456789
    
    dummy_user = DummyUser()
    member_count = 42
    
    # Get template or custom message
    template_name = settings.get("active_template", "default")
    custom_msg = settings.get("custom_welcome_msg", "")
    
    if custom_msg:
        male_msg = custom_msg
        female_msg = custom_msg
    else:
        template = PROFESSIONAL_TEMPLATES.get(template_name, PROFESSIONAL_TEMPLATES["default"])
        male_msg = template.get("male", template["default"])
        female_msg = template.get("female", template["default"])
    
    male_preview = await render_welcome_message(male_msg, dummy_user, gn, gid, member_count, "male")
    female_preview = await render_welcome_message(female_msg, dummy_user, gn, gid, member_count, "female")
    
    # Get buttons
    buttons_data = settings.get("welcome_buttons")
    reply_markup = None
    if buttons_data:
        try:
            buttons_json = json.loads(buttons_data) if isinstance(buttons_data, str) else buttons_data
            keyboard = []
            for row in buttons_json:
                keyboard_row = []
                for btn in row:
                    if btn[1] == "url":
                        keyboard_row.append(InlineKeyboardButton(btn[0], url=btn[2]))
                    elif btn[1] == "callback":
                        keyboard_row.append(InlineKeyboardButton(btn[0], callback_data=btn[2]))
                if keyboard_row:
                    keyboard.append(keyboard_row)
            if keyboard:
                reply_markup = InlineKeyboardMarkup(keyboard)
        except:
            pass
    
    # Send previews
    await safe_send(context, chat.id,
        f"┌─────────────────────┐\n"
        f"│  👦 *MALE PREVIEW*  │\n"
        f"└─────────────────────┘\n\n"
        f"{male_preview}",
        reply_markup=reply_markup
    )
    
    await asyncio.sleep(1)
    
    await safe_send(context, chat.id,
        f"┌─────────────────────┐\n"
        f"│  👧 *FEMALE PREVIEW* │\n"
        f"└─────────────────────┘\n\n"
        f"{female_preview}",
        reply_markup=reply_markup
    )

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current settings"""
    chat = update.effective_chat
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = context.user_data.get("active_group_name", "Group")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Run /connect in your group first!")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Admin only!")
        gid, gn = chat.id, chat.title
    
    s = await get_group_settings(gid)
    ok = lambda v: "✅" if v else "❌"
    
    template_name = s.get("active_template", "default")
    media_type = s.get("welcome_media_type", "none")
    has_buttons = "✅" if s.get("welcome_buttons") else "❌"
    
    await safe_send(context, chat.id,
        f"┌─────────────────────┐\n"
        f"│  ⚙️ *SETTINGS*      │\n"
        f"│   {esc(gn)}   │\n"
        f"└─────────────────────┘\n\n"
        f"*Configuration:*\n"
        f"┣━ Template: *{template_name.title()}*\n"
        f"┣━ Media: {media_type.upper()} {ok(s.get('welcome_media_id'))}\n"
        f"┣━ Custom Msg: {ok(s.get('custom_welcome_msg'))}\n"
        f"┣━ Buttons: {has_buttons}\n"
        f"┗━ AI Detection: {'✅ Active' if GROQ_API_KEY else '❌'}\n\n"
        f"*Commands:*\n"
        f"/template - Change template\n"
        f"/setwelcome - Custom message\n"
        f"/setmedia - Add video/photo\n"
        f"/setbuttons - Add buttons\n"
        f"/preview - Test message"
    )

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete all settings"""
    chat = update.effective_chat
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Run /connect first!")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Admin only!")
        gid = chat.id
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, Delete All", callback_data=f"delete_confirm_{gid}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])
    
    await safe_send(context, chat.id,
        "⚠️ *Delete All Settings?*\n\n"
        "This will remove:\n"
        "• Welcome message\n"
        "• Media\n"
        "• Buttons\n"
        "• Template\n\n"
        "This action cannot be undone!",
        reply_markup=kb
    )


# ============= WELCOME HANDLER =============
async def send_welcome(context, chat_id, user, gender, group_name, method):
    s = await get_group_settings(chat_id)
    
    # Get template or custom message
    template_name = s.get("active_template", "default")
    custom_msg = s.get("custom_welcome_msg", "")
    
    if custom_msg:
        welcome_text = custom_msg
    else:
        template = PROFESSIONAL_TEMPLATES.get(template_name, PROFESSIONAL_TEMPLATES["default"])
        welcome_text = template.get(gender, template["default"])
    
    # Get member count
    try:
        member_count = await context.bot.get_chat_member_count(chat_id)
    except:
        member_count = 0
    
    # Render message
    final = await render_welcome_message(welcome_text, user, group_name, chat_id, member_count, gender)
    
    # Add method badge
    method_badge = {
        "groq_ai": "🤖 AI Detected",
        "name_database": "📚 Database",
        "cache": "💾 Cached",
        "user_selected": "✅ Self-selected"
    }.get(method, "")
    
    if method_badge:
        final += f"\n\n┌─[ {method_badge} ]─┐"
    
    # Get buttons
    buttons_data = s.get("welcome_buttons")
    reply_markup = None
    if buttons_data:
        try:
            buttons_json = json.loads(buttons_data) if isinstance(buttons_data, str) else buttons_data
            keyboard = []
            for row in buttons_json:
                keyboard_row = []
                for btn in row:
                    if btn[1] == "url":
                        keyboard_row.append(InlineKeyboardButton(btn[0], url=btn[2]))
                    elif btn[1] == "callback":
                        keyboard_row.append(InlineKeyboardButton(btn[0], callback_data=btn[2]))
                if keyboard_row:
                    keyboard.append(keyboard_row)
            if keyboard:
                reply_markup = InlineKeyboardMarkup(keyboard)
        except:
            pass
    
    # Get media
    media_id = s.get("welcome_media_id")
    media_type = s.get("welcome_media_type")
    
    # Send with media if available
    if media_id and media_type == "video":
        try:
            await context.bot.send_video(
                chat_id=chat_id, video=media_id,
                caption=final, parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
        except:
            pass
    elif media_id and media_type == "photo":
        try:
            await context.bot.send_photo(
                chat_id=chat_id, photo=media_id,
                caption=final, parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
        except:
            pass
    elif media_id and media_type == "gif":
        try:
            await context.bot.send_animation(
                chat_id=chat_id, animation=media_id,
                caption=final, parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
        except:
            pass
    
    # Send text only
    await safe_send(context, chat_id, final, reply_markup=reply_markup)

async def greet_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r = update.chat_member
    old, new = r.old_chat_member.status, r.new_chat_member.status
    
    if not (new in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)
            and old not in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)):
        return
    
    user = r.new_chat_member.user
    chat = update.effective_chat
    
    if user.is_bot:
        return
    
    gn = chat.title or "Group"
    
    logger.info(f"👤 New member: {user.full_name} in {gn}")
    
    # Detect gender
    gender, confidence, method = await detect_gender_master(
        user_id=user.id,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        username=user.username or ""
    )
    
    if gender != "unknown" and confidence > 0.7:
        await send_welcome(context, chat.id, user, gender, gn, method)
    else:
        # Ask user to select
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("👦 I'm Male", callback_data=f"gender_male_{user.id}_{chat.id}"),
            InlineKeyboardButton("👧 I'm Female", callback_data=f"gender_female_{user.id}_{chat.id}"),
        ]])
        await safe_send(context, chat.id,
            f"┌─────────────────────┐\n"
            f"│  👋 *WELCOME!* 👋   │\n"
            f"└─────────────────────┘\n\n"
            f"*{esc(user.first_name or 'User')}*, please select your gender for personalized welcome 👇",
            reply_markup=kb
        )

async def gender_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    d = q.data
    clicker = update.effective_user.id
    parts = d.split("_")
    
    if len(parts) < 4:
        return
    
    gender, uid, cid = parts[1], int(parts[2]), int(parts[3])
    
    if clicker != uid:
        return await q.answer("❌ Not for you!", show_alert=True)
    
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


# ============= CALLBACK HANDLER =============
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    
    if data == "cancel":
        await q.message.delete()
        return
    
    if data == "show_templates":
        await template_cmd(update, context)
        await q.message.delete()
        return
    
    if data == "help_premium":
        await safe_send(context, q.message.chat.id,
            "┌─────────────────────┐\n"
            "│  📖 *PREMIUM GUIDE*  │\n"
            "└─────────────────────┘\n\n"
            "*Variables:*\n"
            "┣━ {name} - Full name\n"
            "┣━ {username} - Username\n"
            "┣━ {group} - Group name\n"
            "┣━ {member_count} - Members\n"
            "┣━ {date} - Current date\n"
            "┗━ {gender_emoji} - 👦/👧\n\n"
            "*Commands:*\n"
            "┣━ /template - Set template\n"
            "┣━ /setwelcome - Custom\n"
            "┣━ /setmedia - Add media\n"
            "┣━ /setbuttons - Add buttons\n"
            "┗━ /preview - Test\n\n"
            "✨ *Pro:* Use Markdown for formatting!")
        await q.message.delete()
        return
    
    if data == "setup_guide":
        await safe_send(context, q.message.chat.id,
            "┌─────────────────────┐\n"
            "│  ⚙️ *SETUP GUIDE*    │\n"
            "└─────────────────────┘\n\n"
            "*Step 1:* Add bot to group as admin\n"
            "*Step 2:* Run `/connect` in group\n"
            "*Step 3:* Come back to DM\n"
            "*Step 4:* Run `/template` to choose design\n"
            "*Step 5:* Use `/preview` to test\n\n"
            "🎉 *Done!* New members will get welcome messages!")
        await q.message.delete()
        return
    
    if data.startswith("template_"):
        parts = data.split("_")
        if len(parts) >= 3:
            template_name = parts[1]
            gid = int(parts[2])
            await set_group_key(gid, "active_template", template_name)
            await q.edit_message_text(f"✅ *{template_name.title()} template applied!*\n\nUse `/preview` to see how it looks.")
        return
    
    if data.startswith("delete_confirm_"):
        gid = int(data.split("_")[2])
        await delete_group_key(gid)
        await q.edit_message_text("✅ *All settings deleted!*")
        return

# ============= MAIN =============
def main():
    if not BOT_TOKEN:
        print("\n" + "=" * 50)
        print("  ❌ BOT_TOKEN not set!")
        print("=" * 50 + "\n")
        return
    
    Path(SETTINGS_FILE).write_text("{}") if not Path(SETTINGS_FILE).exists() else None
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("connect", connect_cmd))
    app.add_handler(CommandHandler("template", template_cmd))
    app.add_handler(CommandHandler("setwelcome", setwelcome_cmd))
    app.add_handler(CommandHandler("setmedia", setmedia_cmd))
    app.add_handler(CommandHandler("setbuttons", setbuttons_cmd))
    app.add_handler(CommandHandler("preview", preview_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    
    # Old commands for backward compatibility
    app.add_handler(CommandHandler("setwelcome_male", setwelcome_cmd))
    app.add_handler(CommandHandler("setwelcome_female", setwelcome_cmd))
    app.add_handler(CommandHandler("showset", settings_cmd))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(callback_handler, pattern="^(show_templates|help_premium|setup_guide|template_|cancel|delete_confirm_)"))
    app.add_handler(CallbackQueryHandler(gender_cb, pattern=r"^gender_"))
    
    # Member join
    app.add_handler(ChatMemberHandler(greet_member, ChatMemberHandler.CHAT_MEMBER))
    
    # Error handler
    async def err_handler(update, context):
        logger.error(f"Error: {context.error}")
    app.add_error_handler(err_handler)
    
    logger.info("🌹 PREMIUM WELCOME BOT v4.0 - ROSE STYLE running!")
    print("\n" + "=" * 50)
    print("  🌹 BOT IS RUNNING - ROSE STYLE!")
    print("  ✨ Premium Features:")
    print("     • Professional Templates")
    print("     • Media Support")
    print("     • Inline Buttons")
    print("     • AI Gender Detection")
    print("=" * 50 + "\n")
    
    app.run_polling(allowed_updates=["message", "chat_member", "callback_query"])

if __name__ == "__main__":
    main()
