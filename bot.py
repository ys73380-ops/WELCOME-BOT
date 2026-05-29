import logging
import json
import os
import random
import unicodedata
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ChatMemberHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
DATA_FILE = "bot_data.json"

# ─────────────────────────────────────────────
# NAME DICTIONARIES (same as before)
# ─────────────────────────────────────────────

MALE_NAMES = {
    'raj', 'rajan', 'rajesh', 'rajiv', 'rajat', 'rajendra', 'rajkumar',
    'kumar', 'kamal', 'karan', 'kartik', 'krishna', 'kuldeep', 'kapil',
    'singh', 'sunil', 'suresh', 'sanjay', 'sachin', 'sahil', 'siddharth',
    'sharma', 'shiv', 'shivam', 'shivraj', 'shubham', 'saurabh', 'sonu',
    'amit', 'amitabh', 'aman', 'ankit', 'ankur', 'anil', 'ajay', 'akash',
    'akshay', 'arjun', 'aryan', 'arun', 'aditya', 'abhishek', 'abhi',
    'rahul', 'ravi', 'ram', 'rakesh', 'rohit', 'rohan', 'rishi', 'ritesh',
    'vikram', 'vijay', 'vikas', 'vivek', 'vishal', 'vicky', 'varun',
    'mohit', 'manish', 'manoj', 'mahesh', 'mukesh', 'monu', 'mohan',
    'deepak', 'dinesh', 'dev', 'devesh', 'dhruv', 'diljit', 'dilip',
    'harsh', 'harish', 'hardik', 'hanuman', 'himanshu', 'hitesh',
    'nitin', 'nitesh', 'naresh', 'naveen', 'naman', 'navin',
    'pradeep', 'pratik', 'pramod', 'prabhat', 'parth', 'piyush',
    'yogesh', 'yash', 'yashodhan',
    'ganesh', 'gaurav', 'girish', 'gopal', 'golu',
    'lalit', 'lokesh', 'lucky',
    'tarun', 'tushar', 'tinku',
    'umesh', 'uday',
    'vipin', 'vineet', 'vinod', 'vishnu',
    'wasim', 'waseem',
    'zeeshan', 'zahid',
    'thakur', 'choudhary', 'verma', 'gupta', 'yadav', 'patel',
    'shah', 'joshi', 'mehta', 'agarwal', 'mittal', 'goel', 'tiwari',
    'mishra', 'pandey', 'chaudhary', 'chauhan', 'bhatt', 'jain',
    'boy', 'bhai', 'bhaiya', 'bro', 'king', 'boss', 'mr', 'sir',
    'master', 'prince', 'sultan', 'lion', 'tiger', 'devil', 'ninja',
    'rocky', 'tony', 'lucky', 'sunny', 'bunny', 'sonu', 'monu',
    'golu', 'pappu', 'tinku', 'ladka', 'male', 'wild', 'dark',
    'shadow', 'hero', 'babu', 'anna', 'dada', 'baba',
    'ramesh', 'venkat', 'venkatesh', 'ramu', 'krishnamurthy', 'murugan',
    'selvam', 'senthil', 'prakash', 'subramaniam', 'balaji',
    'gurpreet', 'gurjit', 'harpreet', 'jaspreet', 'manpreet',
    'navjot', 'paramjit', 'ranjit', 'surjit', 'amarjit',
    'mohammad', 'mohammed', 'muhammad', 'md', 'ali', 'khan',
    'sheikh', 'ansari', 'siddiqui', 'qureshi', 'hussain',
    'hassan', 'imran', 'irfan', 'danish', 'farhan', 'faisal',
    'salman', 'adnan', 'asif', 'arif', 'nazim',
    'zaid', 'aamir', 'amir', 'usman', 'umer',
}

FEMALE_NAMES = {
    'priya', 'priyanka', 'preeti', 'puja', 'pooja', 'pallavi', 'payal',
    'neha', 'nisha', 'nita', 'nitu', 'namrata', 'nidhi', 'nikita',
    'aarti', 'arti', 'anjali', 'anita', 'ananya', 'asha', 'aisha',
    'sunita', 'sunidhi', 'sona', 'soni', 'sonam', 'sonali', 'swati',
    'seema', 'sima', 'shreya', 'shruti', 'shilpa', 'shital', 'shweta',
    'kavita', 'kajal', 'kiran', 'komal', 'kavya', 'khushi',
    'rekha', 'reena', 'ritu', 'rima', 'rita', 'roshni', 'radha',
    'meena', 'megha', 'monika', 'madhuri', 'mona', 'mansi',
    'deepa', 'deepika', 'divya', 'disha', 'diksha',
    'geeta', 'gita', 'gudiya', 'garima',
    'heena', 'hema', 'honey',
    'ishita', 'isha', 'ishani',
    'jyoti', 'juhi',
    'lata', 'lakshmi', 'leena',
    'tanvi', 'tina', 'tanisha', 'twinkle',
    'usha', 'urvashi',
    'veena', 'vanita', 'varsha', 'vandana', 'vaishnavi',
    'yasmeen', 'yasmin',
    'zara', 'zeenat',
    'devi', 'kumari', 'saraswati', 'parvati', 'durga', 'kali',
    'sita', 'gita', 'rita', 'nita', 'mita',
    'sonal', 'monal', 'sheena', 'teena',
    'sangeeta', 'sangita', 'savita', 'smita', 'amrita', 'mamta',
    'sudha', 'subha', 'alka', 'anupama',
    'kamala', 'kamali', 'meenakshi', 'revathi',
    'sumathi', 'bharati', 'vijayalakshmi', 'saraswathi',
    'padmavathi', 'annapurna', 'bhavani',
    'jasleen', 'harleen', 'navneet', 'parmeet', 'jasveen',
    'fatima', 'fathima', 'ayesha', 'zainab', 'rukhsar',
    'shabnam', 'sana', 'sara', 'sarah', 'noor', 'hina', 'asma',
    'farida', 'reshma', 'nagma', 'nasreen', 'rubina', 'ruksana',
    'samina', 'tahira', 'zubaida',
    'girl', 'didi', 'behen', 'miss', 'mrs', 'ms', 'lady',
    'queen', 'princess', 'ladki', 'female', 'sweety', 'baby',
    'pinky', 'rinky', 'bittu',
}

FEMALE_ENDINGS = (
    'bai', 'bala', 'devi', 'kumari', 'laxmi', 'wati', 'mati',
    'priya', 'nita', 'mala', 'vati', 'shree', 'shri',
    'amma', 'akka', 'chechi', 'ben', 'bhen',
)

MALE_ENDINGS = (
    'esh', 'ash', 'ish', 'ush',
    'raj', 'deep', 'jeet', 'jit',
    'inder', 'vir', 'bir',
    'bhai', 'anna', 'dada',
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# GROQ AI GENDER DETECTION
# ─────────────────────────────────────────────

async def groq_detect_gender(name: str) -> str:
    """
    Groq AI se gender detect karo.
    Returns: 'male', 'female', ya 'neutral'
    """
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set, falling back to neutral")
        return 'neutral'

    prompt = f"""You are a gender detection expert for Indian/South Asian names.
Given the name: "{name}"

Analyze this name and respond with ONLY one word: male, female, or neutral.

Rules:
- If the name is clearly male (Indian, Muslim, Sikh, Hindu male names), say: male
- If the name is clearly female (Indian, Muslim, Sikh, Hindu female names), say: female
- If you are genuinely unsure or it's a username/nickname with no clear gender signal, say: neutral
- Consider all Indian name origins: Hindi, Urdu, Punjabi, Tamil, Telugu, Bengali, Gujarati, Marathi, etc.
- Do NOT explain. Just one word answer: male, female, or neutral"""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama3-8b-8192",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                    "temperature": 0.1
                }
            )
            data = response.json()
            result = data['choices'][0]['message']['content'].strip().lower()

            # Clean result
            if 'female' in result:
                return 'female'
            elif 'male' in result:
                return 'male'
            else:
                return 'neutral'

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return 'neutral'


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

def normalize_name(name: str) -> str:
    try:
        normalized = unicodedata.normalize('NFKD', name)
        ascii_name = ''.join(c for c in normalized if not unicodedata.combining(c))
        cleaned = ''.join(c for c in ascii_name if c.isprintable())
        return cleaned if cleaned.strip() else name
    except:
        return name


def detect_gender_local(name: str) -> str:
    """Fast local dictionary-based detection"""
    normal_name = normalize_name(name)
    name_lower = normal_name.lower().strip()
    words = name_lower.split()

    for word in words:
        clean_word = ''.join(c for c in word if c.isalpha())
        if clean_word and clean_word in FEMALE_NAMES:
            return 'female'

    for word in words:
        clean_word = ''.join(c for c in word if c.isalpha())
        if clean_word and clean_word in MALE_NAMES:
            return 'male'

    for fname in FEMALE_NAMES:
        if fname in name_lower:
            return 'female'

    for mname in MALE_NAMES:
        if mname in name_lower:
            return 'male'

    for ending in FEMALE_ENDINGS:
        if name_lower.endswith(ending):
            return 'female'

    for ending in MALE_ENDINGS:
        if name_lower.endswith(ending):
            return 'male'

    return 'neutral'


async def detect_gender_smart(name: str) -> str:
    """
    2-Step detection:
    1. Local dictionary (fast)
    2. Groq AI (agar local neutral aaye)
    """
    local_result = detect_gender_local(name)
    if local_result != 'neutral':
        logger.info(f"Local detect: '{name}' → {local_result}")
        return local_result

    # Local ne nahi pakda → Groq AI try karo
    logger.info(f"Local neutral, trying Groq AI for: '{name}'")
    ai_result = await groq_detect_gender(name)
    logger.info(f"Groq AI detect: '{name}' → {ai_result}")
    return ai_result


def replace_vars(text, full_name, username, user_mention, gender):
    return (text
            .replace('{name}', full_name)
            .replace('{username}', username)
            .replace('{mention}', user_mention)
            .replace('{gender}', gender))


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id_override=None) -> bool:
    user_id = update.effective_user.id
    target = chat_id_override or update.effective_chat.id
    if not chat_id_override and update.effective_chat.type == 'private':
        return True
    try:
        admins = await context.bot.get_chat_administrators(target)
        return user_id in [a.user.id for a in admins]
    except Exception as e:
        logger.error(f"Admin check error: {e}")
        return False


def get_connected_chat(user_id: int):
    return load_data().get('connections', {}).get(str(user_id))


def set_connected_chat(user_id: int, chat_id: str):
    data = load_data()
    data.setdefault('connections', {})[str(user_id)] = chat_id
    save_data(data)


def remove_connected_chat(user_id: int):
    data = load_data()
    data.get('connections', {}).pop(str(user_id), None)
    save_data(data)


async def get_target_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return str(update.effective_chat.id)
    connected = get_connected_chat(update.effective_user.id)
    if not connected:
        await update.message.reply_text(
            "❌ <b>Koi group connected nahi hai!</b>\n\n"
            "Apne group mein jaao aur <code>/connect</code> chalao.",
            parse_mode='HTML'
        )
        return None
    return connected


async def send_gender_welcome(context, chat_id: str, user_id: int, full_name: str, username: str, gender: str):
    user_mention = f'<a href="tg://user?id={user_id}">{full_name}</a>'
    data = load_data()
    group_data = data.get(chat_id, {})

    default_msg = {
        'male':   f"🎉 Welcome {user_mention} bhai! Hamare group mein swagat hai! 🙏",
        'female': f"🌸 Welcome {user_mention} didi! Hamare group mein swagat hai! 🙏",
        'neutral': f"👋 Welcome {user_mention}! Hamare group mein swagat hai! 🙏",
    }

    msg = group_data.get('welcome_messages', {}).get(gender) or default_msg.get(gender, f"👋 Welcome {user_mention}!")
    msg = replace_vars(msg, full_name, username, user_mention, gender)
    video_list = group_data.get('welcome_videos', {}).get(gender, [])

    try:
        if video_list:
            vd = random.choice(video_list)
            cap = replace_vars(vd.get('caption', ''), full_name, username, user_mention, gender)
            final_cap = f"{msg}\n\n{cap}" if cap else msg
            await context.bot.send_video(
                chat_id=int(chat_id), video=vd['file_id'],
                caption=final_cap, parse_mode='HTML'
            )
        else:
            await context.bot.send_message(chat_id=int(chat_id), text=msg, parse_mode='HTML')
    except Exception as e:
        logger.error(f"send_gender_welcome error: {e}")
        try:
            await context.bot.send_message(chat_id=int(chat_id), text=msg, parse_mode='HTML')
        except Exception as e2:
            logger.error(f"Fallback failed: {e2}")


# ─────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Welcome to Gender Welcome Bot!</b>\n\n"
        "🔗 <b>Setup Steps:</b>\n"
        "1️⃣ Bot ko group mein Admin banao\n"
        "2️⃣ Group mein <code>/connect</code> chalao\n"
        "3️⃣ Bot ke DM mein commands chalao!\n\n"
        "📋 <b>Commands:</b>\n\n"
        "🔗 <code>/connect</code> — Group connect karo\n"
        "🔌 <code>/disconnect</code> — Connection hatao\n\n"
        "🎬 <code>/setwelcomemv male Aao bhai {name}!</code>\n"
        "   ↳ Video reply ke saath = video+msg dono set\n"
        "   ↳ Bina reply ke = sirf msg set\n\n"
        "🎬 <code>/setwelcomemv female Welcome didi {name}!</code>\n"
        "   ↳ Same — video reply karo to video bhi set\n\n"
        "👁 <code>/showpreview</code> — Live preview dekho\n"
        "🗑 <code>/resetwelcome</code> — Sab reset\n"
        "🔍 <code>/testgender name</code> — Gender test\n"
        "👮 <code>/admincheck</code> — Admin check\n\n"
        "✨ <b>Variables:</b>\n"
        "<code>{name}</code> — Full name\n"
        "<code>{username}</code> — @username\n"
        "<code>{mention}</code> — Clickable mention\n"
        "<code>{gender}</code> — male/female/neutral\n\n"
        "🤖 <b>AI Power:</b> Groq AI se smart gender detection!",
        parse_mode='HTML'
    )


async def connect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    if update.effective_chat.type != 'private':
        if not await is_admin(update, context):
            await update.message.reply_text("❌ Sirf admins /connect kar sakte hain!")
            return
        chat_id = str(update.effective_chat.id)
        chat_title = update.effective_chat.title
        set_connected_chat(user_id, chat_id)
        await update.message.reply_text(
            f"✅ <b>Connected!</b>\n\n"
            f"👤 {user_name}\n"
            f"💬 {chat_title}\n\n"
            f"Ab DM mein jaao: @{context.bot.username}",
            parse_mode='HTML'
        )
    else:
        connected = get_connected_chat(user_id)
        if connected:
            try:
                chat = await context.bot.get_chat(connected)
                await update.message.reply_text(
                    f"✅ <b>Connected:</b> {chat.title}\n"
                    f"🆔 <code>{connected}</code>",
                    parse_mode='HTML'
                )
            except:
                await update.message.reply_text(
                    f"✅ Connected: <code>{connected}</code>", parse_mode='HTML'
                )
        else:
            await update.message.reply_text(
                "❌ Koi group connected nahi!\n"
                "Group mein jaao aur <code>/connect</code> chalao.",
                parse_mode='HTML'
            )


async def disconnect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remove_connected_chat(update.effective_user.id)
    await update.message.reply_text(
        "✅ Disconnected!\nNaya connect karne ke liye group mein /connect chalao."
    )


# ─────────────────────────────────────────────
# NEW: /setwelcomemv — MSG + VIDEO EK SAATH
# ─────────────────────────────────────────────

async def setwelcomemv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setwelcomemv male <message>
    - Agar video reply karo → video + message dono set
    - Bina reply ke → sirf message set
    """
    chat_id = await get_target_chat_id(update, context)
    if not chat_id:
        return

    override = int(chat_id) if update.effective_chat.type == 'private' else None
    if not await is_admin(update, context, chat_id_override=override):
        await update.message.reply_text("❌ Only admins can use this!")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ <b>Usage:</b>\n\n"
            "📝 <b>Sirf message:</b>\n"
            "<code>/setwelcomemv male Welcome bhai {name}!</code>\n\n"
            "🎬 <b>Message + Video (video reply karke):</b>\n"
            "<code>/setwelcomemv female Welcome didi {name}!</code>\n\n"
            "🧑 <b>Genders:</b> <code>male</code> | <code>female</code> | <code>neutral</code>",
            parse_mode='HTML'
        )
        return

    gender = context.args[0].lower()
    if gender not in ['male', 'female', 'neutral']:
        await update.message.reply_text(
            "❌ Gender galat hai!\n"
            "Likho: <code>male</code>, <code>female</code>, ya <code>neutral</code>",
            parse_mode='HTML'
        )
        return

    msg = ' '.join(context.args[1:])
    data = load_data()
    group = data.setdefault(chat_id, {})

    # Message set karo
    group.setdefault('welcome_messages', {})[gender] = msg

    # Video bhi hai? (reply check)
    video_added = False
    if update.message.reply_to_message and update.message.reply_to_message.video:
        video = update.message.reply_to_message.video
        vlist = group.setdefault('welcome_videos', {}).setdefault(gender, [])

        # Caption = jo message likha hai ya video ki original caption
        video_caption = update.message.reply_to_message.caption or ''
        vlist.append({
            'file_id': video.file_id,
            'caption': video_caption
        })
        video_added = True

    save_data(data)

    emoji = '👨' if gender == 'male' else '👩' if gender == 'female' else '🧑'

    if video_added:
        vcount = len(data[chat_id]['welcome_videos'][gender])
        await update.message.reply_text(
            f"✅ <b>{emoji} {gender.upper()} — Message + Video Set!</b>\n\n"
            f"📝 <b>Message:</b>\n{msg}\n\n"
            f"🎬 <b>Video added!</b> Total {gender} videos: <b>{vcount}</b>",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f"✅ <b>{emoji} {gender.upper()} — Message Set!</b>\n\n"
            f"📝 <b>Message:</b>\n{msg}\n\n"
            f"💡 <i>Tip: Video bhi add karna ho to kisi video ko reply karke ye command chalao!</i>",
            parse_mode='HTML'
        )


# ─────────────────────────────────────────────
# NEW: /showpreview — LIVE PREVIEW
# ─────────────────────────────────────────────

async def showpreview_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Actual preview bhejta hai — exactly jaisa new member ko milega
    """
    chat_id = await get_target_chat_id(update, context)
    if not chat_id:
        return

    override = int(chat_id) if update.effective_chat.type == 'private' else None
    if not await is_admin(update, context, chat_id_override=override):
        await update.message.reply_text("❌ Only admins can use this!")
        return

    data = load_data()
    group_data = data.get(chat_id, {})

    if not group_data:
        await update.message.reply_text(
            "ℹ️ Koi settings nahi hain abhi.\n"
            "Pehle <code>/setwelcomemv</code> se set karo!",
            parse_mode='HTML'
        )
        return

    user = update.effective_user
    full_name = f"{user.first_name} {user.last_name}".strip() if user.last_name else user.first_name
    username = f"@{user.username}" if user.username else full_name
    user_mention = f'<a href="tg://user?id={user.id}">{full_name}</a>'

    try:
        chat = await context.bot.get_chat(int(chat_id))
        title = chat.title
    except:
        title = chat_id

    # Header
    await update.message.reply_text(
        f"👁 <b>PREVIEW — {title}</b>\n\n"
        f"<i>Neeche exactly waise welcome messages aayenge jaise naye members ko milenge:</i>",
        parse_mode='HTML'
    )

    # Preview for each gender
    for gender in ['male', 'female', 'neutral']:
        emoji = '👨' if gender == 'male' else '👩' if gender == 'female' else '🧑'

        default_msg = {
            'male':    f"🎉 Welcome {user_mention} bhai! Hamare group mein swagat hai! 🙏",
            'female':  f"🌸 Welcome {user_mention} didi! Hamare group mein swagat hai! 🙏",
            'neutral': f"👋 Welcome {user_mention}! Hamare group mein swagat hai! 🙏",
        }

        msg_template = group_data.get('welcome_messages', {}).get(gender, '')
        video_list = group_data.get('welcome_videos', {}).get(gender, [])

        if not msg_template and not video_list:
            await update.message.reply_text(
                f"{emoji} <b>{gender.upper()}</b> — ❌ Not set (default use hoga)",
                parse_mode='HTML'
            )
            continue

        # Replace vars with admin's own info for preview
        final_msg = replace_vars(
            msg_template or default_msg[gender],
            full_name, username, user_mention, gender
        )

        await update.message.reply_text(
            f"{emoji} <b>{gender.upper()} PREVIEW:</b>",
            parse_mode='HTML'
        )

        try:
            if video_list:
                vd = random.choice(video_list)
                cap = replace_vars(vd.get('caption', ''), full_name, username, user_mention, gender)
                final_cap = f"{final_msg}\n\n{cap}" if cap else final_msg
                await update.message.reply_video(
                    video=vd['file_id'],
                    caption=final_cap,
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(final_msg, parse_mode='HTML')
        except Exception as e:
            await update.message.reply_text(
                f"⚠️ Preview error: {e}\n\n📝 Message:\n{final_msg}",
                parse_mode='HTML'
            )


async def reset_welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = await get_target_chat_id(update, context)
    if not chat_id:
        return

    override = int(chat_id) if update.effective_chat.type == 'private' else None
    if not await is_admin(update, context, chat_id_override=override):
        await update.message.reply_text("❌ Only admins can use this!")
        return

    data = load_data()
    if chat_id in data:
        data[chat_id] = {}
        save_data(data)

    await update.message.reply_text(
        "✅ <b>Saari settings reset ho gayi!</b>\n"
        "<i>Ab default welcome messages use honge.</i>",
        parse_mode='HTML'
    )


async def admincheck_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = await get_target_chat_id(update, context)
    if not chat_id:
        return

    try:
        admins = await context.bot.get_chat_administrators(int(chat_id))
        is_adm = user_id in [a.user.id for a in admins]
        status = next((a.status for a in admins if a.user.id == user_id), 'member')
        await update.message.reply_text(
            f"👤 {update.effective_user.first_name}\n"
            f"🆔 <code>{user_id}</code>\n"
            f"📊 Status: {status}\n"
            f"👮 Admin: {'Yes ✅' if is_adm else 'No ❌'}",
            parse_mode='HTML'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def testgender_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/testgender Rahul Singh</code>",
            parse_mode='HTML'
        )
        return

    name = ' '.join(context.args)
    normalized = normalize_name(name)

    # Local first
    local_result = detect_gender_local(name)
    processing_msg = await update.message.reply_text(
        f"🔍 <b>Gender Test</b>\n\n"
        f"👤 Name: <b>{name}</b>\n"
        f"📚 Local Dictionary: <b>{local_result.upper()}</b>\n"
        f"{'🤖 Groq AI: checking...' if local_result == 'neutral' else ''}",
        parse_mode='HTML'
    )

    if local_result == 'neutral' and GROQ_API_KEY:
        ai_result = await groq_detect_gender(name)
        final = ai_result
        source = f"🤖 Groq AI: <b>{ai_result.upper()}</b>"
    else:
        final = local_result
        source = "✅ Local dictionary se mila"

    await processing_msg.edit_text(
        f"🔍 <b>Gender Test Result</b>\n\n"
        f"👤 Name: <b>{name}</b>\n"
        f"✏️ Normalized: <b>{normalized}</b>\n"
        f"📚 Local: <b>{local_result.upper()}</b>\n"
        f"{source}\n\n"
        f"⚡ <b>Final: {final.upper()}</b>",
        parse_mode='HTML'
    )


# ─────────────────────────────────────────────
# WELCOME NEW MEMBER — Groq AI for neutral
# ─────────────────────────────────────────────

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.chat_member:
        return

    cm = update.chat_member
    old_status = cm.old_chat_member.status
    new_status = cm.new_chat_member.status

    if old_status not in ['left', 'kicked', 'banned']:
        return
    if new_status not in ['member', 'administrator']:
        return

    new_member = cm.new_chat_member.user
    chat_id = str(update.effective_chat.id)

    if new_member.is_bot:
        return

    full_name = (
        f"{new_member.first_name} {new_member.last_name}".strip()
        if new_member.last_name
        else new_member.first_name or "New Member"
    )
    username = f"@{new_member.username}" if new_member.username else full_name

    # Smart detection: Local → Groq AI (if neutral)
    gender = await detect_gender_smart(full_name)
    logger.info(f"NEW MEMBER: '{full_name}' | final_gender={gender}")

    # Ab seedha welcome bhejo — no buttons needed!
    await send_gender_welcome(context, chat_id, new_member.id, full_name, username, gender)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("🤖 Starting Gender Welcome Bot...")
    print(f"🔑 Groq AI: {'✅ Active' if GROQ_API_KEY else '❌ Not configured (set GROQ_API_KEY)'}")
    print("✅ Bot is running!")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("connect", connect_command))
    application.add_handler(CommandHandler("disconnect", disconnect_command))
    application.add_handler(CommandHandler("setwelcomemv", setwelcomemv_command))   # NEW
    application.add_handler(CommandHandler("showpreview", showpreview_command))     # NEW
    application.add_handler(CommandHandler("resetwelcome", reset_welcome_command))
    application.add_handler(CommandHandler("admincheck", admincheck_command))
    application.add_handler(CommandHandler("testgender", testgender_command))
    application.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
