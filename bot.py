import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from ai_gender_detect import detect_gender_ai as detect_gender

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")


def build_welcome_message(member) -> str:
    """
    2nd image jaisa clean welcome format.
    Sirf yahan changes karo apne group ke hisab se.
    """

    # ── Member details ──────────────────────────────────────
    username  = f"@{member.username}" if member.username else member.first_name
    gender    = detect_gender(member.first_name or "")
    pronoun   = "bro" if gender == "male" else ("sis" if gender == "female" else "friend")

    # ══════════════════════════════════════════════════════
    #   WELCOME MESSAGE FORMAT — YAHAN EDIT KARO
    # ══════════════════════════════════════════════════════
    msg = f"""
✦ *NOT JUST A CHAT GROUP — SAFE VIBE COMMUNITY* 🐾

🔔 *Join Now* — @celestiaagc

✦ *Celestia <//> *

━━━━━━━━━━━━━━━━━━━━━

👋 Hey {username} !
Welcome to the family, {pronoun}! 🎉

━━━━━━━━━━━━━━━━━━━━━

🐾 Make New Friends
🎧 24x7 Active Voice - Chat
🐾 Safe For Girls {{No Abuse}}
🎵 Listen To Songs - Play Video/Movies Play Games 🐾✦

━━━━━━━━━━━━━━━━━━━━━

🤝 Clean Talks ~ Positive Vibes

━━━━━━━━━━━━━━━━━━━━━

👉 *Safe & active group chahiye?*
🌸 *JOIN RIGHT NOW* 🌸

"""
    # ══════════════════════════════════════════════════════
    return msg.strip()


async def welcome_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Naya member join kare toh ye trigger hoga."""
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue  # bots ko welcome nahi karna
        text = build_welcome_message(member)
        await update.message.reply_text(text, parse_mode="Markdown")


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_handler)
    )
    print("Bot running... (Ctrl+C to stop)")
    app.run_polling()
