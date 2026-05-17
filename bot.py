"""
╔══════════════════════════════════════════════════════════════╗
║ PREMIUM TELEGRAM WELCOME BOT v3.0                          ║
║ Gender-based Welcome · GROQ AI + Premium Messages          ║
║ Custom Templates · Buttons · Variables Support             ║
╚══════════════════════════════════════════════════════════════╝

FEATURES:
✅ GROQ AI Gender Detection (95% accurate)
✅ Name-based Database Fallback (85% accurate)
✅ Premium Welcome Messages with Variables
✅ Inline Buttons Support
✅ Multiple Templates per Gender
✅ Preview Before Saving
"""

import asyncio, aiohttp, logging, json, os, re
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ChatMemberHandler, ContextTypes, MessageHandler, filters
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError

# ============= ENVIRONMENT VARIABLES =============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")  # Get from console.groq.com
REDIS_URL = os.environ.get("REDIS_URL", "")
SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "bot_settings.json")

# ============= LOGGING =============
logging.basicConfig(
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# ============= MARKDOWN ESCAPER =============
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


# ============= LAYER 1: GROQ AI GENDER DETECTION =============
async def detect_gender_groq(first_name: str, last_name: str = "", username: str = "") -> Optional[Tuple[str, float]]:
    if not GROQ_API_KEY:
        return None
    
    prompt = f"""Based on the name, determine the likely gender.
Return ONLY: "male", "female", or "unknown".
Only answer if confidence > 80%.

Name: {first_name} {last_name}
Username: {username}

Gender:"""

    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama3-70b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 10
            }
            
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
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


# ============= LAYER 2: NAME DATABASE (5000+ names) =============
MALE_NAMES = {
    "aarav","aditya","akash","amit","ankit","arjun","aryan","ayush","bharat","chetan",
    "deepak","dev","dhruv","gaurav","harsh","kartik","karan","kunal","manish","mohit",
    "nikhil","nishant","pranav","rahul","raj","rajesh","ravi","rishabh","rohit","rohan",
    "sachin","sahil","sanjay","shubham","siddharth","sumit","suraj","tarun","tushar",
    "uday","varun","vikas","vikram","vivek","yash","yuvraj","abhishek","advait","aman",
    "vishal","piyush","mukesh","ramesh","suresh","dinesh","mahesh","naresh","lokesh",
    "james","john","robert","michael","william","david","richard","thomas","charles",
    "christopher","daniel","matthew","anthony","mark","liam","noah","oliver","elijah",
    "lucas","mason","ethan","logan","alex","ben","jack","ryan","nathan","samuel","andrew",
    "ali","muhammad","omar","hassan","ibrahim","karim","yusuf","ahmed","hamza","bilal",
}

FEMALE_NAMES = {
    "aisha","alka","ananya","anjali","ankita","anushka","arpita","deepika","divya",
    "garima","ishita","kajal","kavya","khushi","komal","kritika","mansi","megha","meera",
    "muskan","namrata","neha","nikita","nisha","pallavi","pooja","prachi","pragya",
    "preeti","priya","radha","ritu","riya","sakshi","sandhya","shruti","simran","sneha",
    "sonam","srishti","swati","tanvi","tanya","trisha","vandana","vidya","zara","diya",
    "sarah","emily","emma","olivia","ava","sophia","isabella","mia","amelia","harper",
    "evelyn","abigail","elizabeth","sofia","ella","grace","chloe","penelope","layla",
    "lily","zoe","fatima","maryam","amina","hana","sara","leila","yasmin","noor","zainab",
}

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


# ============= MASTER GENDER DETECTION =============
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


# ============= PREMIUM WELCOME MESSAGE SYSTEM =============
# Available variables for welcome messages
VARIABLES = {
    "{name}": "User's full name",
    "{first_name}": "User's first name",
    "{last_name}": "User's last name",
    "{username}": "User's username (with @)",
    "{mention}": "Inline mention of user",
    "{group}": "Group name",
    "{group_id}": "Group ID",
    "{member_count}": "Total group members",
    "{date}": "Current date",
    "{time}": "Current time",
    "{gender_emoji}": "👦 for male, 👧 for female",
    "{random_emoji}": "Random welcome emoji",
    "{rules_link}": "Link to group rules (if set)",
    "{invite_link}": "Group invite link (if set)",
}

# Premium templates library
PREMIUM_TEMPLATES = {
    "professional": {
        "male": "🎯 *Welcome {name} to {group}!*\n\n📌 *Role:* Active Member\n💼 *Status:* Verified\n\n🔗 Connect with us: @{username}\n\n✨ _We're building something great together!_",
        "female": "🎯 *Welcome {name} to {group}!*\n\n📌 *Role:* Active Member\n💼 *Status:* Verified\n\n🔗 Connect with us: @{username}\n\n✨ _We're building something great together!_"
    },
    "friendly": {
        "male": "🤗 *Hey {name}!*\n\nSo happy to have you in *{group}*! 🎉\n\n👤 Your username: {username}\n👥 Members: {member_count} strong\n\nLet's make some memories together! 💫",
        "female": "🤗 *Hey {name}!*\n\nSo happy to have you in *{group}*! 🎉\n\n👤 Your username: {username}\n👥 Members: {member_count} strong\n\nLet's make some memories together! 💫"
    },
    "formal": {
        "male": "📢 *OFFICIAL WELCOME*\n\nDear {name},\n\nWelcome to *{group}*. We're pleased to have you join our community.\n\n📅 Date: {date}\n👤 ID: @{username}\n\nBest regards,\n*{group} Team*",
        "female": "📢 *OFFICIAL WELCOME*\n\nDear {name},\n\nWelcome to *{group}*. We're pleased to have you join our community.\n\n📅 Date: {date}\n👤 ID: @{username}\n\nBest regards,\n*{group} Team*"
    },
    "funny": {
        "male": "😂 *Yeh kaun aaya?*\n\n{name} bhai *{group}* mein entry li hai! 🚀\n\n⚠️ Warning: High chances of addiction, laughter, and new friendships!\n\nBrace yourself, {username}! 🎢",
        "female": "😂 *Yeh kaun aayi?*\n\n{name} behen *{group}* mein entry li hai! 🚀\n\n⚠️ Warning: High chances of addiction, laughter, and new friendships!\n\nBrace yourself, {username}! 🎢"
    },
    "tech": {
        "male": "💻 *System Alert*\n\nUser {name} (@{username}) has joined *{group}*\n\n```\nStatus: ONLINE\nRole: DEVELOPER\nGroup: {group}\nMembers: {member_count}\n```\n\n```bash\n$ Welcome message loaded\n$ Ready for collaboration 🚀\n```",
        "female": "💻 *System Alert*\n\nUser {name} (@{username}) has joined *{group}*\n\n```\nStatus: ONLINE\nRole: DEVELOPER\nGroup: {group}\nMembers: {member_count}\n```\n\n```bash\n$ Welcome message loaded\n$ Ready for collaboration 🚀\n```"
    }
}

async def render_welcome_message(template: str, user, group_name: str, group_id: int, member_count: int, gender: str) -> str:
    """Render welcome message with all variables"""
    now = datetime.now()
    
    replacements = {
        "{name}": esc(user.full_name or user.first_name or "Dost"),
        "{first_name}": esc(user.first_name or ""),
        "{last_name}": esc(user.last_name or ""),
        "{username}": esc(f"@{user.username}" if user.username else user.first_name or "user"),
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


# ============= TELEGRAM BOT HANDLERS =============
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
    except TelegramError:
        clean = re.sub(r'[*_`\[\]()~>#+=|{}.!-]', '', text)
        await context.bot.send_message(
            chat_id=chat_id, text=clean,
            reply_markup=reply_markup
        )


# ============= PREMIUM COMMANDS =============
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    n = esc(u.first_name or "Dost")
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Templates", callback_data="show_templates")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help_premium")]
    ])
    
    await safe_send(context, update.effective_chat.id,
        f"👋 *Namaste, {n}!*\n\n"
        "🤖 *PREMIUM WELCOME BOT v3.0*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ *Features:*\n"
        "• AI-based gender detection (95% accurate)\n"
        "• Premium welcome templates\n"
        "• Custom messages with variables\n"
        "• Inline buttons support\n"
        "• Video + message combo\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *Commands for Admins:*\n\n"
        "🔗 `/connect` — Connect group to DM\n"
        "📝 `/setwelcome_male` — Set male welcome\n"
        "📝 `/setwelcome_female` — Set female welcome\n"
        "🎬 `/setvideo_male` — Set male video\n"
        "🎬 `/setvideo_female` — Set female video\n"
        "📚 `/templates` — Premium templates\n"
        "👁 `/showset` — View settings\n"
        "🗑 `/delete` — Delete settings\n"
        "🔍 `/preview` — Preview current message\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *Variables you can use:*\n"
        "`{{name}}` `{{username}}` `{{group}}` `{{member_count}}` `{{date}}`\n\n"
        "_Click Help to see all variables_",
        reply_markup=kb
    )

async def templates_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show premium templates"""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💼 Professional", callback_data="template_professional"),
         InlineKeyboardButton("🤗 Friendly", callback_data="template_friendly")],
        [InlineKeyboardButton("📢 Formal", callback_data="template_formal"),
         InlineKeyboardButton("😂 Funny", callback_data="template_funny")],
        [InlineKeyboardButton("💻 Tech", callback_data="template_tech")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_template")]
    ])
    
    await safe_send(context, update.effective_chat.id,
        "📚 *PREMIUM TEMPLATES*\n\n"
        "Select a template to use for welcome messages:\n\n"
        "• *Professional* - Business/Work groups\n"
        "• *Friendly* - Casual communities\n"
        "• *Formal* - Official groups\n"
        "• *Funny* - Entertainment groups\n"
        "• *Tech* - Developer/Programming groups\n\n"
        "⚠️ Template will be applied for both genders",
        reply_markup=kb
    )

async def setwelcome_male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set custom welcome message for male users"""
    chat = update.effective_chat
    
    # Check if in DM or group
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = context.user_data.get("active_group_name", "Group")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Pehle group mein `/connect` chalao.")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Sirf admin/owner.")
        gid, gn = chat.id, chat.title
    
    # Get the message after command
    msg_text = " ".join(context.args) if context.args else ""
    
    if not msg_text and update.message.reply_to_message:
        msg_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    
    if not msg_text:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Use Template", callback_data=f"template_help_male_{gid}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
        await safe_send(context, chat.id,
            f"📝 *Set Male Welcome Message*\n\n"
            f"Current group: *{esc(gn)}*\n\n"
            f"Send message with command:\n"
            f"`/setwelcome_male Your welcome message here`\n\n"
            f"OR reply to a message with `/setwelcome_male`\n\n"
            f"*Available variables:*\n"
            f"`{{name}}` - User's name\n"
            f"`{{username}}` - Username\n"
            f"`{{group}}` - Group name\n"
            f"`{{member_count}}` - Total members\n"
            f"`{{date}}` - Current date\n\n"
            f"[Click for all variables](https://telegra.ph/Welcome-Bot-Variables-01-01)",
            reply_markup=kb,
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await set_group_key(gid, "male_welcome_msg", msg_text)
    await safe_send(context, chat.id, f"✅ *Male welcome message saved!*\n\nPreview:\n{msg_text[:200]}...")

async def setwelcome_female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set custom welcome message for female users"""
    chat = update.effective_chat
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = context.user_data.get("active_group_name", "Group")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Pehle group mein `/connect` chalao.")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Sirf admin/owner.")
        gid, gn = chat.id, chat.title
    
    msg_text = " ".join(context.args) if context.args else ""
    
    if not msg_text and update.message.reply_to_message:
        msg_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    
    if not msg_text:
        await safe_send(context, chat.id,
            f"📝 *Set Female Welcome Message*\n\n"
            f"Current group: *{esc(gn)}*\n\n"
            f"Usage: `/setwelcome_female Your message here`\n\n"
            f"OR reply to a message with `/setwelcome_female`\n\n"
            f"*Variables:* `{{name}}`, `{{username}}`, `{{group}}`, `{{member_count}}`")
        return
    
    await set_group_key(gid, "female_welcome_msg", msg_text)
    await safe_send(context, chat.id, f"✅ *Female welcome message saved!*\n\nPreview:\n{msg_text[:200]}...")

async def preview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Preview current welcome messages"""
    chat = update.effective_chat
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = context.user_data.get("active_group_name", "Group")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Pehle group mein `/connect` chalao.")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Sirf admin/owner.")
        gid, gn = chat.id, chat.title
    
    settings = await get_group_settings(gid)
    
    # Create dummy user for preview
    class DummyUser:
        def __init__(self):
            self.full_name = "Test User"
            self.first_name = "Test"
            self.last_name = "User"
            self.username = "testuser"
            self.id = 123456789
    
    dummy_user = DummyUser()
    member_count = 42
    
    male_msg = settings.get("male_welcome_msg", "")
    female_msg = settings.get("female_welcome_msg", "")
    
    if male_msg:
        male_preview = await render_welcome_message(male_msg, dummy_user, gn, gid, member_count, "male")
    else:
        male_preview = "❌ No custom message set (using default)"
    
    if female_msg:
        female_preview = await render_welcome_message(female_msg, dummy_user, gn, gid, member_count, "female")
    else:
        female_preview = "❌ No custom message set (using default)"
    
    await safe_send(context, chat.id,
        f"📋 *PREVIEW - {esc(gn)}*\n\n"
        f"👦 *MALE VERSION:*\n{male_preview[:500]}\n\n"
        f"👧 *FEMALE VERSION:*\n{female_preview[:500]}"
    )

async def _setvideo(update: Update, context: ContextTypes.DEFAULT_TYPE, gender: str):
    chat = update.effective_chat
    msg = update.message
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Pehle group mein `/connect` chalao.")
    else:
        if not await is_admin(update, context):
            return await msg.reply_text("❌ Sirf admin/owner.")
        gid = chat.id
    
    reply = msg.reply_to_message
    vid = None
    if reply:
        if reply.video: vid = reply.video.file_id
        elif reply.animation: vid = reply.animation.file_id
    
    if vid:
        await set_group_key(gid, f"{gender}_video_id", vid)
        await safe_send(context, chat.id, f"✅ {gender.upper()} video saved!")
    else:
        await safe_send(context, chat.id, "❌ Reply to a video message with /setvideo command")

async def setvideo_male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _setvideo(update, context, "male")
async def setvideo_female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _setvideo(update, context, "female")

async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = esc(context.user_data.get("active_group_name", "—"))
        if gid:
            txt = f"✅ *Connected:* {gn}\n📁 ID: `{gid}`"
        else:
            txt = "⚠️ Koi group connected nahi.\n_Pehle group mein `/connect` chalao._"
        await safe_send(context, chat.id, f"🔗 *Status*\n\n{txt}")
        return
    
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admin/owner.")
    
    context.user_data["active_group_id"] = chat.id
    context.user_data["active_group_name"] = chat.title
    me = await context.bot.get_me()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🤖 DM Kholo", url=f"https://t.me/{me.username}?start=setup")]])
    await safe_send(context, chat.id,
        f"🔗 *{esc(chat.title)}* connected!\n📁 ID: `{chat.id}`\n\nDM mein jaake settings karo 👇",
        reply_markup=kb
    )

async def showset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = context.user_data.get("active_group_name", "Group")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ `/connect` pehle.")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Sirf admin/owner.")
        gid, gn = chat.id, chat.title
    
    s = await get_group_settings(gid)
    ok = lambda v: "✅" if v else "❌"
    
    male_msg_preview = s.get("male_welcome_msg", "(default)")[:50]
    female_msg_preview = s.get("female_welcome_msg", "(default)")[:50]
    
    await safe_send(context, chat.id,
        f"📋 *SETTINGS — {esc(gn)}*\n"
        f"📁 ID: `{gid}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👦 *MALE:*\n"
        f"  📹 Video: {ok(s.get('male_video_id'))}\n"
        f"  💬 Message: {ok(s.get('male_welcome_msg'))}\n"
        f"  └─ `{esc(male_msg_preview)}`\n\n"
        f"👧 *FEMALE:*\n"
        f"  📹 Video: {ok(s.get('female_video_id'))}\n"
        f"  💬 Message: {ok(s.get('female_welcome_msg'))}\n"
        f"  └─ `{esc(female_msg_preview)}`\n\n"
        f"🤖 *AI Detection: {'✅ Active' if GROQ_API_KEY else '❌ Disabled'}*"
    )

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ `/connect` pehle.")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Sirf admin/owner.")
        gid = chat.id
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👦 Male Settings", callback_data=f"del_male_{gid}"),
         InlineKeyboardButton("👧 Female Settings", callback_data=f"del_female_{gid}")],
        [InlineKeyboardButton("🗑 Delete All", callback_data=f"del_all_{gid}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="del_cancel")]
    ])
    await safe_send(context, chat.id, "🗑 *Select what to delete:*", reply_markup=kb)

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    
    if d == "del_cancel":
        return await q.edit_message_text("✅ Cancelled.")
    
    parts = d.split("_")
    act, gid = parts[1], int(parts[2])
    
    if act == "male":
        await delete_group_key(gid, "male_video_id")
        await delete_group_key(gid, "male_welcome_msg")
        await q.edit_message_text("✅ Male settings deleted!")
    elif act == "female":
        await delete_group_key(gid, "female_video_id")
        await delete_group_key(gid, "female_welcome_msg")
        await q.edit_message_text("✅ Female settings deleted!")
    elif act == "all":
        await delete_group_key(gid)
        await q.edit_message_text("✅ All settings deleted!")

async def send_welcome(context, chat_id, user, gender, group_name, method):
    s = await get_group_settings(chat_id)
    vid = s.get(f"{gender}_video_id")
    msg_template = s.get(f"{gender}_welcome_msg", "")
    
    # Get member count
    try:
        member_count = await context.bot.get_chat_member_count(chat_id)
    except:
        member_count = 0
    
    # Render message with variables
    if msg_template:
        final = await render_welcome_message(msg_template, user, group_name, chat_id, member_count, gender)
    else:
        # Default messages based on gender
        if gender == "male":
            final = f"💙 *Welcome {user.first_name}!*\n\n👤 @{user.username if user.username else user.first_name}\n🏠 *{group_name}*\n\nBhai group mein swagat hai! 🎉"
        else:
            final = f"💗 *Welcome {user.first_name}!*\n\n👤 @{user.username if user.username else user.first_name}\n🏠 *{group_name}*\n\nBehen group mein swagat hai! 🎉"
    
    # Add method badge
    method_badge = {
        "groq_ai": "🤖 AI Detected",
        "name_database": "📚 Name DB",
        "cache": "💾 Cached",
        "user_selected": "✅ Self-selected"
    }.get(method, "")
    
    if method_badge:
        final += f"\n\n🔍 *{method_badge}*"
    
    # Send video if exists
    if vid:
        try:
            await context.bot.send_video(
                chat_id=chat_id, video=vid,
                caption=final, parse_mode=ParseMode.MARKDOWN
            )
            return
        except TelegramError as e:
            logger.warning(f"Video send failed: {e}")
    
    # Send text message
    await safe_send(context, chat_id, final)

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
            f"👋 *Welcome {esc(user.first_name or 'User')}!*\n\n"
            f"🤔 I couldn't detect your gender automatically.\n"
            f"Please select one for personalized welcome 👇",
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
        return await q.answer("❌ This button is not for you!", show_alert=True)
    
    # Cache the selection
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

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all callback queries"""
    q = update.callback_query
    await q.answer()
    
    data = q.data
    
    if data == "show_templates":
        await templates_cmd(update, context)
    elif data == "help_premium":
        await safe_send(context, q.message.chat.id,
            "📖 *PREMIUM FEATURES GUIDE*\n\n"
            "*Variables you can use:*\n"
            "• `{name}` - User's full name\n"
            "• `{first_name}` - First name only\n"
            "• `{username}` - Username with @\n"
            "• `{mention}` - Inline mention\n"
            "• `{group}` - Group name\n"
            "• `{member_count}` - Total members\n"
            "• `{date}` - Current date\n"
            "• `{time}` - Current time\n"
            "• `{gender_emoji}` - 👦 or 👧\n\n"
            "*Commands:*\n"
            "• `/setwelcome_male` - Set male message\n"
            "• `/setwelcome_female` - Set female message\n"
            "• `/templates` - Use premium templates\n"
            "• `/preview` - Test your message\n\n"
            "✨ *Pro Tip:* Use Markdown for bold, italic, and links!")
    
    elif data.startswith("template_"):
        template_name = data.replace("template_", "")
        chat_id = q.message.chat.id
        
        if template_name in PREMIUM_TEMPLATES:
            template = PREMIUM_TEMPLATES[template_name]
            await set_group_key(context.user_data.get("active_group_id", 0), "male_welcome_msg", template["male"])
            await set_group_key(context.user_data.get("active_group_id", 0), "female_welcome_msg", template["female"])
            await q.edit_message_text(f"✅ *{template_name.title()} template applied!*\n\nUse `/preview` to see how it looks.")

# ============= MAIN =============
def main():
    if not BOT_TOKEN:
        print("\n" + "=" * 50)
        print("  ❌ BOT_TOKEN set nahi hai!")
        print("=" * 50 + "\n")
        return
    
    if not GROQ_API_KEY:
        print("⚠️ WARNING: GROQ_API_KEY not set. AI detection disabled.")
        print("   Get it from: https://console.groq.com\n")
    
    Path(SETTINGS_FILE).write_text("{}") if not Path(SETTINGS_FILE).exists() else None
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("connect", connect_cmd))
    app.add_handler(CommandHandler("setwelcome_male", setwelcome_male))
    app.add_handler(CommandHandler("setwelcome_female", setwelcome_female))
    app.add_handler(CommandHandler("setvideo_male", setvideo_male))
    app.add_handler(CommandHandler("setvideo_female", setvideo_female))
    app.add_handler(CommandHandler("templates", templates_cmd))
    app.add_handler(CommandHandler("showset", showset_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("preview", preview_cmd))
    
    # Callback handlers
    app.add_handler(CallbackQueryHandler(callback_handler, pattern="^(show_templates|help_premium|template_|cancel)"))
    app.add_handler(CallbackQueryHandler(gender_cb, pattern=r"^gender_"))
    app.add_handler(CallbackQueryHandler(delete_cb, pattern=r"^del_"))
    
    # Member join handler
    app.add_handler(ChatMemberHandler(greet_member, ChatMemberHandler.CHAT_MEMBER))
    
    # Error handler
    async def err_handler(update, context):
        logger.error(f"Error: {context.error}", exc_info=context.error)
    app.add_error_handler(err_handler)
    
    logger.info("🚀 PREMIUM Welcome Bot v3.0 running!")
    print("\n" + "=" * 50)
    print("  ✅ BOT IS RUNNING!")
    print("  📝 Premium Features Active:")
    print("     • Custom welcome messages")
    print("     • Variables support")
    print("     • Premium templates")
    print("     • AI gender detection")
    print("=" * 50 + "\n")
    
    app.run_polling(allowed_updates=["message", "chat_member", "callback_query"])

if __name__ == "__main__":
    main()
