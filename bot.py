import os
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Load environment variables
load_dotenv()

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not found in .env file!")
    exit(1)

# Database file
DATABASE_FILE = 'videos.json'

# Video database structure
video_database = {
    'girls': [],  # List of {file_id, caption, added_by, added_at}
    'boys': []
}

# Welcome settings
welcome_settings = {
    'girls': {
        'message': "🌸 Welcome {name} to the group! 🎉\n\nYou have been identified as a Female.\nEnjoy your stay!",
        'video_file_id': None
    },
    'boys': {
        'message': "🔥 Welcome {name} to the group! 🎉\n\nYou have been identified as a Male.\nEnjoy your stay!",
        'video_file_id': None
    }
}

# Admin session storage
admin_session = {}

# Load database
def load_database():
    global video_database
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, 'r') as f:
                video_database = json.load(f)
            print("✅ Database loaded")
            print(f"📹 Girls videos: {len(video_database.get('girls', []))}")
            print(f"📹 Boys videos: {len(video_database.get('boys', []))}")
        except Exception as e:
            print(f"Error loading database: {e}")
    else:
        save_database()

def save_database():
    try:
        with open(DATABASE_FILE, 'w') as f:
            json.dump(video_database, f, indent=2)
        print("💾 Database saved")
    except Exception as e:
        print(f"Error saving database: {e}")

# Check if user is group admin
async def is_group_admin(update: Update, user_id: int) -> bool:
    try:
        chat_member = await update.effective_chat.get_member(user_id)
        return chat_member.status in ['administrator', 'creator']
    except:
        return False

# Send welcome videos
async def send_welcome_videos(context: ContextTypes.DEFAULT_TYPE, user_id: int, gender: str):
    videos = video_database.get(gender, [])
    
    if not videos:
        return False
    
    try:
        for i, video in enumerate(videos):
            caption = video['caption']
            if len(videos) > 1:
                caption += f"\n\n📹 Video {i+1}/{len(videos)}"
            
            await context.bot.send_video(
                chat_id=user_id,
                video=video['file_id'],
                caption=caption,
                parse_mode='Markdown'
            )
            
            if i < len(videos) - 1:
                await asyncio.sleep(0.5)
        return True
    except Exception as e:
        print(f"Error sending videos: {e}")
        return False

# ============================================
# COMMAND HANDLERS
# ============================================

# /start command
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👩 Set Welcome for GIRLS", callback_data='admin_set_girls')],
        [InlineKeyboardButton("👨 Set Welcome for BOYS", callback_data='admin_set_boys')],
        [InlineKeyboardButton("📹 View Settings", callback_data='admin_view_settings')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎉 *Welcome Bot Activated!* 🎉\n\n"
        "I will welcome new members with video + message.\n\n"
        "*Setup Instructions:*\n"
        "1️⃣ Click a button below to set welcome for GIRLS\n"
        "2️⃣ Send a video (optional) + welcome message\n"
        "3️⃣ Repeat for BOYS\n\n"
        "*Note:* Only group admins can change settings.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# /setup command (group only)
async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    
    if chat_type in ['private']:
        await update.message.reply_text("❌ Use this command in the GROUP where I am added!")
        return
    
    if not await is_group_admin(update, update.effective_user.id):
        await update.message.reply_text("❌ *Access Denied!*\nOnly group admins can use this command.", parse_mode='Markdown')
        return
    
    keyboard = [
        [InlineKeyboardButton("👩 Set Welcome for GIRLS", callback_data='admin_set_girls')],
        [InlineKeyboardButton("👨 Set Welcome for BOYS", callback_data='admin_set_boys')],
        [InlineKeyboardButton("📹 View Current Settings", callback_data='admin_view_settings')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚙️ *Welcome Bot Setup*\n\n"
        "Click a button below to configure welcome messages and videos for new members.\n\n"
        "Welcome will be sent directly in this GROUP!",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# /settings command
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ['private']:
        await update.message.reply_text("❌ Use this command in the GROUP!")
        return
    
    if not await is_group_admin(update, update.effective_user.id):
        await update.message.reply_text("❌ Only group admins can view settings!", parse_mode='Markdown')
        return
    
    msg = "📹 *CURRENT WELCOME SETTINGS*\n\n"
    msg += f"👩 *GIRLS:*\n"
    msg += f"📝 Message: {welcome_settings['girls']['message'][:80]}...\n"
    msg += f"🎬 Video: {'✅ SET' if welcome_settings['girls']['video_file_id'] else '❌ NOT SET'}\n\n"
    msg += f"👨 *BOYS:*\n"
    msg += f"📝 Message: {welcome_settings['boys']['message'][:80]}...\n"
    msg += f"🎬 Video: {'✅ SET' if welcome_settings['boys']['video_file_id'] else '❌ NOT SET'}\n\n"
    msg += f"Use /setup to change settings."
    
    await update.message.reply_text(msg, parse_mode='Markdown')

# /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = False
    if update.effective_chat.type not in ['private']:
        is_admin = await is_group_admin(update, update.effective_user.id)
    
    help_msg = "🤖 *WELCOME BOT HELP*\n\n"
    help_msg += "*How it works:*\n"
    help_msg += "1️⃣ When someone joins the group\n"
    help_msg += "2️⃣ Bot asks for gender\n"
    help_msg += "3️⃣ User selects GIRL or BOY\n"
    help_msg += "4️⃣ Bot sends welcome video + message in GROUP\n\n"
    
    help_msg += "*Admin Commands (Group only):*\n"
    help_msg += "/setup - Configure welcome settings\n"
    help_msg += "/settings - View current settings\n"
    help_msg += "/help - Show this message\n\n"
    
    help_msg += "*Setup Steps:*\n"
    help_msg += "1️⃣ Type /setup in group\n"
    help_msg += "2️⃣ Click 'Set Welcome for GIRLS'\n"
    help_msg += "3️⃣ Send welcome message (use {name} for member name)\n"
    help_msg += "4️⃣ Send a welcome video (optional) or type /skip\n"
    help_msg += "5️⃣ Repeat for BOYS\n\n"
    
    help_msg += "⚠️ *Make me ADMIN in the group for best results!*"
    
    await update.message.reply_text(help_msg, parse_mode='Markdown')

# /skip command
async def skip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in admin_session:
        await update.message.reply_text("❌ You are not in setup mode! Use /setup first.")
        return
    
    session = admin_session[user_id]
    
    if session['step'] == 'awaiting_video':
        gender = session['gender']
        welcome_settings[gender]['video_file_id'] = None
        
        del admin_session[user_id]
        
        await update.message.reply_text(
            f"✅ *Welcome setup COMPLETE for {gender.upper()}!*\n\n"
            f"📝 Message: {welcome_settings[gender]['message']}\n"
            f"🎬 Video: NOT SET (skipped)\n\n"
            f"Now when a {gender} joins the group, they will see the welcome message.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Use /skip after setting the message!")

# ============================================
# CALLBACK QUERY HANDLERS
# ============================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Check if user is admin (for admin actions)
    if query.data.startswith('admin_'):
        # For group chats, verify admin status
        if query.message.chat.type not in ['private']:
            if not await is_group_admin(update, user_id):
                await query.edit_message_text("❌ Only group admins can change settings!")
                return
    
    if query.data == 'admin_set_girls':
        admin_session[user_id] = {'gender': 'girls', 'step': 'awaiting_message'}
        
        await query.edit_message_text(
            "👩 *Setting up WELCOME for GIRLS*\n\n"
            "Send me the welcome message you want to show when a girl joins.\n\n"
            "*Available placeholders:*\n"
            "{name} - Member's first name\n"
            "{username} - Member's username\n"
            "{mention} - Mention the member\n\n"
            "*Example:*\n"
            '🌸 "Welcome {name}! Happy to have you here!"\n\n'
            "Send your message now 👇",
            parse_mode='Markdown'
        )
    
    elif query.data == 'admin_set_boys':
        admin_session[user_id] = {'gender': 'boys', 'step': 'awaiting_message'}
        
        await query.edit_message_text(
            "👨 *Setting up WELCOME for BOYS*\n\n"
            "Send me the welcome message you want to show when a boy joins.\n\n"
            "*Available placeholders:*\n"
            "{name} - Member's first name\n"
            "{username} - Member's username\n"
            "{mention} - Mention the member\n\n"
            "*Example:*\n"
            '🔥 "Welcome {name}! Glad to see you here!"\n\n'
            "Send your message now 👇",
            parse_mode='Markdown'
        )
    
    elif query.data == 'admin_view_settings':
        msg = "📹 *CURRENT WELCOME SETTINGS*\n\n"
        msg += f"👩 *GIRLS:*\n"
        msg += f"📝 Message: {welcome_settings['girls']['message'][:80]}...\n"
        msg += f"🎬 Video: {'✅ SET' if welcome_settings['girls']['video_file_id'] else '❌ NOT SET'}\n\n"
        msg += f"👨 *BOYS:*\n"
        msg += f"📝 Message: {welcome_settings['boys']['message'][:80]}...\n"
        msg += f"🎬 Video: {'✅ SET' if welcome_settings['boys']['video_file_id'] else '❌ NOT SET'}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("✏️ Edit GIRLS", callback_data='admin_set_girls')],
            [InlineKeyboardButton("✏️ Edit BOYS", callback_data='admin_set_boys')],
            [InlineKeyboardButton("🗑️ Clear All", callback_data='admin_clear_all')],
            [InlineKeyboardButton("❌ Close", callback_data='admin_close')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    elif query.data == 'admin_clear_all':
        welcome_settings['girls']['message'] = "🌸 Welcome {name}!"
        welcome_settings['girls']['video_file_id'] = None
        welcome_settings['boys']['message'] = "🔥 Welcome {name}!"
        welcome_settings['boys']['video_file_id'] = None
        
        await query.edit_message_text(
            "✅ *All welcome settings have been cleared!*\n\n"
            "Use the buttons below to set new welcome messages and videos.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👩 Set GIRLS Welcome", callback_data='admin_set_girls')],
                [InlineKeyboardButton("👨 Set BOYS Welcome", callback_data='admin_set_boys')]
            ])
        )
    
    elif query.data == 'admin_close':
        await query.delete_message()
    
    # Gender selection callback (when new member joins)
    elif query.data.startswith('welcome_'):
        parts = query.data.split('_')
        gender = parts[1]
        target_user_id = int(parts[2])
        user_id = query.from_user.id
        
        if user_id != target_user_id:
            await query.answer("❌ This welcome is not for you!", show_alert=True)
            return
        
        await query.answer(f"✅ Welcome {'Girl' if gender == 'girls' else 'Boy'}!")
        
        # Prepare welcome message
        name = query.from_user.first_name
        username = query.from_user.username or ''
        mention = f"@{username}" if username else name
        
        welcome_message = welcome_settings[gender]['message']
        welcome_message = welcome_message.replace('{name}', name)
        welcome_message = welcome_message.replace('{username}', username)
        welcome_message = welcome_message.replace('{mention}', mention)
        
        video_file_id = welcome_settings[gender]['video_file_id']
        
        # Delete the selection message
        try:
            await query.delete_message()
        except:
            pass
        
        # Send welcome in the group
        if video_file_id:
            await query.message.reply_video(
                video=video_file_id,
                caption=welcome_message,
                parse_mode='Markdown'
            )
        else:
            await query.message.reply_text(welcome_message, parse_mode='Markdown')
        
        # Send confirmation
        await query.message.reply_text(
            f"✅ *{name}*, you have been welcomed as a {'🌸 Girl' if gender == 'girls' else '🔥 Boy'}!\n"
            f"Enjoy your time in the group! 🎉",
            parse_mode='Markdown'
        )

# ============================================
# MESSAGE HANDLERS
# ============================================

# Handle text messages (for admin setup)
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in admin_session:
        return
    
    session = admin_session[user_id]
    
    if session['step'] == 'awaiting_message':
        gender = session['gender']
        welcome_settings[gender]['message'] = update.message.text
        
        admin_session[user_id] = {'gender': gender, 'step': 'awaiting_video'}
        
        await update.message.reply_text(
            f"✅ *Message saved for {gender.upper()}!*\n\n"
            f"📝 Your message:\n\"{update.message.text}\"\n\n"
            f"Now send me a WELCOME VIDEO (optional) for {gender.upper()}.\n\n"
            f"• Send a video to set it\n"
            f"• Or type /skip to continue without video",
            parse_mode='Markdown'
        )

# Handle video messages (for admin setup)
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in admin_session:
        return
    
    session = admin_session[user_id]
    
    if session['step'] == 'awaiting_video':
        gender = session['gender']
        video_file_id = update.message.video.file_id
        welcome_settings[gender]['video_file_id'] = video_file_id
        
        # Also save to database for multiple videos support
        video_database[gender].append({
            'file_id': video_file_id,
            'caption': welcome_settings[gender]['message'],
            'added_by': update.effective_user.first_name,
            'added_at': datetime.now().isoformat()
        })
        save_database()
        
        del admin_session[user_id]
        
        await update.message.reply_text(
            f"✅ *Welcome setup COMPLETE for {gender.upper()}!*\n\n"
            f"📝 Message: {welcome_settings[gender]['message']}\n"
            f"🎬 Video: ✅ SET\n\n"
            f"Now when a {gender} joins the group, they will see this welcome!",
            parse_mode='Markdown'
        )

# Handle new chat members
async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue
        
        user_id = member.id
        name = member.first_name or 'User'
        
        keyboard = [
            [
                InlineKeyboardButton("👩 I am a GIRL / Female", callback_data=f'welcome_girls_{user_id}'),
                InlineKeyboardButton("👨 I am a BOY / Male", callback_data=f'welcome_boys_{user_id}')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎉 *Welcome to the group, {name}!* 🎉\n\n"
            f"Please tell us your gender to get a special welcome message:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

# ============================================
# MAIN FUNCTION
# ============================================

def main():
    print("\n🤖 Telegram Welcome Bot Started!")
    print("=====================================")
    print(f"📹 Girls videos: {len(video_database.get('girls', []))}")
    print(f"📹 Boys videos: {len(video_database.get('boys', []))}")
    print("=====================================\n")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("setup", setup_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("skip", skip_command))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    
    # Start bot
    print("✅ Bot is running... Press Ctrl+C to stop\n")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
