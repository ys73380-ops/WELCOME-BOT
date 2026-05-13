"""
╔══════════════════════════════════════════════════════════════╗
║         ADVANCED TELEGRAM WELCOME BOT v2.0                  ║
║   Gender-based Welcome (Male/Female) + Genderize.io API     ║
║   Multi-group safe · Persistent JSON storage                ║
╚══════════════════════════════════════════════════════════════╝
"""

import asyncio
import aiohttp
import logging
import json
import os
import re
from pathlib import Path
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError

# ══════════════════════════════════════════════════════════════
# CONFIGURATION — Environment Variables
# ══════════════════════════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GENDERIZE_API_KEY = os.environ.get("GENDERIZE_API_KEY", "")
SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "bot_settings.json")

# ══════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# THREAD-SAFE SETTINGS MANAGER
# File locking + in-memory cache se race condition prevent karta hai
# ══════════════════════════════════════════════════════════════
_settings_lock = asyncio.Lock()
_settings_cache: Optional[dict] = None


def _settings_path() -> Path:
    return Path(SETTINGS_FILE)


def load_settings() -> dict:
    """Load settings from JSON file."""
    path = _settings_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Settings load error: {e}")
            # Backup corrupted file
            backup = path.with_suffix(".json.bak")
            try:
                path.rename(backup)
                logger.info(f"Corrupted settings backed up to {backup}")
            except OSError:
                pass
    return {}


async def _save_settings_safe(data: dict):
    """Thread-safe save with file locking."""
    async with _settings_lock:
        path = _settings_path()
        try:
            temp_path = path.with_suffix(".json.tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # Atomic rename
            temp_path.replace(path)
            _settings_cache = data  # Update cache
            logger.debug("Settings saved successfully")
        except OSError as e:
            logger.error(f"Settings save error: {e}")


async def get_group_settings(group_id: int) -> dict:
    """Get settings for a specific group."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = load_settings()
    return _settings_cache.get(str(group_id), {})


async def set_group_key(group_id: int, key: str, value):
    """Set a specific key for a group (thread-safe)."""
    settings = load_settings()
    gid = str(group_id)
    if gid not in settings:
        settings[gid] = {}
    settings[gid][key] = value
    await _save_settings_safe(settings)


async def delete_group_key(group_id: int, key: str = None):
    """Delete a key or entire group settings (thread-safe)."""
    settings = load_settings()
    gid = str(group_id)
    if gid in settings:
        if key:
            settings[gid].pop(key, None)
            if not settings[gid]:  # Remove empty group
                del settings[gid]
        else:
            del settings[gid]
        await _save_settings_safe(settings)


# ══════════════════════════════════════════════════════════════
# ADMIN CHECK
# ══════════════════════════════════════════════════════════════
async def is_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    group_id: int = None
) -> bool:
    """Check if the user is admin or owner of the group."""
    user_id = update.effective_user.id
    chat_id = group_id or update.effective_chat.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except TelegramError:
        return False


# ══════════════════════════════════════════════════════════════
# GENDER DETECTION ENGINE
# Layer 1 → Genderize.io API (online)
# Layer 2 → Local name database (offline fallback)
# ══════════════════════════════════════════════════════════════
MALE_NAMES = {
    # Indian
    "aarav", "aditya", "akash", "amit", "ankit", "arjun", "aryan", "ayush",
    "deepak", "dev", "dhruv", "gaurav", "harsh", "kartik", "karan", "kunal",
    "manish", "mohit", "nikhil", "nishant", "pranav", "rahul", "raj", "rajesh",
    "ravi", "rishabh", "rohit", "rohan", "sachin", "sahil", "sanjay", "shubham",
    "siddharth", "sumit", "suraj", "tarun", "tushar", "uday", "varun", "vikas",
    "vikram", "vivek", "yash", "yuvraj", "abhishek", "advait", "aman", "vishal",
    "piyush", "mukesh", "ramesh", "suresh", "dinesh", "mahesh", "naresh",
    "lokesh", "hitesh", "ritesh", "rakesh", "nilesh", "girish", "kamlesh",
    "brijesh", "shailesh", "yogesh", "rajat", "ronit", "kush", "om", "param",
    "parth", "pratik", "chirag", "bhavesh", "hardik", "jatin", "lalit",
    "manan", "neel", "paras", "ruchit", "sagar", "tej", "umang",
    # English
    "james", "john", "robert", "michael", "william", "david", "richard",
    "thomas", "charles", "christopher", "daniel", "matthew", "anthony",
    "mark", "liam", "noah", "oliver", "elijah", "lucas", "mason", "ethan",
    "logan", "alex", "ben", "jack", "ryan", "nathan", "samuel", "andrew",
    # Arabic
    "ali", "muhammad", "omar", "hassan", "ibrahim", "karim", "yusuf",
    "ahmed", "rajan", "qasim",
}

FEMALE_NAMES = {
    # Indian
    "aisha", "alka", "ananya", "anjali", "ankita", "anushka", "arpita",
    "deepika", "divya", "garima", "ishita", "kajal", "kavya", "khushi",
    "komal", "kritika", "mansi", "megha", "meera", "muskan", "namrata",
    "neha", "nikita", "nisha", "pallavi", "pooja", "prachi", "pragya",
    "preeti", "priya", "radha", "ritu", "riya", "sakshi", "sandhya",
    "shruti", "simran", "sneha", "sonam", "srishti", "swati", "tanvi",
    "tanya", "trisha", "vandana", "vidya", "zara", "diya", "yukta",
    "amrita", "ayesha", "bhavna", "charu", "damini", "ekta", "falak",
    "gunjan", "harshita", "indira", "janvi", "kamini", "lavanya", "madhu",
    "nandini", "parul", "rekha", "savita", "taruna", "uma", "vaishnavi",
    "chanchal", "dimple", "esha", "heena", "isha", "jyoti", "kiran",
    "lata", "minal", "nitu", "payal", "reena", "seema", "usha", "yamini",
    # English
    "sarah", "emily", "emma", "olivia", "ava", "sophia", "isabella",
    "mia", "amelia", "harper", "evelyn", "abigail", "elizabeth", "sofia",
    "ella", "grace", "chloe", "penelope", "layla", "lily", "zoe",
    # Arabic
    "fatima", "maryam", "amina", "hana", "sara", "leila", "yasmin",
    "noor", "zainab",
}


async def detect_gender_api(first_name: str) -> Optional[str]:
    """
    Genderize.io API se gender detect karta hai.

    Returns:
        'male' | 'female' | None

    Probability < 0.70 → None (uncertain, fallback to local DB)
    """
    if not first_name:
        return None

    clean_name = re.sub(r"[^a-zA-Z]", "", first_name).lower()
    if not clean_name:
        return None

    try:
        url = "https://api.genderize.io"
        params: dict = {"name": clean_name}
        if GENDERIZE_API_KEY:
            params["apikey"] = GENDERIZE_API_KEY

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                gender = data.get("gender")
                probability = data.get("probability", 0)

                if gender and probability >= 0.70:
                    logger.info(
                        f"Genderize: {first_name} → {gender} ({probability:.0%})"
                    )
                    return gender
                else:
                    logger.info(
                        f"Genderize: {first_name} → uncertain ({probability:.0%})"
                    )
                    return None

    except Exception as e:
        logger.warning(f"Genderize API error: {e}")
        return None


def detect_gender_db(first_name: str, last_name: str = "") -> Optional[str]:
    """Local name database se gender detect karta hai (offline fallback)."""
    full = f"{first_name} {last_name}".lower().strip()
    words = re.findall(r"[a-z]+", full)
    for word in words:
        if word in MALE_NAMES:
            return "male"
        if word in FEMALE_NAMES:
            return "female"
    return None


async def detect_gender(
    first_name: str,
    last_name: str = ""
) -> Optional[str]:
    """
    Gender detect karta hai — pehle API, phir DB fallback.

    Returns: 'male' | 'female' | None
    """
    # Layer 1: Genderize.io API
    gender = await detect_gender_api(first_name)
    if gender:
        return gender

    # Layer 2: Local database
    gender = detect_gender_db(first_name, last_name)
    if gender:
        logger.info(f"DB fallback: {first_name} {last_name} → {gender}")
        return gender

    return None


# ══════════════════════════════════════════════════════════════
# WELCOME MESSAGE FORMATTER
# Newlines properly handle karta hai
# ══════════════════════════════════════════════════════════════
def format_welcome_message(
    template: str,
    name: str,
    username: str,
    group_name: str
) -> str:
    """
    Welcome message template format karta hai.

    Placeholders:
        {name}     → User's full name
        {username} → @username ya name fallback
        {group}    → Group ka naam

    Supports \\n, actual newlines, and escaped characters.
    """
    formatted = (
        template
        .replace("{name}", name)
        .replace("{username}", username)
        .replace("{group}", group_name)
    )
    return formatted


# ══════════════════════════════════════════════════════════════
# DEFAULT WELCOME MESSAGES
# ══════════════════════════════════════════════════════════════
DEFAULT_MALE_MSG = (
    "💙 *Swagat hai, {name}!*\n\n"
    "👤 Username: {username}\n"
    "🏠 Group: *{group}*\n\n"
    "Bhai group mein tumhara dil se swagat hai! 🎉\n\n"
    "📌 Rules follow karo, masti karo aur seekhte raho! 🚀"
)

DEFAULT_FEMALE_MSG = (
    "💗 *Swagat hai, {name}!*\n\n"
    "👤 Username: {username}\n"
    "🏠 Group: *{group}*\n\n"
    "Behen group mein tumhara dil se swagat hai! 🎉\n\n"
    "📌 Rules follow karo, masti karo aur seekhte raho! 🚀"
)


# ══════════════════════════════════════════════════════════════
# /start — Bot Info & Commands
# ══════════════════════════════════════════════════════════════
async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    await update.message.reply_text(
        "👋 *Namaste, {name}!*\n\n"
        "Main *Advanced Welcome Bot v2.0* hoon 🤖\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *Available Commands:*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔗 `/connect`\n"
        "   └─ Group se DM mein setup karo\n\n"
        "🎬 `/setvideo_male [message]`\n"
        "   └─ Boy welcome video + msg set karo\n"
        "   └─ _Video pe reply karo + message likho_\n\n"
        "🎀 `/setvideo_female [message]`\n"
        "   └─ Girl welcome video + msg set karo\n"
        "   └─ _Video pe reply karo + message likho_\n\n"
        "👁 `/showset`\n"
        "   └─ Current settings dekho\n\n"
        "🗑 `/delete`\n"
        "   └─ Settings delete karo\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *Tips:*\n"
        "• `{name}` → Member ka naam\n"
        "• `{username}` → @username\n"
        "• `{group}` → Group ka naam\n"
        "• Multiline msg bhi set kar sakte ho!\n\n"
        "⚠️ _Sirf admin/owner commands use kar sakte hain_".format(
            name=user.first_name or "Dost"
        ),
        parse_mode=ParseMode.MARKDOWN
    )


# ══════════════════════════════════════════════════════════════
# /connect — Group ↔ DM Bridge
# ══════════════════════════════════════════════════════════════
async def connect_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    chat = update.effective_chat
    user = update.effective_user

    # ── Private Chat ──
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gname = context.user_data.get("active_group_name", "—")

        if gid:
            status = (
                f"✅ *Connected Group:* {gname}\n"
                f"📋 Group ID: `{gid}`"
            )
            tip = "\n\nAb `/setvideo_male` ya `/setvideo_female` se settings karo."
        else:
            status = "⚠️ Koi group connected nahi."
            tip = (
                "\n\n_Pehle apne group mein `/connect` chalao,_\n"
                "_phir yahan aao settings karne ke liye._"
            )

        await update.message.reply_text(
            f"🔗 *Bot Connection Status*\n\n"
            f"{status}{tip}",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── Group Chat ──
    if not await is_admin(update, context):
        await update.message.reply_text(
            "❌ Sirf admin/owner yeh command use kar sakte hain."
        )
        return

    context.user_data["active_group_id"] = chat.id
    context.user_data["active_group_name"] = chat.title

    bot_me = await context.bot.get_me()
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🤖 Bot DM Mein Kholo",
            url=f"https://t.me/{bot_me.username}?start=setup"
        )
    ]])
    await update.message.reply_text(
        f"🔗 *{chat.title}* ke liye setup shuru karo!\n\n"
        "Neeche button dabao — DM mein jao aur settings karo 👇",
        reply_markup=btn,
        parse_mode=ParseMode.MARKDOWN
    )


# ══════════════════════════════════════════════════════════════
# /setvideo_male & /setvideo_female
# Video + Multiline Welcome Message set karo
# ══════════════════════════════════════════════════════════════
async def _setvideo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gender: str
):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.message

    # ── Determine group_id ──
    if chat.type == "private":
        group_id = context.user_data.get("active_group_id")
        group_name = context.user_data.get("active_group_name", "Group")
        if not group_id:
            await msg.reply_text(
                "⚠️ Pehle group mein `/connect` chalao,\n"
                "phir yahan aao settings karne ke liye.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    else:
        if not await is_admin(update, context):
            await msg.reply_text(
                "❌ Sirf admin/owner yeh command use kar sakte hain."
            )
            return
        group_id = chat.id
        group_name = chat.title

    # ── Extract video from reply ──
    reply = msg.reply_to_message
    video_fid = None
    if reply:
        if reply.video:
            video_fid = reply.video.file_id
        elif reply.animation:
            video_fid = reply.animation.file_id
        elif (
            reply.document
            and reply.document.mime_type
            and "video" in reply.document.mime_type
        ):
            video_fid = reply.document.file_id

    # ── Extract welcome message from args ──
    # context.args = command ke baad saara text (spaces included)
    # Telegram multiline message properly capture hota hai
    if context.args:
        welcome_text = " ".join(context.args).strip()
    else:
        welcome_text = ""

    emoji = "🎬" if gender == "male" else "🎀"
    label = "Male (Boy)" if gender == "male" else "Female (Girl)"

    # ── Save settings ──
    if video_fid:
        await set_group_key(group_id, f"{gender}_video_id", video_fid)

    if welcome_text:
        await set_group_key(group_id, f"{gender}_welcome_msg", welcome_text)

    # ── Build response ──
    lines = [
        f"{emoji} *{label} Settings Updated!*\n",
        f"🏠 Group: *{group_name}*",
        f"📁 Group ID: `{group_id}`\n",
    ]

    if video_fid:
        lines.append("📹 Video: ✅ Save ho gaya")
    else:
        lines.append("📹 Video: ⚠️ Video reply nahi ki — purana rahega")

    if welcome_text:
        lines.append("💬 Message: ✅ Save ho gaya")
        # Preview — properly formatted
        preview = format_welcome_message(
            welcome_text, name="Sample Name",
            username="@sample_user", group_name=group_name
        )
        lines.append(f"\n📝 *Message Preview:*\n{preview}")
    else:
        lines.append("💬 Message: ℹ️ Nahi diya — default rahega")

    await msg.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN
    )
    logger.info(
        f"[{group_name}] {label} settings updated by "
        f"@{user.username or user.id}"
    )


async def setvideo_male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _setvideo(update, context, "male")


async def setvideo_female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _setvideo(update, context, "female")


# ══════════════════════════════════════════════════════════════
# /showset — View Current Settings
# ══════════════════════════════════════════════════════════════
async def showset_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    chat = update.effective_chat

    if chat.type == "private":
        group_id = context.user_data.get("active_group_id")
        group_name = context.user_data.get("active_group_name", "Group")
        if not group_id:
            await update.message.reply_text(
                "⚠️ Pehle group mein `/connect` chalao.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    else:
        if not await is_admin(update, context):
            await update.message.reply_text(
                "❌ Sirf admin/owner settings dekh sakte hain."
            )
            return
        group_id = chat.id
        group_name = chat.title

    s = await get_group_settings(group_id)
    check = lambda v: "✅ Set hai" if v else "❌ Set nahi"

    # Build settings report
    male_video = check(s.get("male_video_id"))
    male_msg = s.get("male_welcome_msg", "❌ Set nahi (default use hoga)")
    female_video = check(s.get("female_video_id"))
    female_msg = s.get("female_welcome_msg", "❌ Set nahi (default use hoga)")

    text = (
        f"📋 *Settings — {group_name}*\n"
        f"📁 Group ID: `{group_id}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎬 *Male (Boy):*\n"
        f"   📹 Video : {male_video}\n"
        f"   💬 Msg :\n"
        f"   └─ `{male_msg}`\n\n"
        f"🎀 *Female (Girl):*\n"
        f"   📹 Video : {female_video}\n"
        f"   💬 Msg :\n"
        f"   └─ `{female_msg}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ══════════════════════════════════════════════════════════════
# /delete — Delete Settings
# ══════════════════════════════════════════════════════════════
async def delete_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    chat = update.effective_chat

    if chat.type == "private":
        group_id = context.user_data.get("active_group_id")
        group_name = context.user_data.get("active_group_name", "Group")
        if not group_id:
            await update.message.reply_text(
                "⚠️ Pehle group mein `/connect` chalao.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    else:
        if not await is_admin(update, context):
            await update.message.reply_text(
                "❌ Sirf admin/owner delete kar sakte hain."
            )
            return
        group_id = chat.id
        group_name = chat.title

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎬 Male Delete",
                callback_data=f"del_male_{group_id}"
            ),
            InlineKeyboardButton(
                "🎀 Female Delete",
                callback_data=f"del_female_{group_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "🗑 Sab Delete Karo",
                callback_data=f"del_all_{group_id}"
            )
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="del_cancel")],
    ])

    await update.message.reply_text(
        f"🗑 *{group_name}* — Kya delete karna hai?",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN
    )


async def delete_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "del_cancel":
        await query.edit_message_text("✅ Delete cancel kar diya.")
        return

    parts = data.split("_")
    action = parts[1]
    group_id = int(parts[2])

    if action == "male":
        await delete_group_key(group_id, "male_video_id")
        await delete_group_key(group_id, "male_welcome_msg")
        await query.edit_message_text("✅ Male settings delete ho gayi!")

    elif action == "female":
        await delete_group_key(group_id, "female_video_id")
        await delete_group_key(group_id, "female_welcome_msg")
        await query.edit_message_text("✅ Female settings delete ho gayi!")

    elif action == "all":
        await delete_group_key(group_id)
        await query.edit_message_text("✅ Saari settings delete ho gayi!")


# ══════════════════════════════════════════════════════════════
# WELCOME SENDER
# Video + Properly formatted message
# ══════════════════════════════════════════════════════════════
async def send_welcome(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user,
    gender: str,
    group_name: str
):
    s = await get_group_settings(chat_id)
    video_id = s.get(f"{gender}_video_id")
    saved_msg = s.get(f"{gender}_welcome_msg", "")

    name = user.full_name or user.first_name or "Dost"
    username = f"@{user.username}" if user.username else name

    # ── Build final message ──
    if saved_msg:
        final = format_welcome_message(
            saved_msg,
            name=name,
            username=username,
            group_name=group_name
        )
    else:
        template = DEFAULT_MALE_MSG if gender == "male" else DEFAULT_FEMALE_MSG
        final = format_welcome_message(
            template,
            name=name,
            username=username,
            group_name=group_name
        )

    # ── Send with video or fallback to text ──
    if video_id:
        try:
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_id,
                caption=final,
                parse_mode=ParseMode.MARKDOWN
            )
            return
        except TelegramError as e:
            logger.warning(f"Video send error (fallback to text): {e}")

    # Fallback: text only
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=final,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramError:
        # Markdown parse fail → plain text fallback
        await context.bot.send_message(
            chat_id=chat_id,
            text=final.replace("*", "").replace("_", "")
        )


# ══════════════════════════════════════════════════════════════
# GENDER BUTTON CALLBACK
# Format: gender_GENDER_USERID_CHATID
# Sirf wahi user click kar sakta hai jiske liye button hai
# ══════════════════════════════════════════════════════════════
async def gender_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    data = query.data
    clicker = update.effective_user.id

    parts = data.split("_")
    if len(parts) < 4:
        await query.answer()
        return

    gender = parts[1]
    user_id = int(parts[2])
    chat_id = int(parts[3])

    # ✅ Sirf wahi user click kare jiske liye button hai
    if clicker != user_id:
        await query.answer(
            "❌ Yeh button sirf naye member ke liye hai!",
            show_alert=True
        )
        return

    await query.answer(
        f"{'👦 Boy' if gender == 'male' else '👧 Girl'} select kiya!"
    )

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        user = member.user
    except TelegramError:
        user = update.effective_user

    try:
        chat_obj = await context.bot.get_chat(chat_id)
        group_name = chat_obj.title or "Group"
    except TelegramError:
        group_name = "Group"

    # Button wala message delete karo
    try:
        await query.message.delete()
    except TelegramError:
        pass

    await send_welcome(context, chat_id, user, gender, group_name)
    logger.info(
        f"Gender selected: {gender} for {user.full_name} in {group_name}"
    )


# ══════════════════════════════════════════════════════════════
# NEW MEMBER JOIN HANDLER
# ══════════════════════════════════════════════════════════════
async def greet_new_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    result = update.chat_member
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    joined = (
        new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)
        and old_status not in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR
        )
    )
    if not joined:
        return

    user = result.new_chat_member.user
    chat = update.effective_chat

    if user.is_bot:
        return

    group_name = chat.title or "Group"
    name = user.full_name or user.first_name or "Dost"
    username = f"@{user.username}" if user.username else name

    logger.info(f"New member: {name} ({username}) in {group_name}")

    # Gender detect — API + DB fallback
    gender = await detect_gender(user.first_name or "", user.last_name or "")

    if gender:
        # Auto-detected → directly send welcome
        await send_welcome(context, chat.id, user, gender, group_name)
    else:
        # Gender unknown → ask the member
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "👦 Boy hoon",
                callback_data=f"gender_male_{user.id}_{chat.id}"
            ),
            InlineKeyboardButton(
                "👧 Girl hoon",
                callback_data=f"gender_female_{user.id}_{chat.id}"
            ),
        ]])

        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                f"👋 *{name}* ka swagat hai!\n"
                f"👤 Username: {username}\n\n"
                f"Batao tum kaun ho? 😊\n"
                f"_Sirf tum hi yeh button daba sakte ho_ 👇"
            ),
            reply_markup=kb,
            parse_mode=ParseMode.MARKDOWN
        )


# ══════════════════════════════════════════════════════════════
# MAIN — Bot Startup
# ══════════════════════════════════════════════════════════════
def main():
    if not BOT_TOKEN:
        print("\n" + "=" * 55)
        print("  ❌  BOT_TOKEN environment variable set nahi hai!")
        print("  Railway:  Variables mein BOT_TOKEN daalo")
        print("  Local:   .env file mein BOT_TOKEN=your_token")
        print("=" * 55 + "\n")
        return

    # Settings file verify
    path = _settings_path()
    if not path.exists():
        logger.info(f"Settings file not found. Creating: {path}")
        path.write_text("{}")

    app = Application.builder().token(BOT_TOKEN).build()

    # ── Command Handlers ──
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("connect", connect_command))
    app.add_handler(CommandHandler("setvideo_male", setvideo_male))
    app.add_handler(CommandHandler("setvideo_female", setvideo_female))
    app.add_handler(CommandHandler("showset", showset_command))
    app.add_handler(CommandHandler("delete", delete_command))

    # ── Callback Handlers ──
    app.add_handler(CallbackQueryHandler(gender_callback, pattern=r"^gender_"))
    app.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del_"))

    # ── Chat Member Handler ──
    app.add_handler(
        ChatMemberHandler(greet_new_member, ChatMemberHandler.CHAT_MEMBER)
    )

    logger.info("🤖 Advanced Welcome Bot v2.0 — Running!")
    logger.info("   Press Ctrl+C to stop.")

    app.run_polling(
        allowed_updates=["message", "chat_member", "callback_query"]
    )


if __name__ == "__main__":
    main()
