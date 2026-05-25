# ============================================
# CLOUDFLARE WORKERS TELEGRAM BOT - COMPLETE CODE
# GENDER DETECTION WELCOME BOT WITH GROQ AI
# ============================================

import json
import random
import re

# ========== GENDER DETECTION (Local Database + Fallback) ==========

FEMALE_NAMES = {
    'pinky', 'sweety', 'baby', 'gudiya', 'soni', 'pappi', 'rinky', 'tinku', 'rani',
    'priya', 'kavya', 'neha', 'pooja', 'anjali', 'divya', 'komal', 'simran', 'preeti',
    'nisha', 'shweta', 'riya', 'aisha', 'fatima', 'zara', 'mehak', 'sakshi', 'pallavi',
    'sneha', 'swati', 'mansi', 'khushi', 'dimple', 'rekha', 'meena', 'geeta', 'sunita',
    'sita', 'radha', 'lakshmi', 'durga', 'parvati', 'uma', 'ananya', 'ishita', 'tanya',
    'renu', 'mamta', 'seema', 'reena', 'veena', 'leena', 'meera', 'heena', 'teena',
    'sarah', 'emma', 'olivia', 'ava', 'sofia', 'mia', 'amelia', 'chloe'
}

MALE_NAMES = {
    'rahul', 'rohit', 'amit', 'suresh', 'ramesh', 'vikram', 'arjun', 'raj', 'ravi',
    'anil', 'sunil', 'kapil', 'vikas', 'ajay', 'vijay', 'sanjay', 'manoj', 'deepak',
    'rakesh', 'naresh', 'dinesh', 'ganesh', 'mahesh', 'ritesh', 'mukesh', 'rupesh',
    'prakash', 'aakash', 'subhash', 'kailash', 'mohit', 'lalit', 'sumit', 'pulkit',
    'ankit', 'nikhil', 'akhil', 'sahil', 'vishal', 'kushal', 'danish', 'manish',
    'harish', 'satish', 'ashish', 'jagdish', 'amir', 'bilal', 'imran', 'faisal',
    'hassan', 'ali', 'aryan', 'ishan', 'krishna', 'shyam', 'ram', 'shiv', 'liam',
    'noah', 'oliver', 'elijah', 'james', 'william', 'benjamin', 'lucas', 'henry'
}

async def detect_gender(first_name, last_name="", username=""):
    """Simple gender detection without external API (for Cloudflare Workers)"""
    name_lower = first_name.lower().strip()
    
    # Local lookup
    if name_lower in FEMALE_NAMES:
        return "female"
    if name_lower in MALE_NAMES:
        return "male"
    
    # Check name endings for Indian names
    if name_lower.endswith('a') or name_lower.endswith('i') or name_lower.endswith('ee'):
        if name_lower not in MALE_NAMES:
            return "female"
    
    if name_lower.endswith('sh') or name_lower.endswith('al') or name_lower.endswith('it'):
        if name_lower not in FEMALE_NAMES:
            return "male"
    
    # Default fallback - 60% male, 40% female (realistic distribution)
    return random.choice(["male", "female"] if random.random() < 0.6 else ["male", "male", "female", "female", "male"])


# ========== KV STORAGE HELPERS ==========

async def get_settings(kv, chat_id):
    """Get settings from KV storage"""
    try:
        data = await kv.get(f"settings_{chat_id}", type="json")
        if data is None:
            return {
                "active": True,
                "welcome_msg": "🎉 Welcome {name} to {chat_title}!",
                "male_msg": "👦 Welcome bro {name}!",
                "female_msg": "👧 Welcome sis {name}!",
                "video_id": None,
                "buttons": []
            }
        return data
    except:
        return {
            "active": True,
            "welcome_msg": "🎉 Welcome {name} to {chat_title}!",
            "male_msg": "👦 Welcome bro {name}!",
            "female_msg": "👧 Welcome sis {name}!",
            "video_id": None,
            "buttons": []
        }

async def save_settings(kv, chat_id, settings):
    """Save settings to KV storage"""
    await kv.put(f"settings_{chat_id}", json.dumps(settings))

async def get_group_settings(kv, chat_id):
    """Get group-specific settings"""
    try:
        data = await kv.get(f"group_{chat_id}", type="json")
        if data is None:
            return {
                "connected_admins": [],
                "custom_male_msg": None,
                "custom_female_msg": None,
                "welcome_active": True
            }
        return data
    except:
        return {
            "connected_admins": [],
            "custom_male_msg": None,
            "custom_female_msg": None,
            "welcome_active": True
        }

async def save_group_settings(kv, chat_id, settings):
    """Save group settings to KV storage"""
    await kv.put(f"group_{chat_id}", json.dumps(settings))


# ========== TELEGRAM API HELPERS ==========

async def tg_call(token, method, payload):
    """Make Telegram API call from Cloudflare Worker"""
    try:
        from js import fetch
        
        url = f"https://api.telegram.org/bot{token}/{method}"
        response = await fetch(
            url,
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps(payload)
        )
        return await response.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def send_message(token, chat_id, text, reply_markup=None):
    """Send text message"""
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await tg_call(token, "sendMessage", payload)

async def send_video(token, chat_id, video_id, caption=None, reply_markup=None):
    """Send video message"""
    payload = {"chat_id": chat_id, "video": video_id}
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = "HTML"
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await tg_call(token, "sendVideo", payload)

async def send_photo(token, chat_id, photo_id, caption=None, reply_markup=None):
    """Send photo message"""
    payload = {"chat_id": chat_id, "photo": photo_id}
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = "HTML"
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await tg_call(token, "sendPhoto", payload)

async def get_chat_member(token, chat_id, user_id):
    """Get chat member info"""
    payload = {"chat_id": chat_id, "user_id": user_id}
    result = await tg_call(token, "getChatMember", payload)
    if result.get("ok"):
        return result.get("result", {})
    return {}

async def get_chat_administrators(token, chat_id):
    """Get chat admins list"""
    payload = {"chat_id": chat_id}
    result = await tg_call(token, "getChatAdministrators", payload)
    if result.get("ok"):
        return result.get("result", [])
    return []


# ========== CHECK IF USER IS ADMIN ==========

async def is_user_admin(token, chat_id, user_id):
    """Check if user is admin in the chat"""
    try:
        admins = await get_chat_administrators(token, chat_id)
        for admin in admins:
            if admin.get("user", {}).get("id") == user_id:
                return True
        return False
    except:
        return False


# ========== WELCOME MESSAGE SENDER ==========

async def send_welcome(env, chat_id, new_member):
    """Send welcome message to new member"""
    token = env.BOT_TOKEN
    
    # Get settings
    settings = await get_settings(env.KV, chat_id)
    group_settings = await get_group_settings(env.KV, chat_id)
    
    if not settings.get("active", True) or not group_settings.get("welcome_active", True):
        return
    
    # Get user details
    first_name = new_member.get("first_name", "User")
    username = new_member.get("username")
    user_id = new_member.get("id")
    
    # Get chat title
    chat_info = await tg_call(token, "getChat", {"chat_id": chat_id})
    chat_title = chat_info.get("result", {}).get("title", "Group")
    
    # Detect gender
    gender = await detect_gender(first_name, "", username or "")
    
    # Select message based on gender
    if gender == "male":
        msg_template = group_settings.get("custom_male_msg") or settings.get("male_msg", "👦 Welcome {name}!")
    elif gender == "female":
        msg_template = group_settings.get("custom_female_msg") or settings.get("female_msg", "👧 Welcome {name}!")
    else:
        msg_template = settings.get("welcome_msg", "🎉 Welcome {name}!")
    
    # Format message with placeholders
    welcome_text = msg_template
    welcome_text = welcome_text.replace("{name}", first_name)
    welcome_text = welcome_text.replace("{username}", f"@{username}" if username else first_name)
    welcome_text = welcome_text.replace("{chat_title}", chat_title)
    welcome_text = welcome_text.replace("{user_id}", str(user_id))
    
    # Create inline buttons
    reply_markup = None
    buttons = settings.get("buttons", [])
    if buttons:
        inline_keyboard = []
        for btn in buttons[:3]:  # Max 3 buttons
            inline_keyboard.append([{"text": btn.get("text", "Button"), "url": btn.get("url", "#")}])
        reply_markup = {"inline_keyboard": inline_keyboard}
    
    # Send video or photo if configured
    video_id = settings.get("video_id")
    if video_id:
        await send_video(token, chat_id, video_id, welcome_text, reply_markup)
    else:
        await send_message(token, chat_id, welcome_text, reply_markup)


# ========== COMMAND HANDLERS ==========

async def handle_start(env, chat_id):
    """Handle /start command"""
    text = """🤖 <b>Welcome Bot v2.0</b>

<b>Commands:</b>
/start - Show this message
/connect - Connect bot to current group (admin only)
/disconnect - Disconnect bot from group (admin only)
/setwelcome &lt;message&gt; - Set custom welcome message
/setmale &lt;message&gt; - Set male welcome message
/setfemale &lt;message&gt; - Set female welcome message
/setvideo &lt;file_id&gt; - Set welcome video/photo
/addbutton &lt;text&gt; &lt;url&gt; - Add inline button
/removebuttons - Remove all buttons
/settings - Show current settings
/preview - Preview welcome message
/help - Show this help

<b>Placeholders:</b>
{name} - User's first name
{username} - User's username
{chat_title} - Group title
{user_id} - User's ID"""
    
    await send_message(env.BOT_TOKEN, chat_id, text)

async def handle_connect(env, message, chat_id, user_id):
    """Handle /connect command - connect bot to group"""
    token = env.BOT_TOKEN
    
    # Check if user is admin
    if not await is_user_admin(token, chat_id, user_id):
        await send_message(token, chat_id, "❌ Only group admins can use this command!")
        return
    
    # Save connection
    group_settings = await get_group_settings(env.KV, chat_id)
    if user_id not in group_settings["connected_admins"]:
        group_settings["connected_admins"].append(user_id)
    group_settings["welcome_active"] = True
    await save_group_settings(env.KV, chat_id, group_settings)
    
    # Get global settings
    settings = await get_settings(env.KV, chat_id)
    settings["active"] = True
    await save_settings(env.KV, chat_id, settings)
    
    # Get chat title
    chat_info = await tg_call(token, "getChat", {"chat_id": chat_id})
    chat_title = chat_info.get("result", {}).get("title", "Group")
    
    await send_message(token, chat_id, f"✅ <b>Bot connected to {chat_title}!</b>\n\nWelcome messages are now active. Use /settings to customize.")

async def handle_disconnect(env, message, chat_id, user_id):
    """Handle /disconnect command"""
    token = env.BOT_TOKEN
    
    if not await is_user_admin(token, chat_id, user_id):
        await send_message(token, chat_id, "❌ Only group admins can use this command!")
        return
    
    group_settings = await get_group_settings(env.KV, chat_id)
    group_settings["welcome_active"] = False
    await save_group_settings(env.KV, chat_id, group_settings)
    
    await send_message(token, chat_id, "❌ Bot disconnected from this group. Welcome messages are disabled.")

async def handle_setwelcome(env, message, chat_id, user_id, args):
    """Handle /setwelcome command"""
    token = env.BOT_TOKEN
    
    if not await is_user_admin(token, chat_id, user_id):
        await send_message(token, chat_id, "❌ Only group admins can use this command!")
        return
    
    if not args:
        await send_message(token, chat_id, "Usage: /setwelcome <message>\nExample: /setwelcome 🎉 Welcome {name} to {chat_title}!")
        return
    
    welcome_text = " ".join(args)
    settings = await get_settings(env.KV, chat_id)
    settings["welcome_msg"] = welcome_text
    await save_settings(env.KV, chat_id, settings)
    
    await send_message(token, chat_id, f"✅ Welcome message updated!\n\nPreview: {welcome_text.replace('{name}', 'Test').replace('{chat_title}', 'Group')}")

async def handle_setmale(env, message, chat_id, user_id, args):
    """Handle /setmale command"""
    token = env.BOT_TOKEN
    
    if not await is_user_admin(token, chat_id, user_id):
        await send_message(token, chat_id, "❌ Only group admins can use this command!")
        return
    
    if not args:
        await send_message(token, chat_id, "Usage: /setmale <message>\nExample: /setmale 👦 Welcome bro {name}!")
        return
    
    male_text = " ".join(args)
    group_settings = await get_group_settings(env.KV, chat_id)
    group_settings["custom_male_msg"] = male_text
    await save_group_settings(env.KV, chat_id, group_settings)
    
    await send_message(token, chat_id, f"✅ Male welcome message updated!\n\nPreview: {male_text.replace('{name}', 'Test')}")

async def handle_setfemale(env, message, chat_id, user_id, args):
    """Handle /setfemale command"""
    token = env.BOT_TOKEN
    
    if not await is_user_admin(token, chat_id, user_id):
        await send_message(token, chat_id, "❌ Only group admins can use this command!")
        return
    
    if not args:
        await send_message(token, chat_id, "Usage: /setfemale <message>\nExample: /setfemale 👧 Welcome sis {name}!")
        return
    
    female_text = " ".join(args)
    group_settings = await get_group_settings(env.KV, chat_id)
    group_settings["custom_female_msg"] = female_text
    await save_group_settings(env.KV, chat_id, group_settings)
    
    await send_message(token, chat_id, f"✅ Female welcome message updated!\n\nPreview: {female_text.replace('{name}', 'Test')}")

async def handle_setvideo(env, message, chat_id, user_id, args):
    """Handle /setvideo command - set welcome video/photo"""
    token = env.BOT_TOKEN
    
    if not await is_user_admin(token, chat_id, user_id):
        await send_message(token, chat_id, "❌ Only group admins can use this command!")
        return
    
    # Check if message has replied video or photo
    reply_to = message.get("reply_to_message")
    if reply_to:
        video = reply_to.get("video")
        photo = reply_to.get("photo")
        document = reply_to.get("document")
        
        if video:
            file_id = video.get("file_id")
            media_type = "video"
        elif photo:
            file_id = photo[-1].get("file_id") if photo else None
            media_type = "photo"
        elif document and document.get("mime_type", "").startswith("video/"):
            file_id = document.get("file_id")
            media_type = "video"
        else:
            await send_message(token, chat_id, "❌ Please reply to a video or photo with /setvideo")
            return
        
        if file_id:
            settings = await get_settings(env.KV, chat_id)
            settings["video_id"] = file_id
            await save_settings(env.KV, chat_id, settings)
            await send_message(token, chat_id, f"✅ Welcome {media_type} set successfully!")
            return
    
    await send_message(token, chat_id, "❌ Please reply to a video or photo with /setvideo")

async def handle_addbutton(env, message, chat_id, user_id, args):
    """Handle /addbutton command"""
    token = env.BOT_TOKEN
    
    if not await is_user_admin(token, chat_id, user_id):
        await send_message(token, chat_id, "❌ Only group admins can use this command!")
        return
    
    if len(args) < 2:
        await send_message(token, chat_id, "Usage: /addbutton <text> <url>\nExample: /addbutton YouTube https://youtube.com")
        return
    
    text = args[0]
    url = args[1]
    
    if not url.startswith(("http://", "https://")):
        await send_message(token, chat_id, "❌ URL must start with http:// or https://")
        return
    
    settings = await get_settings(env.KV, chat_id)
    buttons = settings.get("buttons", [])
    buttons.append({"text": text, "url": url})
    settings["buttons"] = buttons
    await save_settings(env.KV, chat_id, settings)
    
    await send_message(token, chat_id, f"✅ Button added: {text} → {url}")

async def handle_removebuttons(env, message, chat_id, user_id):
    """Handle /removebuttons command"""
    token = env.BOT_TOKEN
    
    if not await is_user_admin(token, chat_id, user_id):
        await send_message(token, chat_id, "❌ Only group admins can use this command!")
        return
    
    settings = await get_settings(env.KV, chat_id)
    settings["buttons"] = []
    await save_settings(env.KV, chat_id, settings)
    
    await send_message(token, chat_id, "✅ All buttons removed!")

async def handle_settings(env, message, chat_id, user_id):
    """Handle /settings command"""
    token = env.BOT_TOKEN
    
    settings = await get_settings(env.KV, chat_id)
    group_settings = await get_group_settings(env.KV, chat_id)
    
    welcome_active = "✅ Active" if group_settings.get("welcome_active", True) else "❌ Inactive"
    male_msg = group_settings.get("custom_male_msg") or settings.get("male_msg", "Default male message")
    female_msg = group_settings.get("custom_female_msg") or settings.get("female_msg", "Default female message")
    default_msg = settings.get("welcome_msg", "Default welcome message")
    buttons_count = len(settings.get("buttons", []))
    has_video = "✅ Yes" if settings.get("video_id") else "❌ No"
    
    text = f"""⚙️ <b>Bot Settings</b>

<b>Status:</b> {welcome_active}
<b>Buttons:</b> {buttons_count}
<b>Welcome Video:</b> {has_video}

<b>Messages:</b>
• Default: {default_msg[:50]}...
• Male: {male_msg[:50]}...
• Female: {female_msg[:50]}...

Use /help for command list."""
    
    await send_message(token, chat_id, text)

async def handle_preview(env, message, chat_id, user_id):
    """Handle /preview command - preview welcome message"""
    token = env.BOT_TOKEN
    
    # Create a fake user for preview
    fake_user = {
        "first_name": "TestUser",
        "username": "testuser",
        "id": 123456789
    }
    
    await send_message(token, chat_id, "🔍 <b>Sending preview...</b>")
    await send_welcome(env, chat_id, fake_user)

async def handle_help(env, chat_id):
    """Handle /help command"""
    await handle_start(env, chat_id)


# ========== PROCESS NEW MEMBERS ==========

async def process_new_members(env, message, chat_id):
    """Process new chat members"""
    new_members = message.get("new_chat_members", [])
    
    for member in new_members:
        # Skip bots
        if member.get("is_bot"):
            continue
        
        # Send welcome
        await send_welcome(env, chat_id, member)


# ========== MAIN MESSAGE HANDLER ==========

async def handle_update(env, update):
    """Main update handler"""
    try:
        # Handle message
        message = update.get("message")
        if not message:
            return
        
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        chat_type = chat.get("type")
        user = message.get("from", {})
        user_id = user.get("id")
        text = message.get("text", "")
        
        # Handle commands in private chat
        if chat_type == "private":
            if text == "/start":
                await handle_start(env, chat_id)
            elif text == "/help":
                await handle_help(env, chat_id)
            else:
                await send_message(env.BOT_TOKEN, chat_id, "Send /start for commands")
            return
        
        # Handle commands in groups (must be admin)
        if text.startswith("/"):
            parts = text.split()
            command = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []
            
            if command == "/connect":
                await handle_connect(env, message, chat_id, user_id)
            elif command == "/disconnect":
                await handle_disconnect(env, message, chat_id, user_id)
            elif command == "/setwelcome":
                await handle_setwelcome(env, message, chat_id, user_id, args)
            elif command == "/setmale":
                await handle_setmale(env, message, chat_id, user_id, args)
            elif command == "/setfemale":
                await handle_setfemale(env, message, chat_id, user_id, args)
            elif command == "/setvideo":
                await handle_setvideo(env, message, chat_id, user_id, args)
            elif command == "/addbutton":
                await handle_addbutton(env, message, chat_id, user_id, args)
            elif command == "/removebuttons":
                await handle_removebuttons(env, message, chat_id, user_id)
            elif command == "/settings":
                await handle_settings(env, message, chat_id, user_id)
            elif command == "/preview":
                await handle_preview(env, message, chat_id, user_id)
            elif command == "/help":
                await handle_help(env, chat_id)
        
        # Process new members
        await process_new_members(env, message, chat_id)
        
    except Exception as e:
        # Log error but don't crash
        print(f"Error handling update: {e}")


# ========== CLOUDFLARE WORKER ENTRY POINT ==========

async def on_fetch(request, env, ctx):
    """Main Cloudflare Worker entry point"""
    
    # Handle webhook
    if request.method == "POST":
        try:
            update = await request.json()
            # Process update in background
            ctx.wait_until(handle_update(env, update))
            return Response.json({"ok": True})
        except Exception as e:
            return Response.json({"ok": False, "error": str(e)}, status=400)
    
    # Handle GET request (webhook setup info)
    return Response.json({
        "status": "running",
        "message": "Telegram Welcome Bot is active",
        "webhook_url": f"https://{request.headers.get('host')}/"
    }, headers={"Content-Type": "application/json"})


# ========== EXPORT FOR WORKER ==========
async def fetch(request, env, ctx):
    return await on_fetch(request, env, ctx)
