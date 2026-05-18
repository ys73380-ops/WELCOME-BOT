#!/usr/bin/env python3
"""
Welcome Bot Gender Detection + Full Feature Set
Fixed: Better gender detection + Video save confirmation
"""

import os
import logging
import json
import random
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
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")
DATA_FILE = "welcome_bot_data.json"

# Initialize GROQ client
groq_client = Groq(api_key=GROQ_API_KEY)

# ---------- Database Helper ----------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
    return [int(cid) for cid, s in data.items() if user_id in s.get("admins", [])]

# ---------- GROQ Gender Detection (IMPROVED for names like Pinky) ----------
async def detect_gender(first_name: str, last_name: str = "", username: str = "") -> str:
    """Use GROQ LLM to detect gender. Returns 'male', 'female', or 'unknown'."""
    try:
        full_name = f"{first_name} {last_name}".strip()
        
        # Special case for common female names that AI might get wrong
        common_female_names = ['pinky', 'sweety', 'baby', 'gudiya', 'soni', 'pappi', 'rinky', 'tinku', 'bittu', 'chintu', 'pintu']
        if full_name.lower() in common_female_names or full_name.lower().split()[0] in common_female_names:
            logger.info(f"Special case: {full_name} forced to female")
            return "female"
        
        prompt = (
            f"Based on the name '{full_name}' (username: @{username}), determine the gender.\n"
            "Reply with ONLY one word: 'male', 'female', or 'unknown'.\n"
            "Consider Indian, Arabic, English, and international names.\n"
            "IMPORTANT: Names like Pinky, Sweety, Baby, Gudiya are FEMALE names in Indian context.\n"
            "If unsure, reply 'unknown'."
        )
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.1,
        )
        result = response.choices[0].message.content.strip().lower()
        if "female" in result:
            return "female"
        elif "male" in result:
            return "male"
        else:
            return "unknown"
    except Exception as e:
        logger.error(f"GROQ gender detection error: {e}")
        return "unknown"

# ---------- Helper Functions ----------
def esc(text: str) -> str:
    return escape_markdown(text, version=2)

async def send_welcome(context, chat_id, user, gender_key):
    """gender_key = 'male', 'female', or 'unknown'"""
    settings = get_settings(chat_id)
    gdata = settings.get(gender_key, {"messages": [], "videos": []})
    messages = gdata.get("messages", [])
    videos = gdata.get("videos", [])
    buttons = settings.get("buttons", [])

    if not messages:
        fallback = f"👋 Welcome {user.first_name}!"
        await context.bot.send_message(chat_id=chat_id, text=fallback)
        return

    msg_template = random.choice(messages)
    gender_label = "👦 Male" if gender_key == "male" else "👧 Female" if gender_key == "female" else "🧑 Member"
    
    # Replace placeholders
    name_mention = f"[{user.first_name}](tg://user?id={user.id})"
    msg = msg_template.replace("{name}", user.first_name)
    msg = msg.replace("{mention}", name_mention)
    msg = msg.replace("{username}", f"@{user.username}" if user.username else user.first_name)
    msg = msg.replace("{gender}", gender_label)

    video_id = random.choice(videos) if videos else None

    # Inline keyboard
    kb = []
    for btn in buttons:
        kb.append([InlineKeyboardButton(btn["text"], url=btn["url"])])
    reply_markup = InlineKeyboardMarkup(kb) if kb else None

    try:
        if video_id:
            await context.bot.send_video(
                chat_id=chat_id, video=video_id,
                caption=msg, parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id, text=msg,
                parse_mode=ParseMode.MARKDOWN,
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

# ---------- /connect Command (in group) ----------
async def cmd_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("❌ Ye command group mein use karo!")
        return
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Sirf group admins /connect kar sakte hain.")
        return
    # Check if bot is admin
    bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
    if bot_member.status != "administrator":
        await update.message.reply_text("⚠️ Pehle mujhe group *admin* banao. Phir /connect karo.", parse_mode=ParseMode.MARKDOWN)
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
        f"✅ Bot connected to *{chat.title}*\\!\n\n"
        f"Ab DM mein jaakar /set\\_male, /set\\_female, /set\\_unknown use karo\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
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
        "▪ /preview — test welcome message\n"
        "▪ /settings — current config dekho\n"
        "▪ /setbuttons — inline buttons set karo\n"
        "▪ /reset — sab settings delete karo\n\n"
        "*Pehle group mein /connect karo\\!*"
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
    await update.message.reply_text(
        f"{'👦' if gender=='male' else '👧' if gender=='female' else '🧑'} *{gender.capitalize()} welcome message likho:*\n"
        "Placeholders: `{name}`, `{mention}`, `{username}`, `{gender}`\n\n"
        "Example: `Welcome {name}! {gender} member ho aap.`",
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
    await update.message.reply_text(
        f"✅ *Message saved successfully!* 🎉\n\n"
        f"📝 *Your {gender} welcome message:*\n`{context.user_data['msg'][:100]}...`\n\n"
        f"🎬 Ab {gender} ke liye *video bhejo* (ya /skip kar sakte ho)\n"
        f"Video bhejte hi *message + video dono save ho jayenge*!",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    state_map = {"male": WAITING_MALE_VIDEO, "female": WAITING_FEMALE_VIDEO, "unknown": WAITING_UNKNOWN_VIDEO}
    return state_map[gender]

async def recv_gender_video(update, context):
    gender = context.user_data["gender"]
    msg = context.user_data.get("msg", "")
    video_id = None
    
    if update.message.video:
        video_id = update.message.video.file_id
        logger.info(f"Video received: {video_id}")
    elif update.message.document and update.message.document.mime_type.startswith("video"):
        video_id = update.message.document.file_id
        logger.info(f"Document video received: {video_id}")
    
    for chat_id in context.user_data.get("linked", []):
        settings = get_settings(chat_id)
        gdata = settings.setdefault(gender, {"messages": [], "videos": []})
        if msg:
            gdata["messages"].append(msg)
        if video_id:
            gdata["videos"].append(video_id)
        save_settings(chat_id, settings)
    
    # Show confirmation with counts
    msg_count = len(gdata['messages'])
    video_count = len(gdata['videos'])
    
    await update.message.reply_text(
        f"✅ *{gender.capitalize()} setup COMPLETE!* 🎉\n\n"
        f"📝 *Message saved:* `{msg_count}` message(s)\n"
        f"🎬 *Video saved:* `{video_count}` video(s)\n\n"
        f"✨ *Welcome message + video ready!*\n"
        f"Jab koi {gender} member join karega, ye randomly select hoga.",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return ConversationHandler.END

async def skip_video(update, context):
    gender = context.user_data.get("gender")
    msg = context.user_data.get("msg", "")
    if not msg:
        await update.message.reply_text("❌ Pehle message to bhejo.")
        return ConversationHandler.END
    
    for chat_id in context.user_data.get("linked", []):
        settings = get_settings(chat_id)
        gdata = settings.setdefault(gender, {"messages": [], "videos": []})
        gdata["messages"].append(msg)
        save_settings(chat_id, settings)
    
    msg_count = len(gdata['messages'])
    
    await update.message.reply_text(
        f"✅ *{gender.capitalize()} message saved (no video)!* 📝\n\n"
        f"📝 *Total messages:* `{msg_count}`\n"
        f"🎬 *Video:* Skipped (None)\n\n"
        f"✨ *Welcome message ready!* (bina video ke)",
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
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👦 Male", callback_data="more_male"),
         InlineKeyboardButton("👧 Female", callback_data="more_female"),
         InlineKeyboardButton("🧑 Unknown", callback_data="more_unknown")]
    ])
    await update.message.reply_text("➕ *Aur media add karna hai?* Kiske liye?", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb)
    return WAITING_MORE_GENDER

async def more_gender_callback(update, context):
    query = update.callback_query
    await query.answer()
    gender = query.data.split("_")[1]
    context.user_data["gender"] = gender
    await query.edit_message_text(f"{gender.capitalize()} ke liye naya *message* likho:", parse_mode=ParseMode.MARKDOWN_V2)
    return WAITING_MORE_MSG

async def recv_more_msg(update, context):
    context.user_data["msg"] = update.message.text
    await update.message.reply_text(
        f"✅ *New message noted!* 📝\n\n"
        f"Ab *video bhejo* (ya /skip)\n"
        f"Video bhejte hi *dono save ho jayenge*!",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_MORE_VIDEO

async def recv_more_video(update, context):
    gender = context.user_data["gender"]
    msg = context.user_data.get("msg", "")
    video_id = None
    if update.message.video:
        video_id = update.message.video.file_id
    
    for chat_id in context.user_data["linked"]:
        settings = get_settings(chat_id)
        gdata = settings.setdefault(gender, {"messages": [], "videos": []})
        if msg:
            gdata["messages"].append(msg)
        if video_id:
            gdata["videos"].append(video_id)
        save_settings(chat_id, settings)
    
    await update.message.reply_text(
        f"✅ *New media added for {gender.capitalize()}!* 🎉\n\n"
        f"📝 Total messages: `{len(gdata['messages'])}`\n"
        f"🎬 Total videos: `{len(gdata['videos'])}`",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return ConversationHandler.END

# ---------- /listmedia, /clearmedia, /preview, /settings, /setbuttons, /reset ----------
async def cmd_listmedia(update, context):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    linked = get_linked_chats(user.id)
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
            icon = "👦" if g=="male" else "👧" if g=="female" else "🧑"
            text += f"*{esc(title)}* {icon} {g.capitalize()}: `{msgs}` msgs, `{vids}` vids\n"
        text += "\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_clearmedia(update, context):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    linked = get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Haan, Clear Karo", callback_data="confirm_clear"),
         InlineKeyboardButton("❌ Nahi", callback_data="cancel_clear")]
    ])
    await update.message.reply_text("⚠️ *Sab media clear karna chahte ho?*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)

async def clearmedia_callback(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_clear":
        user = update.effective_user
        linked = get_linked_chats(user.id)
        for chat_id in linked:
            settings = get_settings(chat_id)
            settings["male"] = {"messages": [], "videos": []}
            settings["female"] = {"messages": [], "videos": []}
            settings["unknown"] = {"messages": [], "videos": []}
            save_settings(chat_id, settings)
        await query.edit_message_text("✅ Sab media clear ho gaya!", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.edit_message_text("❌ Cancel.", parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_preview(update, context):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    linked = get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return
    await update.message.reply_text("🔍 Preview bhej raha hoon (DM mein hi)...")
    for chat_id in linked:
        settings = get_settings(chat_id)
        title = settings.get("chat_title", str(chat_id))
        for g in ["male", "female", "unknown"]:
            await update.message.reply_text(f"📌 *{esc(title)} - {g.capitalize()} Preview:*", parse_mode=ParseMode.MARKDOWN_V2)
            await send_welcome(context, update.effective_chat.id, user, g)

async def cmd_settings(update, context):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    linked = get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return
    for chat_id in linked:
        settings = get_settings(chat_id)
        title = settings.get("chat_title", str(chat_id))
        active = "✅ Active" if settings.get("active") else "❌ Inactive"
        btns = len(settings.get("buttons", []))
        text = f"⚙️ *Settings — {esc(title)}*\n\nStatus: {active}\n🔘 Buttons: {btns}\n"
        for g in ["male", "female", "unknown"]:
            msgs = len(settings.get(g, {}).get("messages", []))
            vids = len(settings.get(g, {}).get("videos", []))
            icon = "👦" if g=="male" else "👧" if g=="female" else "🧑"
            text += f"{icon} {g.capitalize()}: `{msgs}` msgs, `{vids}` vids\n"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_setbuttons(update, context):
    if update.effective_chat.type != "private":
        return ConversationHandler.END
    user = update.effective_user
    linked = get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Pehle /connect karo.")
        return ConversationHandler.END
    context.user_data["linked"] = linked
    await update.message.reply_text("🔘 *Inline Button Set Karo*\n\nButton ka *text* type karo:", parse_mode=ParseMode.MARKDOWN_V2)
    return WAITING_BUTTON_TEXT

async def recv_button_text(update, context):
    context.user_data["button_text"] = update.message.text
    await update.message.reply_text("✅ Text noted! Ab button ki *URL* bhejo (http:// or https://):", parse_mode=ParseMode.MARKDOWN_V2)
    return WAITING_BUTTON_URL

async def recv_button_url(update, context):
    url = update.message.text.strip()
    text = context.user_data.get("button_text", "Button")
    if not url.startswith("http"):
        await update.message.reply_text("❌ Valid URL bhejo (http:// ya https://)", parse_mode=ParseMode.MARKDOWN_V2)
        return WAITING_BUTTON_URL
    for chat_id in context.user_data["linked"]:
        settings = get_settings(chat_id)
        settings.setdefault("buttons", []).append({"text": text, "url": url})
        save_settings(chat_id, settings)
    await update.message.reply_text(f"✅ Button added! `{esc(text)}` → {esc(url)}", parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END

async def cmd_reset(update, context):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    linked = get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Haan, Reset Karo", callback_data="confirm_reset"),
         InlineKeyboardButton("❌ Nahi", callback_data="cancel_reset")]
    ])
    await update.message.reply_text("⚠️ *Sab settings delete karna chahte ho?* Ye undo nahi ho sakta.", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)

async def reset_callback(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_reset":
        user = update.effective_user
        linked = get_linked_chats(user.id)
        for chat_id in linked:
            delete_settings(chat_id)
        await query.edit_message_text("✅ Sab reset ho gaya!", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.edit_message_text("❌ Cancel.", parse_mode=ParseMode.MARKDOWN_V2)

async def cancel(update, context):
    await update.message.reply_text("❌ Operation cancel kiya.", parse_mode=ParseMode.MARKDOWN_V2)
    context.user_data.clear()
    return ConversationHandler.END

# ---------- New Member Handler (GROQ Detection) ----------
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
        (ChatMember.LEFT, ChatMember.RESTRICTED)
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

    # GROQ gender detection
    gender = await detect_gender(
        new_member.first_name,
        new_member.last_name or "",
        new_member.username or ""
    )
    logger.info(f"New member: {new_member.first_name} | GROQ gender: {gender}")

    await send_welcome(context, chat_id, new_member, gender)

# ---------- Main ----------
def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Please set BOT_TOKEN environment variable.")
        return
    if not GROQ_API_KEY or GROQ_API_KEY == "YOUR_GROQ_API_KEY_HERE":
        print("❌ Please set GROQ_API_KEY environment variable.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handlers
    male_conv = ConversationHandler(
        entry_points=[CommandHandler("set_male", cmd_set_male)],
        states={
            WAITING_MALE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_gender_msg)],
            WAITING_MALE_VIDEO: [MessageHandler(filters.VIDEO | filters.Document.VIDEO, recv_gender_video), CommandHandler("skip", skip_video)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    female_conv = ConversationHandler(
        entry_points=[CommandHandler("set_female", cmd_set_female)],
        states={
            WAITING_FEMALE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_gender_msg)],
            WAITING_FEMALE_VIDEO: [MessageHandler(filters.VIDEO | filters.Document.VIDEO, recv_gender_video), CommandHandler("skip", skip_video)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    unknown_conv = ConversationHandler(
        entry_points=[CommandHandler("set_unknown", cmd_set_unknown)],
        states={
            WAITING_UNKNOWN_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_gender_msg)],
            WAITING_UNKNOWN_VIDEO: [MessageHandler(filters.VIDEO | filters.Document.VIDEO, recv_gender_video), CommandHandler("skip", skip_video)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    more_conv = ConversationHandler(
        entry_points=[CommandHandler("add_more", cmd_add_more)],
        states={
            WAITING_MORE_GENDER: [CallbackQueryHandler(more_gender_callback, pattern="^more_")],
            WAITING_MORE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_more_msg)],
            WAITING_MORE_VIDEO: [MessageHandler(filters.VIDEO | filters.Document.VIDEO, recv_more_video), CommandHandler("skip", skip_video)],
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
    app.add_handler(CommandHandler("listmedia", cmd_listmedia))
    app.add_handler(CommandHandler("clearmedia", cmd_clearmedia))
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

    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    logger.info("🚀 Bot started with improved gender detection + video confirmation")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
