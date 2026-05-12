import os
import logging
import asyncio

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from ai_gender_detect import detect_gender_ai

# ========== CONFIGURATION ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable not set!")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== WELCOME MESSAGE ==========
def build_welcome_message(member, gender: str) -> str:
    """Beautiful welcome message"""
    
    username = f"@{member.username}" if member.username else member.first_name
    pronoun = "bro" if gender == "male" else ("sis" if gender == "female" else "friend")
    
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
    return msg.strip()

# ========== HANDLERS ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "✨ Bot is active!\n"
        "I'll automatically welcome new members with AI gender detection! 🤖"
    )

async def welcome_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new members joining"""
    
    if not update.message or not update.message.new_chat_members:
        return
    
    for new_member in update.message.new_chat_members:
        # Skip bots
        if new_member.is_bot:
            logger.info(f"Skipping bot: {new_member.first_name}")
            continue
        
        # Detect gender using AI
        name_to_detect = new_member.first_name or ""
        gender = detect_gender_ai(name_to_detect)
        
        logger.info(f"📥 New member: {new_member.first_name} (@{new_member.username}) - Detected: {gender}")
        
        # Create and send welcome message
        welcome_text = build_welcome_message(new_member, gender)
        
        try:
            await update.message.reply_text(welcome_text, parse_mode="Markdown")
            logger.info(f"✅ Welcome sent to {new_member.first_name}")
        except Exception as e:
            logger.error(f"Failed to send: {e}")
            # Send without markdown
            await update.message.reply_text(welcome_text.replace("*", ""))

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Exception: {context.error}")

# ========== MAIN ==========
async def main():
    """Start the bot"""
    
    print("\n" + "="*60)
    print("🤖 CELESTIA WELCOME BOT")
    print("="*60)
    print(f"📱 Bot Token: {'✅ Set' if BOT_TOKEN else '❌ Missing'}")
    print("="*60)
    print("\n📌 Checklist:")
    print("✓ Bot is ADMIN in group")
    print("✓ Privacy mode DISABLED (@BotFather)")
    print("✓ Add a member to test\n")
    
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_handler))
    app.add_error_handler(error_handler)
    
    # Clear existing webhook/updates
    async with app:
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.bot.get_updates(offset=-1, timeout=1)
    
    print("✅ Bot ready! Listening...\n")
    
    # Start polling
    await app.run_polling(allowed_updates=["message", "chat_member"], drop_pending_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")
    except Exception as e:
        print(f"\n❌ Error: {e}")
