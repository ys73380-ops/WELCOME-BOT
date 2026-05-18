"""
🌹 Welcome Bot - Professional Telegram Group Welcome Bot
Features: Gender detection via GROQ API, custom messages, multiple media support
"""

import os
import logging
import random
import json
import re
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ChatMemberHandler,
    ContextTypes, filters, ConversationHandler, CallbackQueryHandler
)
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from groq import Groq
from database import Database

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN   = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")

db = Database("data.json")
groq_client = Groq(api_key=GROQ_API_KEY)

# ─── States for ConversationHandler ─────────────────────────────────────────
WAITING_MALE_MSG   = 1
WAITING_MALE_VIDEO = 2
WAITING_FEMALE_MSG = 3
WAITING_FEMALE_VIDEO = 4
WAITING_BUTTON_TEXT = 5
WAITING_BUTTON_URL  = 6
WAITING_MORE_GENDER = 7
WAITING_MORE_MSG    = 8
WAITING_MORE_VIDEO  = 9

# ─── Gender Detection via GROQ ───────────────────────────────────────────────
async def detect_gender(first_name: str, last_name: str = "", username: str = "") -> str:
    """Use GROQ LLM to detect gender from name. Returns 'male', 'female', or 'unknown'."""
    try:
        full_name = f"{first_name} {last_name}".strip()
        prompt = (
            f"Based on the name '{full_name}' (username: @{username}), determine the gender.\n"
            "Reply with ONLY one word: 'male', 'female', or 'unknown'.\n"
            "Consider Indian, Arabic, English, and international names.\n"
            "If the name is ambiguous or you're not sure, reply 'unknown'."
        )
        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
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

# ─── Helpers ─────────────────────────────────────────────────────────────────
def esc(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    return escape_markdown(text, version=2)

def is_admin(user_id: int, chat_id: int) -> bool:
    """Check if user is configured as admin for this chat."""
    settings = db.get_settings(chat_id)
    return user_id in settings.get("admins", [])

async def check_admin(update: Update, chat_id: int) -> bool:
    """Verify user is admin in the group."""
    user = update.effective_user
    settings = db.get_settings(chat_id)
    if user.id in settings.get("admins", []):
        return True
    await update.message.reply_text("❌ Sirf admins ye command use kar sakte hain.")
    return False

async def send_welcome(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user, gender: str):
    """Send the appropriate welcome message + video to the group."""
    settings = db.get_settings(chat_id)
    gender_data = settings.get(gender) or settings.get("unknown") or {}

    messages = gender_data.get("messages", [])
    videos   = gender_data.get("videos", [])
    buttons  = settings.get("buttons", [])

    if not messages:
        # fallback
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"👋 Welcome {user.first_name}!",
        )
        return

    # Pick random message and video
    msg_template = random.choice(messages)
    video_id     = random.choice(videos) if videos else None

    # Replace placeholders
    name_mention = f"[{user.first_name}](tg://user?id={user.id})"
    msg = msg_template.replace("{name}", user.first_name)
    msg = msg.replace("{mention}", name_mention)
    msg = msg.replace("{username}", f"@{user.username}" if user.username else user.first_name)
    msg = msg.replace("{gender}", "👦 Male" if gender == "male" else "👧 Female" if gender == "female" else "🧑 Member")

    # Build inline keyboard
    keyboard = []
    for btn in buttons:
        keyboard.append([InlineKeyboardButton(btn["text"], url=btn["url"])])
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    try:
        if video_id:
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_id,
                caption=msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
            )
    except Exception as e:
        logger.error(f"Error sending welcome: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"👋 Welcome {user.first_name}!")

# ─── New Member Handler ───────────────────────────────────────────────────────
async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when a new member joins or is approved."""
    result = update.chat_member
    chat_id = result.chat.id

    settings = db.get_settings(chat_id)
    if not settings.get("active", False):
        return

    new_member = result.new_chat_member
    old_member = result.old_chat_member

    # Only trigger on join (pending → member or left → member)
    valid_transitions = [
        (ChatMember.LEFT, ChatMember.MEMBER),
        (ChatMember.BANNED, ChatMember.MEMBER),
        (ChatMember.RESTRICTED, ChatMember.MEMBER),
    ]
    transition = (old_member.status, new_member.status)
    if transition not in valid_transitions:
        return

    user = new_member.user
    if user.is_bot:
        return

    # Detect gender
    gender = await detect_gender(
        user.first_name,
        user.last_name or "",
        user.username or ""
    )
    logger.info(f"New member: {user.first_name} | Gender: {gender}")

    await send_welcome(context, chat_id, user, gender)

# ─── /start Command ───────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != "private":
        await update.message.reply_text("ℹ️ Ye bot DM mein use karo. Pehle group mein /connect karo.")
        return

    text = (
        "🌹 *Welcome Bot* — Simple Setup\n\n"
        "*Pehle group mein /connect use karo\\.*\n"
        "Phir DM mein aake ye commands use kar:\n\n"
        "▪ /set\\_male — male message \\+ video add\n"
        "▪ /set\\_female — female message \\+ video add\n"
        "▪ /add\\_more — aur messages/videos add karo\n"
        "▪ /listmedia — media count dekho\n"
        "▪ /clearmedia — sab media clear karo\n"
        "▪ /preview — test welcome message\n"
        "▪ /settings — current config dekho\n"
        "▪ /setbuttons — inline buttons set karo\n"
        "▪ /reset — sab settings delete karo\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

# ─── /connect Command (in group) ─────────────────────────────────────────────
async def cmd_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("❌ Ye command group mein use karo!")
        return

    # Check if user is group admin
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("❌ Sirf group admins /connect kar sakte hain.")
        return

    settings = db.get_settings(chat.id)
    if user.id not in settings.get("admins", []):
        settings.setdefault("admins", []).append(user.id)
    settings["active"] = True
    settings["chat_title"] = chat.title
    db.save_settings(chat.id, settings)

    await update.message.reply_text(
        f"✅ Bot connected to *{chat.title}*\\!\n"
        f"Ab DM mein [@me](tg://user?id={context.bot.id}) jaake settings karo\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )

# ─── /set_male ConversationHandler ───────────────────────────────────────────
async def cmd_set_male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("❌ DM mein use karo.")
        return ConversationHandler.END

    user = update.effective_user
    linked = db.get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Pehle group mein /connect karo.")
        return ConversationHandler.END

    context.user_data["setting_gender"] = "male"
    context.user_data["linked_chats"] = linked
    await update.message.reply_text(
        "👦 *Male Welcome Message Set Karo*\n\n"
        "Apna welcome message type karo\\.\n"
        "Placeholders use kar sakte ho:\n"
        "`{name}` — member ka naam\n"
        "`{mention}` — clickable mention\n"
        "`{username}` — @username\n"
        "`{gender}` — gender label\n\n"
        "Message exactly jaisa type karoge waisa hi send hoga\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_MALE_MSG

async def recv_male_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_message"] = update.message.text
    await update.message.reply_text(
        "✅ Message saved\\!\n\n"
        "Ab male ke liye *video send karo* \\(ya /skip karo\\)\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_MALE_VIDEO

async def recv_male_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gender = context.user_data.get("setting_gender", "male")
    msg    = context.user_data.get("new_message", "")
    video_id = None

    if update.message.video:
        video_id = update.message.video.file_id
    elif update.message.document and update.message.document.mime_type.startswith("video"):
        video_id = update.message.document.file_id

    for chat_id in context.user_data.get("linked_chats", []):
        settings = db.get_settings(chat_id)
        g_data = settings.setdefault(gender, {"messages": [], "videos": []})
        if msg:
            g_data["messages"].append(msg)
        if video_id:
            g_data["videos"].append(video_id)
        db.save_settings(chat_id, settings)

    count_msg   = len(settings.get(gender, {}).get("messages", []))
    count_video = len(settings.get(gender, {}).get("videos", []))
    await update.message.reply_text(
        f"✅ *Male setup complete\\!*\n"
        f"📝 Messages: `{count_msg}` | 🎥 Videos: `{count_video}`",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return ConversationHandler.END

async def skip_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gender = context.user_data.get("setting_gender", "male")
    msg    = context.user_data.get("new_message", "")

    for chat_id in context.user_data.get("linked_chats", []):
        settings = db.get_settings(chat_id)
        g_data = settings.setdefault(gender, {"messages": [], "videos": []})
        if msg:
            g_data["messages"].append(msg)
        db.save_settings(chat_id, settings)

    await update.message.reply_text("✅ Video skip kiya\\. Message saved\\!", parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END

# ─── /set_female ConversationHandler ─────────────────────────────────────────
async def cmd_set_female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("❌ DM mein use karo.")
        return ConversationHandler.END

    user = update.effective_user
    linked = db.get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Pehle group mein /connect karo.")
        return ConversationHandler.END

    context.user_data["setting_gender"] = "female"
    context.user_data["linked_chats"] = linked
    await update.message.reply_text(
        "👧 *Female Welcome Message Set Karo*\n\n"
        "Apna welcome message type karo\\.\n"
        "Placeholders:\n"
        "`{name}` `{mention}` `{username}` `{gender}`\n\n"
        "Message exactly jaisa type karoge waisa hi send hoga\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_FEMALE_MSG

async def recv_female_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_message"] = update.message.text
    await update.message.reply_text(
        "✅ Message saved\\!\n\nAb female ke liye *video send karo* \\(ya /skip karo\\)\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_FEMALE_VIDEO

async def recv_female_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await recv_male_video(update, context)  # same logic

# ─── /add_more Command ───────────────────────────────────────────────────────
async def cmd_add_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("❌ DM mein use karo.")
        return ConversationHandler.END

    user = update.effective_user
    linked = db.get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Pehle group mein /connect karo.")
        return ConversationHandler.END

    context.user_data["linked_chats"] = linked
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👦 Male", callback_data="more_male"),
         InlineKeyboardButton("👧 Female", callback_data="more_female")]
    ])
    await update.message.reply_text(
        "➕ *Aur Media/Message Add Karo*\n\nKiske liye add karna hai?",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    return WAITING_MORE_GENDER

async def more_gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gender = "male" if query.data == "more_male" else "female"
    context.user_data["setting_gender"] = gender
    await query.edit_message_text(
        f"Type karo naya {'👦 male' if gender == 'male' else '👧 female'} *welcome message*\\:",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_MORE_MSG

async def recv_more_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_message"] = update.message.text
    await update.message.reply_text(
        "✅ Message noted\\! Ab *video send karo* \\(ya /skip karo\\)\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_MORE_VIDEO

async def recv_more_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await recv_male_video(update, context)

# ─── /listmedia Command ──────────────────────────────────────────────────────
async def cmd_listmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    user = update.effective_user
    linked = db.get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return

    text = "📊 *Media Count*\n\n"
    for chat_id in linked:
        settings = db.get_settings(chat_id)
        title = settings.get("chat_title", str(chat_id))
        m_msgs   = len(settings.get("male", {}).get("messages", []))
        m_vids   = len(settings.get("male", {}).get("videos", []))
        f_msgs   = len(settings.get("female", {}).get("messages", []))
        f_vids   = len(settings.get("female", {}).get("videos", []))
        text += (
            f"*{esc(title)}*\n"
            f"👦 Male: `{m_msgs}` msgs, `{m_vids}` videos\n"
            f"👧 Female: `{f_msgs}` msgs, `{f_vids}` videos\n\n"
        )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

# ─── /clearmedia Command ─────────────────────────────────────────────────────
async def cmd_clearmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    user = update.effective_user
    linked = db.get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Haan, Clear Karo", callback_data="confirm_clear"),
         InlineKeyboardButton("❌ Nahi", callback_data="cancel_clear")]
    ])
    await update.message.reply_text(
        "⚠️ *Sab media clear karna chahte ho?*\nYe undo nahi ho sakta\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )

async def clearmedia_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_clear":
        user = update.effective_user
        linked = db.get_linked_chats(user.id)
        for chat_id in linked:
            settings = db.get_settings(chat_id)
            settings["male"] = {"messages": [], "videos": []}
            settings["female"] = {"messages": [], "videos": []}
            db.save_settings(chat_id, settings)
        await query.edit_message_text("✅ Sab media clear ho gaya\\!", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.edit_message_text("❌ Cancel kiya\\.", parse_mode=ParseMode.MARKDOWN_V2)

# ─── /preview Command ────────────────────────────────────────────────────────
async def cmd_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    user = update.effective_user
    linked = db.get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return

    await update.message.reply_text("🔍 Preview bhej raha hoon DM mein hi...")
    for chat_id in linked:
        settings = db.get_settings(chat_id)
        # Preview as male
        await update.message.reply_text(f"👦 *Male Preview:*", parse_mode=ParseMode.MARKDOWN_V2)
        await send_welcome(context, update.effective_chat.id, user, "male")
        # Preview as female
        await update.message.reply_text(f"👧 *Female Preview:*", parse_mode=ParseMode.MARKDOWN_V2)
        await send_welcome(context, update.effective_chat.id, user, "female")

# ─── /settings Command ───────────────────────────────────────────────────────
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    user = update.effective_user
    linked = db.get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return

    for chat_id in linked:
        settings = db.get_settings(chat_id)
        title    = settings.get("chat_title", str(chat_id))
        active   = "✅ Active" if settings.get("active") else "❌ Inactive"
        m_msgs   = len(settings.get("male", {}).get("messages", []))
        m_vids   = len(settings.get("male", {}).get("videos", []))
        f_msgs   = len(settings.get("female", {}).get("messages", []))
        f_vids   = len(settings.get("female", {}).get("videos", []))
        btns     = len(settings.get("buttons", []))

        text = (
            f"⚙️ *Settings — {esc(title)}*\n\n"
            f"Status: {active}\n"
            f"👦 Male: `{m_msgs}` msgs, `{m_vids}` videos\n"
            f"👧 Female: `{f_msgs}` msgs, `{f_vids}` videos\n"
            f"🔘 Buttons: `{btns}`\n"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

# ─── /setbuttons ConversationHandler ─────────────────────────────────────────
async def cmd_setbuttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return ConversationHandler.END

    user = update.effective_user
    linked = db.get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Pehle group mein /connect karo.")
        return ConversationHandler.END

    context.user_data["linked_chats"] = linked
    await update.message.reply_text(
        "🔘 *Inline Button Set Karo*\n\n"
        "Button ka *text* type karo \\(jo button pe dikhega\\)\\:",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_BUTTON_TEXT

async def recv_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["button_text"] = update.message.text
    await update.message.reply_text(
        "✅ Text noted\\! Ab button ki *URL* bhejo\\:",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return WAITING_BUTTON_URL

async def recv_button_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url  = update.message.text.strip()
    text = context.user_data.get("button_text", "Button")

    if not url.startswith("http"):
        await update.message.reply_text("❌ Valid URL bhejo \\(http:// ya https://\\)", parse_mode=ParseMode.MARKDOWN_V2)
        return WAITING_BUTTON_URL

    for chat_id in context.user_data.get("linked_chats", []):
        settings = db.get_settings(chat_id)
        settings.setdefault("buttons", []).append({"text": text, "url": url})
        db.save_settings(chat_id, settings)

    await update.message.reply_text(
        f"✅ Button added\\!\n`{esc(text)}` → {esc(url)}",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return ConversationHandler.END

# ─── /reset Command ──────────────────────────────────────────────────────────
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    user = update.effective_user
    linked = db.get_linked_chats(user.id)
    if not linked:
        await update.message.reply_text("❌ Koi group connected nahi.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Haan, Reset Karo", callback_data="confirm_reset"),
         InlineKeyboardButton("❌ Nahi", callback_data="cancel_reset")]
    ])
    await update.message.reply_text(
        "⚠️ *Sab settings delete karna chahte ho?*\nYe undo nahi ho sakta\\!",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )

async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_reset":
        user = update.effective_user
        linked = db.get_linked_chats(user.id)
        for chat_id in linked:
            db.delete_settings(chat_id)
        await query.edit_message_text("✅ Sab reset ho gaya\\!", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.edit_message_text("❌ Reset cancel kiya\\.", parse_mode=ParseMode.MARKDOWN_V2)

# ─── Cancel Handler ───────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancel kiya\\.", parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Male setup conversation
    male_conv = ConversationHandler(
        entry_points=[CommandHandler("set_male", cmd_set_male)],
        states={
            WAITING_MALE_MSG:   [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_male_msg)],
            WAITING_MALE_VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, recv_male_video),
                CommandHandler("skip", skip_video),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True, per_chat=True,
    )

    # Female setup conversation
    female_conv = ConversationHandler(
        entry_points=[CommandHandler("set_female", cmd_set_female)],
        states={
            WAITING_FEMALE_MSG:   [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_female_msg)],
            WAITING_FEMALE_VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, recv_female_video),
                CommandHandler("skip", skip_video),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True, per_chat=True,
    )

    # Add more conversation
    more_conv = ConversationHandler(
        entry_points=[CommandHandler("add_more", cmd_add_more)],
        states={
            WAITING_MORE_GENDER: [CallbackQueryHandler(more_gender_callback, pattern="^more_")],
            WAITING_MORE_MSG:    [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_more_msg)],
            WAITING_MORE_VIDEO:  [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, recv_more_video),
                CommandHandler("skip", skip_video),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True, per_chat=True,
    )

    # Buttons conversation
    button_conv = ConversationHandler(
        entry_points=[CommandHandler("setbuttons", cmd_setbuttons)],
        states={
            WAITING_BUTTON_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_button_text)],
            WAITING_BUTTON_URL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_button_url)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True, per_chat=True,
    )

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("connect", cmd_connect))
    app.add_handler(CommandHandler("listmedia", cmd_listmedia))
    app.add_handler(CommandHandler("clearmedia", cmd_clearmedia))
    app.add_handler(CommandHandler("preview", cmd_preview))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(male_conv)
    app.add_handler(female_conv)
    app.add_handler(more_conv)
    app.add_handler(button_conv)

    # Callback queries
    app.add_handler(CallbackQueryHandler(clearmedia_callback, pattern="^(confirm|cancel)_clear$"))
    app.add_handler(CallbackQueryHandler(reset_callback, pattern="^(confirm|cancel)_reset$"))

    # New member handler (requires allowed_updates=["chat_member"])
    app.add_handler(ChatMemberHandler(on_new_member, ChatMemberHandler.CHAT_MEMBER))

    logger.info("🌹 Welcome Bot started!")
    app.run_polling(allowed_updates=["message", "chat_member", "callback_query"])

if __name__ == "__main__":
    main()
