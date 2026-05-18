#!/usr/bin/env python3
"""
Welcome Bot Gender Detection + Full Feature Set
Fixed version — all 12 bugs resolved
"""

import os
import json
import logging
import random
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ChatMemberHandler,
    ContextTypes, filters, ConversationHandler, CallbackQueryHandler
)
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from groq import Groq

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- Config ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Validate at startup, not inside main()
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN environment variable set nahi hai.")
if not GROQ_API_KEY:
    raise RuntimeError("❌ GROQ_API_KEY environment variable set nahi hai.")

DATA_FILE = "welcome_bot_data.json"

groq_client = Groq(api_key=GROQ_API_KEY)

# ---------- Database Helper (thread-safe) ----------
# FIX #4: Added threading lock to prevent race condition / data corruption
_data_lock = threading.Lock()

def load_data():
    with _data_lock:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

def save_data(data):
    with _data_lock:
        # Atomic write: write to temp file first, then rename
        tmp = DATA_FILE + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)

def get_settings(chat_id):
    data = load_data()
    return data.get(str(chat_id), {
        "active": False,
        "admins": [],
        "chat_title": "",
        "male": {"messages": [], "videos": []},
        "female": {"messages": [], "videos": []},
        "unknown": {"messages": [], "videos": []},
        "buttons": []
    })

def save_settings(chat_id, settings):
    data = load_data()
    data[str(chat_id)] = settings
    save_data(data)

def delete_settings(chat_id):
    data = load_data()
    data.pop(str(chat_id), None)
    save_data(data)

def get_linked_chats(user_id):
    data = load_data()
    # FIX #8: Cast both sides to int for safe comparison
    return [int(cid) for cid, s in data.items() if int(user_id) in [int(x) for x in s.get("admins", [])]]

# ---------- GROQ Gender Detection ----------
# FIX #7: Fixed the common_female_names check — was always False for full names
# FIX #12: Added timeout to Groq API call to prevent blocking
async def detect_gender(first_name: str, last_name: str = "", username: str = "") -> str:
    """Use GROQ LLM to detect gender. Returns 'male', 'female', or 'unknown'."""
    try:
        # FIX #7: Check first_name only (not full_name) against the list — was dead code before
        common_female_names = {
            'pinky', 'sweety', 'baby', 'gudiya', 'soni', 'pappi',
            'rinky', 'tinku', 'bittu', 'chintu', 'pintu', 'rani',
            'priya', 'kavya', 'neha', 'pooja', 'anjali', 'divya'
        }
        if first_name.lower() in common_female_names:
            logger.info(f"Special case female name: {first_name}")
            return "female"

        full_name = f"{first_name} {last_name}".strip()
        prompt = (
            f"Based on the name '{full_name}' (username: @{username}), determine the gender.\n"
            "Reply with ONLY one word: 'male', 'female', or 'unknown'.\n"
            "Consider Indian, Arabic, English, and international names.\n"
            "IMPORTANT: Names like Pinky, Sweety, Baby, Gudiya are FEMALE names in Indian context.\n"
            "If unsure, reply 'unknown'."
        )
        # FIX #12: Added timeout=10 so it never hangs the bot
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.1,
            timeout=10,
        )
        result = response.choices[0].message.content.strip().lower()
        if "female" in result:
            return "female"
        elif "male" in result:
            return "male"
        return "unknown"
    except Exception as e:
        logger.error(f"GROQ gender detection error: {e}")
        return "unknown"

# ---------- Helper ----------
def esc(text: str) -> str:
    return escape_markdown(text, version=2)

def smart_truncate(text: str, limit: int = 100) -> str:
    # FIX #5: Don't add '...' if text is already short enough
    if len(text) <= limit:
        return text
    return text[:limit] + "..."

async def send_welcome(context, chat_id, user, gender_key):
    settings = get_settings(chat_id)
    gdata = settings.get(gender_key, {"messages": [], "videos": []})
    messages = gdata.get("messages", [])
    videos = gdata.get("videos", [])
    buttons = settings.get("buttons", [])

    if not messages:
        await context.bot.send_message(chat_id=chat_id, text=f"👋 Welcome {user.first_name}!")
        return

    msg_template = random.choice(messages)
    gender_label = "👦 Male" if gender_key == "male" else "👧 Female" if gender_key == "female" else "🧑 Member"
    name_mention = f"[{user.first_name}](tg://user?id={user.id})"
    msg = msg_template.replace("{name}", user.first_name)
    msg = msg.replace("{mention}", name_mention)
    msg = msg.replace("{username}", f"@{user.username}" if user.username else user.first_name)
    msg = msg.replace("{gender}", gender_label)

    video_id = random.choice(videos) if videos else None
    kb = [[InlineKeyboardButton(btn["text"], url=btn["url"])] for btn in buttons]
    reply_markup = InlineKeyboardMarkup(kb) if kb else None

    try:
        if video_id:
            await context.bot.send_video(
                chat_id=chat_id, video=video_id,
                # FIX #6: Changed ParseMode.MARKDOWN → MARKDOWN_V2 for consistency
                caption=msg, parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=reply_markup
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id, text=msg,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Send welcome error: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"👋 Welcome {user.first_name}!")

# ---------- Conversation States ----------
WAITING_MALE_MSG, WAITING_MALE_VIDEO = 1, 2
WAITING_FEMALE_MSG, WAITING_FEMALE_VIDEO = 3, 4
WAITING_UNKNOWN_MSG, WAITING_UNKNOWN_VIDEO = 5, 6
WAITING_BUTTON_TEXT, WAITING_BUTTON_URL = 7, 8
WAITING_MORE_GENDER, WAITING_MORE_MSG, WAITING_MORE_VIDEO = 9, 10, 11

# ---------- Admin Check ----------
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    user_id = update.effective_user.id
    target = chat_id or update.effective_chat.id
    if update.effective_chat.type == "private":
        return True
    try:
        admins = await context.bot.get_chat_administrators(target)
        return user_id in [a.user.id for a in admins]
    except:
        return False

# ---------- /connect ----------
async def cmd_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("❌ Ye command group mein use karo!")
        return
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Sirf group admins /connect kar sakte hain.")
        return
    bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
    if bot_member.status != "administrator":
        await update.message.reply_text(
            "⚠️ Pehle mujhe group *admin* banao\\. Phir /connect karo\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    settings = get_settings(chat.id)
    if user.id not in settings["admins"]:
        settings["admins"].append(user.id)
    settings["active"] = True
    settings["chat_title"] = chat.title
    save_settings(chat.id, settings)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📩 Bot DM mein settings", url=f"https://t.me/{context.bot.username}")
    ]])
    await update.message.reply_text(
        f"✅ Bot connected to *{esc(chat.title)}*\\!\n\n"
        f"Ab DM mein jaakar /set\\_male, /set\\_female, /set\\_unknown use karo\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )

# ---------- /disconnect (FIX #9: New command — disconnect without data loss) ----------
async def cmd_disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("❌ Ye command group mein use karo!")
        return
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Sirf admins disconnect kar sakte hain.")
        return
    settings = get_settings(chat.id)
    settings["active"] = False
    # Remove this user from admins list for this group
    settings["admins"] = [a for a in settings["admins"] if int(a) != int(user.id)]
    save_settings(chat.id, settings)
    await update.message.reply_text(
        "✅ Bot disconnect ho gaya\\! Settings safe hain, /connect se wapas aa sakte ho\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )

# ---------- /start ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("ℹ️ DM mein use karo.")
        return
    text = (
        "🌹 *Welcome Bot* \\- Gender Detection\n\n"
        "▪ /set\\_male — male message \\+ video\n"
        "▪ /set\\_female — female message \\+ video\n"
        "▪ /set\\_unknown — unknown gender message \\+ video\n"
        "▪ /add\\_more — aur messages/videos add karo\n"
        "▪ /listmedia — media count dekho\n"
        "▪ /clearmedia — sab media clear karo\n"
        "▪ /clearbuttons — sab buttons clear karo\n"
        "▪ /preview — test welcome message\n"
        "▪ /settings — current config dekho\n"
        "▪ /setbuttons — inline buttons set karo\n"
        "▪ /reset — sab settings delete karo\n\n"
        "*Pehle group mein /connect karo\\!*\n"
        "Group se hatane ke liye group mein /disconnect karo\\."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

# ---------- Generic Setup Handlers ----------
async def setup_start(update, context, gender):
    if update.effective_chat.type != "private":
        return ConversationHandler.END
    user = update.effective_user
    linked = get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Pehle group mein /connect karo.")
        return ConversationHandler.END
    context.user_data["gender"] = gender
    context.user_data["linked"] = linked
    icon = "👦" if gender == "male" else "👧" if gender == "female" else "🧑"
    await update.message.reply_text(
        f"{icon} *{esc(gender.capitalize())} welcome message likho:*\n"
        "Placeholders: `{name}`, `{mention}`, `{username}`, `{gender}`\n\n"
        "Example: `Welcome {name}\\! {gender} member ho aap\\.`",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    state_map = {"male": WAITING_MALE_MSG, "female": WAITING_FEMALE_MSG, "unknown": WAITING_UNKNOWN_MSG}
    return state_map[gender]

async def cmd_set_male(update, context): return await setup_start(update, context, "male")
async def cmd_set_female(update, context): return await setup_start(update, context, "female")
async def cmd_set_unknown(update, context): return await setup_start(update, context, "unknown")

async def recv_gender_msg(update, context):
    context.user_data["msg"] = update.message.text
    gender = context.user_data["gender"]
    preview = esc(smart_truncate(context.user_data["msg"]))  # FIX #5
    await update.message.reply_text(
        f"✅ *Message saved successfully\\!* 🎉\n\n"
        f"📝 *Your {esc(gender)} welcome message:*\n`{preview}`\n\n"
        f"🎬 Ab {esc(gender)} ke liye *video bhejo* \\(ya /skip kar sakte ho\\)\n"
        f"Video bhejte hi *message \\+ video dono save ho jayenge*\\!",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    state_map = {"male": WAITING_MALE_VIDEO, "female": WAITING_FEMALE_VIDEO, "unknown": WAITING_UNKNOWN_VIDEO}
    return state_map[gender]

async def recv_gender_video(update, context):
    gender = context.user_data.get("gender", "unknown")
    msg = context.user_data.get("msg", "")
    video_id = None

    if update.message.video:
        video_id = update.message.video.file_id
    elif update.message.document and update.message.document.mime_type and \
            update.message.document.mime_type.startswith("video"):
        video_id = update.message.document.file_id

    # FIX #1: Track gdata outside loop with a safe default
    gdata = {"messages": [], "videos": []}
    for chat_id in context.user_data.get("linked", []):
        settings = get_settings(chat_id)
        gdata = settings.setdefault(gender, {"messages": [], "videos": []})
        if msg:
            gdata["messages"].append(msg)
        if video_id:
            gdata["videos"].append(video_id)
        save_settings(chat_id, settings)

    await update.message.reply_text(
        f"✅ *{esc(gender.capitalize())} setup COMPLETE\\!* 🎉\n\n"
        f"📝 *Messages saved:* `{len(gdata['messages'])}`\n"
        f"🎬 *Videos saved:* `{len(gdata['videos'])}`\n\n"
        f"✨ Welcome message \\+ video ready\\!",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return ConversationHandler.END

async def skip_video(update, context):
    gender = context.user_data.get("gender", "unknown")
    msg = context.user_data.get("msg", "")
    if not msg:
        await update.message.reply_text("❌ Pehle message to bhejo.")
        return ConversationHandler.END

    # FIX #1: Safe gdata reference outside loop
    gdata = {"messages": [], "videos": []}
    for chat_id in context.user_data.get("linked", []):
        settings = get_settings(chat_id)
        gdata = settings.setdefault(gender, {"messages": [], "videos": []})
        gdata["messages"].append(msg)
        save_settings(chat_id, settings)

    await update.message.reply_text(
        f"✅ *{esc(gender.capitalize())} message saved \\(no video\\)\\!* 📝\n\n"
        f"📝 *Total messages:* `{len(gdata['messages'])}`\n"
        f"🎬 *Video:* Skipped\n\n"
        f"✨ Welcome message ready\\! \\(bina video ke\\)",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return ConversationHandler.END

# ---------- /add_more ----------
async def cmd_add_more(update, context):
    if update.effective_chat.type != "private":
        return ConversationHandler.END
    user = update.effective_user
    linked = get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Pehle /connect karo.")
        return ConversationHandler.END
    context.user_data["linked"] = linked
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("👦 Male", callback_data="more_male"),
        InlineKeyboardButton("👧 Female", callback_data="more_female"),
        InlineKeyboardButton("🧑 Unknown", callback_data="more_unknown")
    ]])
    await update.message.reply_text(
        "➕ *Aur media add karna hai?* Kiske liye?",
        parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb
    )
    return WAITING_MORE_GENDER

async def more_gender_callback(update, context):
    query = update.callback_query
    await query.answer()
    gender = query.data.split("_")[1]
    context.user_data["gender"] = gender
    await query.edit_message_text(
        f"{esc(gender.capitalize())} ke liye naya *message* likho:",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_MORE_MSG

async def recv_more_msg(update, context):
    context.user_data["msg"] = update.message.text
    await update.message.reply_text(
        "✅ *New message noted\\!* 📝\n\nAb *video bhejo* \\(ya /skip\\)",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_MORE_VIDEO

async def recv_more_video(update, context):
    gender = context.user_data.get("gender", "unknown")
    msg = context.user_data.get("msg", "")
    video_id = None
    if update.message.video:
        video_id = update.message.video.file_id

    # FIX #1: Safe gdata reference
    gdata = {"messages": [], "videos": []}
    for chat_id in context.user_data.get("linked", []):
        settings = get_settings(chat_id)
        gdata = settings.setdefault(gender, {"messages": [], "videos": []})
        if msg:
            gdata["messages"].append(msg)
        if video_id:
            gdata["videos"].append(video_id)
        save_settings(chat_id, settings)

    await update.message.reply_text(
        f"✅ *New media added for {esc(gender.capitalize())}\\!* 🎉\n\n"
        f"📝 Total messages: `{len(gdata['messages'])}`\n"
        f"🎬 Total videos: `{len(gdata['videos'])}`",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return ConversationHandler.END

# ---------- /listmedia ----------
async def cmd_listmedia(update, context):
    if update.effective_chat.type != "private":
        return
    linked = get_linked_chats(update.effective_user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return
    text = "📊 *Media Count*\n\n"
    for chat_id in linked:
        settings = get_settings(chat_id)
        title = settings.get("chat_title", str(chat_id))
        for g in ["male", "female", "unknown"]:
            msgs = len(settings.get(g, {}).get("messages", []))
            vids = len(settings.get(g, {}).get("videos", []))
            icon = "👦" if g == "male" else "👧" if g == "female" else "🧑"
            text += f"*{esc(title)}* {icon} {esc(g.capitalize())}: `{msgs}` msgs, `{vids}` vids\n"
        text += "\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

# ---------- /clearmedia ----------
async def cmd_clearmedia(update, context):
    if update.effective_chat.type != "private":
        return
    if not get_linked_chats(update.effective_user.id):
        await update.message.reply_text("❌ Koi group connected nahi.")
        return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Haan, Clear Karo", callback_data="confirm_clear"),
        InlineKeyboardButton("❌ Nahi", callback_data="cancel_clear")
    ]])
    await update.message.reply_text(
        "⚠️ *Sab media clear karna chahte ho?*",
        parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb
    )

async def clearmedia_callback(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_clear":
        linked = get_linked_chats(update.effective_user.id)
        for chat_id in linked:
            settings = get_settings(chat_id)
            for g in ["male", "female", "unknown"]:
                settings[g] = {"messages": [], "videos": []}
            save_settings(chat_id, settings)
        await query.edit_message_text("✅ Sab media clear ho gaya\\!", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.edit_message_text("❌ Cancel\\.", parse_mode=ParseMode.MARKDOWN_V2)

# ---------- /clearbuttons (FIX #11: New command) ----------
async def cmd_clearbuttons(update, context):
    if update.effective_chat.type != "private":
        return
    linked = get_linked_chats(update.effective_user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return
    for chat_id in linked:
        settings = get_settings(chat_id)
        settings["buttons"] = []
        save_settings(chat_id, settings)
    await update.message.reply_text("✅ Sab buttons clear ho gaye\\!", parse_mode=ParseMode.MARKDOWN_V2)

# ---------- /preview ----------
async def cmd_preview(update, context):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    linked = get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return
    await update.message.reply_text("🔍 Preview bhej raha hoon \\(DM mein\\)\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
    for chat_id in linked:
        settings = get_settings(chat_id)
        title = esc(settings.get("chat_title", str(chat_id)))
        for g in ["male", "female", "unknown"]:
            await update.message.reply_text(
                f"📌 *{title} \\- {esc(g.capitalize())} Preview:*",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            await send_welcome(context, update.effective_chat.id, user, g)

# ---------- /settings ----------
async def cmd_settings(update, context):
    if update.effective_chat.type != "private":
        return
    linked = get_linked_chats(update.effective_user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return
    for chat_id in linked:
        settings = get_settings(chat_id)
        title = esc(settings.get("chat_title", str(chat_id)))
        active = "✅ Active" if settings.get("active") else "❌ Inactive"
        btns = len(settings.get("buttons", []))
        text = f"⚙️ *Settings — {title}*\n\nStatus: {active}\n🔘 Buttons: `{btns}`\n"
        for g in ["male", "female", "unknown"]:
            msgs = len(settings.get(g, {}).get("messages", []))
            vids = len(settings.get(g, {}).get("videos", []))
            icon = "👦" if g == "male" else "👧" if g == "female" else "🧑"
            text += f"{icon} {esc(g.capitalize())}: `{msgs}` msgs, `{vids}` vids\n"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

# ---------- /setbuttons ----------
async def cmd_setbuttons(update, context):
    if update.effective_chat.type != "private":
        return ConversationHandler.END
    linked = get_linked_chats(update.effective_user.id)
    if not linked:
        await update.message.reply_text("❌ Pehle /connect karo.")
        return ConversationHandler.END
    context.user_data["linked"] = linked
    await update.message.reply_text(
        "🔘 *Inline Button Set Karo*\n\nButton ka *text* type karo:",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_BUTTON_TEXT

async def recv_button_text(update, context):
    context.user_data["button_text"] = update.message.text
    await update.message.reply_text(
        "✅ Text noted\\! Ab button ki *URL* bhejo \\(http:// ya https://\\):",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_BUTTON_URL

async def recv_button_url(update, context):
    url = update.message.text.strip()
    text = context.user_data.get("button_text", "Button")
    if not url.startswith("http"):
        await update.message.reply_text(
            "❌ Valid URL bhejo \\(http:// ya https://\\)",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return WAITING_BUTTON_URL
    for chat_id in context.user_data.get("linked", []):
        settings = get_settings(chat_id)
        settings.setdefault("buttons", []).append({"text": text, "url": url})
        save_settings(chat_id, settings)
    await update.message.reply_text(
        f"✅ Button added\\! `{esc(text)}` → {esc(url)}",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return ConversationHandler.END

# ---------- /reset ----------
async def cmd_reset(update, context):
    if update.effective_chat.type != "private":
        return
    if not get_linked_chats(update.effective_user.id):
        await update.message.reply_text("❌ Koi group connected nahi.")
        return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑 Haan, Reset Karo", callback_data="confirm_reset"),
        InlineKeyboardButton("❌ Nahi", callback_data="cancel_reset")
    ]])
    await update.message.reply_text(
        "⚠️ *Sab settings delete karna chahte ho?* Ye undo nahi ho sakta\\.",
        parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb
    )

async def reset_callback(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_reset":
        linked = get_linked_chats(update.effective_user.id)
        for chat_id in linked:
            delete_settings(chat_id)
        await query.edit_message_text("✅ Sab reset ho gaya\\!", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.edit_message_text("❌ Cancel\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def cancel(update, context):
    await update.message.reply_text("❌ Operation cancel kiya\\.", parse_mode=ParseMode.MARKDOWN_V2)
    context.user_data.clear()
    return ConversationHandler.END

# ---------- New Member Handler ----------
# FIX #3: Added note — bot MUST be admin in the group for ChatMemberHandler.CHAT_MEMBER to work
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.chat_member:
        return
    cm = update.chat_member
    old = cm.old_chat_member.status
    new = cm.new_chat_member.status
    valid = [
        (ChatMember.LEFT, ChatMember.MEMBER),
        (ChatMember.BANNED, ChatMember.MEMBER),
        (ChatMember.RESTRICTED, ChatMember.MEMBER),
        (ChatMember.LEFT, ChatMember.RESTRICTED),
    ]
    if (old, new) not in valid:
        return
    new_member = cm.new_chat_member.user
    chat_id = cm.chat.id
    if new_member.is_bot:
        return
    settings = get_settings(chat_id)
    if not settings.get("active"):
        return
    gender = await detect_gender(
        new_member.first_name,
        new_member.last_name or "",
        new_member.username or ""
    )
    logger.info(f"New member: {new_member.first_name} | gender: {gender}")
    await send_welcome(context, chat_id, new_member, gender)

# ---------- Main ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    male_conv = ConversationHandler(
        entry_points=[CommandHandler("set_male", cmd_set_male)],
        states={
            WAITING_MALE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_gender_msg)],
            WAITING_MALE_VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, recv_gender_video),
                CommandHandler("skip", skip_video)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    female_conv = ConversationHandler(
        entry_points=[CommandHandler("set_female", cmd_set_female)],
        states={
            WAITING_FEMALE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_gender_msg)],
            WAITING_FEMALE_VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, recv_gender_video),
                CommandHandler("skip", skip_video)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    unknown_conv = ConversationHandler(
        entry_points=[CommandHandler("set_unknown", cmd_set_unknown)],
        states={
            WAITING_UNKNOWN_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_gender_msg)],
            WAITING_UNKNOWN_VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, recv_gender_video),
                CommandHandler("skip", skip_video)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    more_conv = ConversationHandler(
        entry_points=[CommandHandler("add_more", cmd_add_more)],
        states={
            WAITING_MORE_GENDER: [CallbackQueryHandler(more_gender_callback, pattern="^more_")],
            WAITING_MORE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_more_msg)],
            WAITING_MORE_VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, recv_more_video),
                CommandHandler("skip", skip_video)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    button_conv = ConversationHandler(
        entry_points=[CommandHandler("setbuttons", cmd_setbuttons)],
        states={
            WAITING_BUTTON_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_button_text)],
            WAITING_BUTTON_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_button_url)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("connect", cmd_connect))
    app.add_handler(CommandHandler("disconnect", cmd_disconnect))   # FIX #9
    app.add_handler(CommandHandler("listmedia", cmd_listmedia))
    app.add_handler(CommandHandler("clearmedia", cmd_clearmedia))
    app.add_handler(CommandHandler("clearbuttons", cmd_clearbuttons))  # FIX #11
    app.add_handler(CommandHandler("preview", cmd_preview))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(male_conv)
    app.add_handler(female_conv)
    app.add_handler(unknown_conv)
    app.add_handler(more_conv)
    app.add_handler(button_conv)
    app.add_handler(CallbackQueryHandler(clearmedia_callback, pattern="^(confirm|cancel)_clear$"))
    app.add_handler(CallbackQueryHandler(reset_callback, pattern="^(confirm|cancel)_reset$"))
    # FIX #3: Note — requires bot to be admin in group for this event to fire
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    logger.info("🚀 Bot started (all bugs fixed)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
