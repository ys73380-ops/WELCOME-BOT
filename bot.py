import os
import logging
import random
import requests
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)
from pymongo import MongoClient

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== CONFIG =====================
BOT_TOKEN = "8634101836:AAGzYMAtCVYf4KaG_pq15T2q_snOgR1RWbs"
GROQ_API_KEY = "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"
MONGO_URL = "mongodb+srv://sys73380_db_uer:hUDwAON8eE8RvG2A@cluster0.vek5qdm.mongodb.net/?appName=Cluster0"

# ===================== MONGODB =====================
try:
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    client.server_info()
    db = client["welcomebot"]
    settings_col = db["settings"]
    group_col = db["groups"]
    logger.info("✅ MongoDB connected!")
except Exception as e:
    logger.error(f"❌ MongoDB error: {e}")
    db = None

# ===================== FLASK =====================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot is running!", 200

@flask_app.route("/ping")
def ping():
    return "pong", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=8080, debug=False)

# ===================== GENDER DETECTION =====================
FEMALE_NAMES = {
    'pinky','sweety','baby','gudiya','soni','pappi','rinky','tinku','rani',
    'priya','kavya','neha','pooja','anjali','divya','komal','simran','preeti',
    'nisha','shweta','riya','aisha','fatima','zara','mehak','sakshi','pallavi',
    'sneha','swati','mansi','khushi','dimple','rekha','meena','geeta','sunita',
    'sita','radha','lakshmi','durga','parvati','uma','ananya','ishita','tanya',
    'renu','mamta','seema','reena','veena','leena','meera','heena','teena',
    'sarah','emma','olivia','ava','sofia','mia','amelia','chloe','zoya','sana',
    'iqra','meher','alia','kajal','sri','devi','deepthi','spandana','navya',
    'sindhu','bindhu','swapna','jyothi','jyoti','mamatha','savitha','savita',
    'kavitha','geetha','chitra','vani','rohini','saritha',
    'varsha','prathima','lavanya','bhargavi','soumya','rashmi','soundarya'
}

MALE_NAMES = {
    'rahul','rohit','amit','suresh','ramesh','vikram','arjun','raj','ravi',
    'anil','sunil','kapil','vikas','ajay','vijay','sanjay','manoj','deepak',
    'rakesh','naresh','dinesh','ganesh','mahesh','ritesh','mukesh','rupesh',
    'prakash','aakash','subhash','kailash','mohit','lalit','sumit','pulkit',
    'ankit','nikhil','akhil','sahil','vishal','kushal','danish','manish',
    'harish','satish','ashish','jagdish','amir','bilal','imran','faisal',
    'hassan','ali','aryan','ishan','krishna','shyam','ram','shiv','liam',
    'noah','oliver','elijah','james','william','benjamin','lucas','henry',
    'rajesh','mahendra','sachin','sharma','verma','gupta','singh','khan',
    'ansari','nair','menon','pillai','reddy','naidu','babu','raju','teja',
    'veera','rambabu','varma','sai','prasad'
}

def detect_gender(first_name, username=""):
    name = first_name.lower().strip()
    if name in FEMALE_NAMES:
        return "female"
    if name in MALE_NAMES:
        return "male"
    if name.endswith(('a','i','ee','u')):
        if name not in MALE_NAMES:
            return "female"
    if name.endswith(('sh','al','it','raj')):
        if name not in FEMALE_NAMES:
            return "male"
    if username:
        uname = username.lower()
        if any(w in uname for w in ['girl','miss','sweety','baby']):
            return "female"
        if any(w in uname for w in ['boy','mr','master']):
            return "male"
    return "male" if random.random() < 0.55 else "female"

# ===================== GROQ AI =====================
def call_groq_ai(prompt):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "mixtral-8x7b-32768",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant for a Telegram welcome bot."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 150
        }
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        data = res.json()
        if "choices" in data and data["choices"]:
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Groq error: {e}")
    return None

def ai_detect_gender(first_name, username=""):
    prompt = f'Based on the name "{first_name}"{"and username " + username if username else ""}, is this person male or female? Return ONLY one word: male or female.'
    result = call_groq_ai(prompt)
    if result:
        result = result.lower()
        if "female" in result:
            return "female"
        if "male" in result:
            return "male"
    return None

def ai_generate_message(first_name, gender, chat_title):
    emoji = "👦" if gender == "male" else "👧"
    word = "brother" if gender == "male" else "sister"
    prompt = f'Write a short welcome message. Name: {first_name}, Gender: {gender}, Group: {chat_title}. Use {emoji} emoji, call them {word}. Max 100 chars. Return only the message.'
    result = call_groq_ai(prompt)
    if result and 10 < len(result) < 200:
        return result
    return None

# ===================== DEFAULT VALUES =====================
DEFAULT_SETTINGS = {
    "active": True, "ai_enabled": False,
    "male_msg": "Welcome brother {name}! 👦",
    "female_msg": "Welcome sister {name}! 👧",
    "video_id": None, "photo_id": None, "media_type": None,
}
DEFAULT_GROUP = {
    "connected_admins": [], "welcome_active": True,
    "custom_male_msg": None, "custom_female_msg": None
}

# ===================== DB HELPERS =====================
def get_settings(chat_id):
    if db is None:
        return DEFAULT_SETTINGS.copy()
    try:
        doc = settings_col.find_one({"chat_id": chat_id})
        if not doc:
            return DEFAULT_SETTINGS.copy()
        doc.pop("_id", None)
        return doc
    except Exception as e:
        logger.error(f"get_settings error: {e}")
        return DEFAULT_SETTINGS.copy()

def save_settings(chat_id, settings):
    if db is None:
        return
    try:
        settings_col.update_one(
            {"chat_id": chat_id},
            {"$set": {**settings, "chat_id": chat_id}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"save_settings error: {e}")

def get_group(chat_id):
    if db is None:
        return DEFAULT_GROUP.copy()
    try:
        doc = group_col.find_one({"chat_id": chat_id})
        if not doc:
            return DEFAULT_GROUP.copy()
        doc.pop("_id", None)
        return doc
    except Exception as e:
        logger.error(f"get_group error: {e}")
        return DEFAULT_GROUP.copy()

def save_group(chat_id, group):
    if db is None:
        return
    try:
        group_col.update_one(
            {"chat_id": chat_id},
            {"$set": {**group, "chat_id": chat_id}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"save_group error: {e}")

def get_user_groups(user_id):
    if db is None:
        return []
    try:
        docs = list(group_col.find({"connected_admins": user_id}))
        return docs
    except Exception as e:
        logger.error(f"get_user_groups error: {e}")
        return []

# ===================== MENUS =====================
async def show_main_menu(update_or_query, context, edit=False):
    if hasattr(update_or_query, 'effective_user'):
        user_id = update_or_query.effective_user.id
    else:
        user_id = update_or_query.from_user.id

    groups = get_user_groups(user_id)

    if not groups:
        text = (
            "<b>🤖 Welcome Bot</b>\n\n"
            "Koi group connected nahi hai abhi.\n\n"
            "👉 Apne group mein jao\n"
            "👉 Bot ko <b>ADMIN</b> banao\n"
            "👉 <code>/connect</code> command use karo\n"
            "👉 DM button aayega — click karo\n\n"
            "Phir yahan sab settings kar sakte ho! ✅"
        )
        keyboard = []
    else:
        text = "<b>🤖 Welcome Bot</b>\n\nApna group select karo:"
        keyboard = []
        for g in groups:
            gid = g.get("chat_id")
            try:
                chat = await context.bot.get_chat(gid)
                gname = chat.title or str(gid)
            except:
                gname = f"Group {gid}"
            status = "✅" if g.get("welcome_active") else "❌"
            keyboard.append([InlineKeyboardButton(f"{status} {gname}", callback_data=f"group_{gid}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if edit:
        await update_or_query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update_or_query.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def show_group_menu(query, context, group_id):
    try:
        chat = await context.bot.get_chat(group_id)
        gname = chat.title or str(group_id)
    except:
        gname = str(group_id)

    settings = get_settings(group_id)
    grp = get_group(group_id)

    status = "✅ Active" if grp.get("welcome_active") else "❌ Inactive"
    ai_status = "🤖 ON" if settings.get("ai_enabled") else "OFF"
    media = settings.get("media_type") or "None"
    male_msg = str(grp.get('custom_male_msg') or settings.get('male_msg', ''))[:50]
    female_msg = str(grp.get('custom_female_msg') or settings.get('female_msg', ''))[:50]

    text = (
        f"<b>⚙️ {gname}</b>\n\n"
        f"📊 Status: {status}\n"
        f"🤖 AI Mode: {ai_status}\n"
        f"🎬 Media: {media}\n\n"
        f"👦 Male: {male_msg}\n"
        f"👧 Female: {female_msg}"
    )

    toggle_btn = "❌ Deactivate" if grp.get("welcome_active") else "✅ Activate"
    ai_btn = "🤖 AI OFF" if settings.get("ai_enabled") else "🤖 AI ON"

    keyboard = [
        [InlineKeyboardButton("👦 Set Male Msg", callback_data=f"setmale_{group_id}"),
         InlineKeyboardButton("👧 Set Female Msg", callback_data=f"setfemale_{group_id}")],
        [InlineKeyboardButton("📸 Set Photo/Video", callback_data=f"setmedia_{group_id}"),
         InlineKeyboardButton("🗑️ Clear Media", callback_data=f"clearmedia_{group_id}")],
        [InlineKeyboardButton(toggle_btn, callback_data=f"toggle_{group_id}"),
         InlineKeyboardButton(ai_btn, callback_data=f"aitoggle_{group_id}")],
        [InlineKeyboardButton("👁️ Preview", callback_data=f"preview_{group_id}"),
         InlineKeyboardButton("🔌 Disconnect", callback_data=f"disconnect_{group_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ===================== SEND WELCOME =====================
async def send_welcome(context, chat_id, new_member):
    settings = get_settings(chat_id)
    group = get_group(chat_id)

    if not settings.get("active") or not group.get("welcome_active"):
        return

    first_name = new_member.first_name or "User"
    username = new_member.username or ""
    user_id = new_member.id

    try:
        chat = await context.bot.get_chat(chat_id)
        chat_title = chat.title or "Group"
    except:
        chat_title = "Group"

    gender = detect_gender(first_name, username)

    if settings.get("ai_enabled"):
        ai_gender = ai_detect_gender(first_name, username)
        if ai_gender:
            gender = ai_gender
        msg_template = ai_generate_message(first_name, gender, chat_title)
        if not msg_template:
            msg_template = settings.get("male_msg") if gender == "male" else settings.get("female_msg")
    else:
        if gender == "male" and group.get("custom_male_msg"):
            msg_template = group["custom_male_msg"]
        elif gender == "female" and group.get("custom_female_msg"):
            msg_template = group["custom_female_msg"]
        else:
            msg_template = settings.get("male_msg") if gender == "male" else settings.get("female_msg")

    welcome_text = msg_template \
        .replace("{name}", first_name) \
        .replace("{username}", f"@{username}" if username else first_name) \
        .replace("{chat_title}", chat_title) \
        .replace("{user_id}", str(user_id))

    try:
        if settings.get("media_type") == "video" and settings.get("video_id"):
            await context.bot.send_video(chat_id=chat_id, video=settings["video_id"],
                                         caption=welcome_text, parse_mode="HTML")
        elif settings.get("media_type") == "photo" and settings.get("photo_id"):
            await context.bot.send_photo(chat_id=chat_id, photo=settings["photo_id"],
                                         caption=welcome_text, parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id=chat_id, text=welcome_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"send_welcome error: {e}")

# ===================== /start =====================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    # Deep link se aaya?
    if context.args and context.args[0].startswith("connect_"):
        try:
            target_chat_id = int(context.args[0].replace("connect_", ""))
            await do_connect(update, context, target_chat_id)
            return
        except Exception as e:
            logger.error(f"Deep link error: {e}")

    await show_main_menu(update, context)

# ===================== /connect — SIRF GROUP MEIN =====================
async def cmd_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # DM mein use kiya toh guide karo
    if chat_type == "private":
        await update.message.reply_text(
            "ℹ️ Yeh command group mein use karo!\n\n"
            "Steps:\n"
            "1️⃣ Bot ko group mein ADMIN banao\n"
            "2️⃣ Group mein <code>/connect</code> likho\n"
            "3️⃣ Button aayega — click karo\n"
            "4️⃣ Sab settings yahan DM mein hogi ✅",
            parse_mode="HTML"
        )
        return

    # Bot admin hai?
    try:
        bot_info = await context.bot.get_me()
        bot_member = await context.bot.get_chat_member(chat_id, bot_info.id)
        if bot_member.status not in ['administrator', 'creator']:
            await update.message.reply_text("❌ Pehle mujhe group ka ADMIN banao, phir /connect karo!")
            return
    except Exception as e:
        logger.error(f"Bot admin check error: {e}")

    # User admin/owner hai?
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("❌ Sirf group owner/admin /connect kar sakte hain!")
            return
    except Exception as e:
        logger.error(f"User admin check error: {e}")
        await update.message.reply_text("❌ Error aaya. Bot ko admin banao aur dobara try karo.")
        return

    bot_info = await context.bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start=connect_{chat_id}"
    keyboard = [[InlineKeyboardButton("🔗 Bot DM mein Open Karo & Connect", url=deep_link)]]

    await update.message.reply_text(
        "✅ Button dabao — DM mein group connect ho jayega!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===================== CONNECT LOGIC =====================
async def do_connect(update: Update, context: ContextTypes.DEFAULT_TYPE, target_chat_id: int):
    user_id = update.effective_user.id

    try:
        member = await context.bot.get_chat_member(target_chat_id, user_id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("❌ Tum us group ke admin/owner nahi ho!")
            return
    except Exception as e:
        logger.error(f"do_connect check error: {e}")
        await update.message.reply_text("❌ Error aaya. Bot ko group admin banao aur dobara try karo.")
        return

    group = get_group(target_chat_id)
    admins = group.get("connected_admins", [])
    if user_id not in admins:
        admins.append(user_id)
    group["connected_admins"] = admins
    group["welcome_active"] = True
    save_group(target_chat_id, group)

    settings = get_settings(target_chat_id)
    settings["active"] = True
    save_settings(target_chat_id, settings)

    try:
        chat = await context.bot.get_chat(target_chat_id)
        chat_title = chat.title or "Group"
    except:
        chat_title = "Group"

    await update.message.reply_text(
        f"🎉 <b>{chat_title}</b> connected!\n\nAb neeche group select karke sab DM se set karo 👇",
        parse_mode="HTML"
    )
    await show_main_menu(update, context)

# ===================== CALLBACK HANDLER =====================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "main_menu":
        await show_main_menu(query, context, edit=True)
        return

    if data.startswith("group_"):
        group_id = int(data.replace("group_", ""))
        context.user_data["selected_group"] = group_id
        await show_group_menu(query, context, group_id)
        return

    if data.startswith("toggle_"):
        group_id = int(data.replace("toggle_", ""))
        grp = get_group(group_id)
        grp["welcome_active"] = not grp.get("welcome_active", True)
        save_group(group_id, grp)
        settings = get_settings(group_id)
        settings["active"] = grp["welcome_active"]
        save_settings(group_id, settings)
        await show_group_menu(query, context, group_id)
        return

    if data.startswith("aitoggle_"):
        group_id = int(data.replace("aitoggle_", ""))
        settings = get_settings(group_id)
        settings["ai_enabled"] = not settings.get("ai_enabled", False)
        save_settings(group_id, settings)
        await show_group_menu(query, context, group_id)
        return

    if data.startswith("clearmedia_"):
        group_id = int(data.replace("clearmedia_", ""))
        settings = get_settings(group_id)
        settings["video_id"] = None
        settings["photo_id"] = None
        settings["media_type"] = None
        save_settings(group_id, settings)
        await query.edit_message_text(
            "✅ Media clear ho gaya!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"group_{group_id}")]])
        )
        return

    if data.startswith("preview_"):
        group_id = int(data.replace("preview_", ""))
        await query.edit_message_text("⏳ Preview group mein bhej raha hoon...")

        class FakeUser:
            first_name = "TestUser"
            username = "testuser"
            id = 123456789
            is_bot = False

        await send_welcome(context, group_id, FakeUser())
        await query.edit_message_text(
            "✅ Preview group mein bhej diya!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"group_{group_id}")]])
        )
        return

    if data.startswith("disconnect_"):
        group_id = int(data.replace("disconnect_", ""))
        grp = get_group(group_id)
        admins = grp.get("connected_admins", [])
        if user_id in admins:
            admins.remove(user_id)
        grp["connected_admins"] = admins
        grp["welcome_active"] = False
        save_group(group_id, grp)
        settings = get_settings(group_id)
        settings["active"] = False
        save_settings(group_id, settings)
        await query.edit_message_text(
            "✅ Group disconnect ho gaya!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]])
        )
        return

    if data.startswith("setmale_"):
        group_id = int(data.replace("setmale_", ""))
        context.user_data["awaiting"] = {"type": "male_msg", "group_id": group_id}
        await query.edit_message_text(
            "👦 <b>Male welcome message type karo:</b>\n\n"
            "Variables:\n"
            "<code>{name}</code> — naam\n"
            "<code>{username}</code> — @username\n"
            "<code>{chat_title}</code> — group naam\n\n"
            "Example:\n<code>Welcome bhai {name}! 👦 Khush aaye!</code>\n\n"
            "✍️ Abhi type karo 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"group_{group_id}")]])
        )
        return

    if data.startswith("setfemale_"):
        group_id = int(data.replace("setfemale_", ""))
        context.user_data["awaiting"] = {"type": "female_msg", "group_id": group_id}
        await query.edit_message_text(
            "👧 <b>Female welcome message type karo:</b>\n\n"
            "Variables:\n"
            "<code>{name}</code> — naam\n"
            "<code>{username}</code> — @username\n"
            "<code>{chat_title}</code> — group naam\n\n"
            "Example:\n<code>Welcome didi {name}! 👧 Khush aaye!</code>\n\n"
            "✍️ Abhi type karo 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"group_{group_id}")]])
        )
        return

    if data.startswith("setmedia_"):
        group_id = int(data.replace("setmedia_", ""))
        context.user_data["awaiting"] = {"type": "media", "group_id": group_id}
        await query.edit_message_text(
            "📸 <b>Photo ya Video bhejo:</b>\n\n"
            "Abhi DM mein photo ya video send karo.\n"
            "Wo welcome message ke saath group mein jayega! 🎬",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"group_{group_id}")]])
        )
        return

# ===================== DM MESSAGE HANDLER =====================
async def dm_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    awaiting = context.user_data.get("awaiting")
    if not awaiting:
        await show_main_menu(update, context)
        return

    atype = awaiting.get("type")
    group_id = awaiting.get("group_id")
    context.user_data.pop("awaiting", None)

    back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Group", callback_data=f"group_{group_id}")]])

    if atype == "male_msg":
        msg = update.message.text
        if not msg:
            await update.message.reply_text("❌ Text message chahiye!")
            return
        grp = get_group(group_id)
        grp["custom_male_msg"] = msg
        save_group(group_id, grp)
        preview = msg.replace('{name}','Rahul').replace('{username}','@rahul').replace('{chat_title}','Group')
        await update.message.reply_text(
            f"✅ Male message set!\n\n<b>Preview:</b> {preview}",
            parse_mode="HTML", reply_markup=back_btn
        )
        return

    if atype == "female_msg":
        msg = update.message.text
        if not msg:
            await update.message.reply_text("❌ Text message chahiye!")
            return
        grp = get_group(group_id)
        grp["custom_female_msg"] = msg
        save_group(group_id, grp)
        preview = msg.replace('{name}','Priya').replace('{username}','@priya').replace('{chat_title}','Group')
        await update.message.reply_text(
            f"✅ Female message set!\n\n<b>Preview:</b> {preview}",
            parse_mode="HTML", reply_markup=back_btn
        )
        return

    if atype == "media":
        msg = update.message
        settings = get_settings(group_id)
        if msg.video:
            settings["video_id"] = msg.video.file_id
            settings["media_type"] = "video"
            settings["photo_id"] = None
            save_settings(group_id, settings)
            await update.message.reply_text("✅ Video set! Welcome ke saath jayegi. 🎬", reply_markup=back_btn)
        elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("video/"):
            settings["video_id"] = msg.document.file_id
            settings["media_type"] = "video"
            settings["photo_id"] = None
            save_settings(group_id, settings)
            await update.message.reply_text("✅ Video set! Welcome ke saath jayegi. 🎬", reply_markup=back_btn)
        elif msg.photo:
            settings["photo_id"] = msg.photo[-1].file_id
            settings["media_type"] = "photo"
            settings["video_id"] = None
            save_settings(group_id, settings)
            await update.message.reply_text("✅ Photo set! Welcome ke saath jayegi. 🖼️", reply_markup=back_btn)
        else:
            await update.message.reply_text("❌ Photo ya Video bhejo, text nahi!", reply_markup=back_btn)
        return

# ===================== NEW MEMBER HANDLER =====================
async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return
    chat_id = update.effective_chat.id
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        await send_welcome(context, chat_id, member)

# ===================== MAIN =====================
def main():
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask server started on port 8080")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("connect", cmd_connect))  # Group mein chalega
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL),
        dm_message_handler
    ))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_handler))

    logger.info("🚀 Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
