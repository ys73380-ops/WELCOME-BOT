#!/usr/bin/env python3

import logging
import json
import os
import random
import unicodedata
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ChatMemberHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "your_token_here")
DATA_FILE = "/data/bot_data.json"  # purana — reh sakta hai
PROMO_LINK = os.getenv("PROMO_LINK", "")


MALE_NAMES = {
    'raj', 'rajan', 'rajesh', 'rajiv', 'rajat', 'rajendra', 'rajkumar',
    'kumar', 'kamal', 'karan', 'kartik', 'krishna', 'kuldeep', 'kapil',
    'singh', 'sunil', 'suresh', 'sanjay', 'sachin', 'sahil', 'siddharth',
    'sharma', 'shiv', 'shivam', 'shivraj', 'shubham', 'saurabh', 'sonu',
    'amit', 'amitabh', 'aman', 'ankit', 'ankur', 'anil', 'ajay', 'akash',
    'akshay', 'arjun', 'aryan', 'arun', 'aditya',    'abhishek', 'abhi', 'rahul', 'ravi', 'ram', 'rakesh', 'rohit', 'rohan', 'rishi', 'ritesh',
    'vikram', 'vijay', 'vikas', 'vivek', 'vishal', 'vicky', 'varun',
    'mohit', 'manish', 'manoj', 'mahesh', 'mukesh', 'monu', 'mohan',
    'deepak', 'dinesh', 'dev', 'devesh', 'dhruv',
    'harsh', 'harish', 'hardik', 'himanshu', 'hitesh',
    'nitin', 'nitesh', 'naresh', 'naveen', 'naman',
    'pradeep', 'pratik', 'pramod', 'parth', 'piyush',
    'yogesh', 'yash', 'ganesh', 'gaurav', 'golu',
    'lalit', 'lokesh', 'lucky', 'tarun', 'tushar',
    'umesh', 'uday', 'vipin', 'vineet', 'vinod', 'vishnu',
    'thakur', 'choudhary', 'verma', 'gupta', 'yadav', 'patel',
    'shah', 'joshi', 'mehta', 'agarwal', 'tiwari', 'pandey', 'jain',
    'boy', 'bhai', 'bro', 'king', 'boss', 'mr', 'sir',
    'master', 'prince', 'sultan', 'lion', 'tiger', 'devil', 'ninja',
    'rocky', 'tony', 'sunny', 'bunny', 'shadow', 'hero', 'babu',
    # Naye trending
    'bad', 'wild', 'dark', 'royal', 'attitude', 'fire', 'pro', 'vip',
    'toxic', 'danger', 'single', 'silent', 'lone', 'wolf', 'mafia',
    'stylish', 'hacker', 'beast', 'hunter', 'assassin', 'killer',
    'demon', 'warrior', 'ghost', 'savage', 'reaper', 'gamer',
    'dragon', 'titan', 'alpha', 'omega', 'legend', 'spartan',
    'gladiator', 'commander', 'emperor', 'destroyer', 'predator', 'venom',
 'abhishek', 'abhi',
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
    'suresh', 'ramesh', 'naresh', 'ganesh', 'dinesh', 'mahesh',
    'venkat', 'venkatesh', 'ramu', 'krishnamurthy', 'murugan',
    'selvam', 'senthil', 'prakash', 'subramaniam', 'balaji',
    'gurpreet', 'gurjit', 'harpreet', 'jaspreet', 'manpreet',
    'navjot', 'paramjit', 'ranjit', 'surjit', 'amarjit',
    'mohammad', 'mohammed', 'muhammad', 'md', 'ali', 'khan',
    'sheikh', 'ansari', 'siddiqui', 'qureshi', 'hussain',
    'hassan', 'imran', 'irfan', 'danish', 'farhan', 'faisal',
    'salman', 'adnan', 'asif', 'arif', 'wasim', 'nazim',
    'zaid', 'zeeshan', 'aamir', 'amir', 'usman', 'umer',
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
    'sudha', 'subha', 'usha', 'alka', 'anupama',
    'lakshmi', 'kamala', 'kamali', 'meenakshi', 'revathi',
    'sumathi', 'bharati', 'vijayalakshmi', 'saraswathi',
    'padmavathi', 'annapurna', 'bhavani',
    'gurpreet', 'harpreet', 'manpreet', 'navpreet', 'simran',
    'jasleen', 'harleen', 'navneet', 'parmeet', 'jasveen',
    'fatima', 'fathima', 'aisha', 'ayesha', 'zainab', 'rukhsar',
    'shabnam', 'sana', 'sara', 'sarah', 'noor', 'hina', 'asma',
    'farida', 'reshma', 'nagma', 'nasreen', 'rubina', 'ruksana',
    'samina', 'tahira', 'yasmin', 'zara', 'zubaida',
    'girl', 'didi', 'behen', 'miss', 'mrs', 'ms', 'lady',
    'queen', 'princess', 'ladki', 'female', 'sweety', 'baby',
    'pinky', 'rinky', 'gudiya', 'soni', 'bittu',
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


def normalize_name(name: str) -> str:
    """Fancy Unicode fonts ko normal ASCII mein convert karo"""
    if not name:
        return ''
    result = ''
    for char in str(name):
        if char in FANCY_CHAR_MAP:
            result += FANCY_CHAR_MAP[char]
        elif ord(char) < 128:
            result += char
        else:
            result += char
    normalized = unicodedata.normalize('NFKD', result)
    ascii_name = ''.join(c for c in normalized if not unicodedata.combining(c))
    cleaned = ''.join(c for c in ascii_name if c.isprintable())
    return cleaned.strip() if cleaned.strip() else name


FANCY_CHAR_MAP = {
    # Bold lowercase
    '𝐚':'a','𝐛':'b','𝐜':'c','𝐝':'d','𝐞':'e','𝐟':'f','𝐠':'g','𝐡':'h',
    '𝐢':'i','𝐣':'j','𝐤':'k','𝐥':'l','𝐦':'m','𝐧':'n','𝐨':'o','𝐩':'p',
    '𝐪':'q','𝐫':'r','𝐬':'s','𝐭':'t','𝐮':'u','𝐯':'v','𝐰':'w','𝐱':'x',
    '𝐲':'y','𝐳':'z',
    # Bold uppercase
    '𝐀':'A','𝐁':'B','𝐂':'C','𝐃':'D','𝐄':'E','𝐅':'F','𝐆':'G','𝐇':'H',
    '𝐈':'I','𝐉':'J','𝐊':'K','𝐋':'L','𝐌':'M','𝐍':'N','𝐎':'O','𝐏':'P',
    '𝐐':'Q','𝐑':'R','𝐒':'S','𝐓':'T','𝐔':'U','𝐕':'V','𝐖':'W','𝐗':'X',
    '𝐘':'Y','𝐙':'Z',
    # Italic lowercase
    '𝑎':'a','𝑏':'b','𝑐':'c','𝑑':'d','𝑒':'e','𝑓':'f','𝑔':'g','𝒉':'h',
    '𝑖':'i','𝑗':'j','𝑘':'k','𝑙':'l','𝑚':'m','𝑛':'n','𝑜':'o','𝑝':'p',
    '𝑞':'q','𝑟':'r','𝑠':'s','𝑡':'t','𝑢':'u','𝑣':'v','𝑤':'w','𝑥':'x',
    '𝑦':'y','𝑧':'z',
    # Sans-serif bold lowercase
    '𝗮':'a','𝗯':'b','𝗰':'c','𝗱':'d','𝗲':'e','𝗳':'f','𝗴':'g','𝗵':'h',
    '𝗶':'i','𝗷':'j','𝗸':'k','𝗹':'l','𝗺':'m','𝗻':'n','𝗼':'o','𝗽':'p',
    '𝗾':'q','𝗿':'r','𝘀':'s','𝘁':'t','𝘂':'u','𝘃':'v','𝘄':'w','𝘅':'x',
    '𝘆':'y','𝘇':'z',
    # Sans-serif bold uppercase
    '𝗔':'A','𝗕':'B','𝗖':'C','𝗗':'D','𝗘':'E','𝗙':'F','𝗚':'G','𝗛':'H',
    '𝗜':'I','𝗝':'J','𝗞':'K','𝗟':'L','𝗠':'M','𝗡':'N','𝗢':'O','𝗣':'P',
    '𝗤':'Q','𝗥':'R','𝗦':'S','𝗧':'T','𝗨':'U','𝗩':'V','𝗪':'W','𝗫':'X',
    '𝗬':'Y','𝗭':'Z',
    # Circled lowercase
    'ⓐ':'a','ⓑ':'b','ⓒ':'c','ⓓ':'d','ⓔ':'e','ⓕ':'f','ⓖ':'g','ⓗ':'h',
    'ⓘ':'i','ⓙ':'j','ⓚ':'k','ⓛ':'l','ⓜ':'m','ⓝ':'n','ⓞ':'o','ⓟ':'p',
    'ⓠ':'q','ⓡ':'r','ⓢ':'s','ⓣ':'t','ⓤ':'u','ⓥ':'v','ⓦ':'w','ⓧ':'x',
    'ⓨ':'y','ⓩ':'z',
    # Fullwidth lowercase
    'ａ':'a','ｂ':'b','ｃ':'c','ｄ':'d','ｅ':'e','ｆ':'f','ｇ':'g','ｈ':'h',
    'ｉ':'i','ｊ':'j','ｋ':'k','ｌ':'l','ｍ':'m','ｎ':'n','ｏ':'o','ｐ':'p',
    'ｑ':'q','ｒ':'r','ｓ':'s','ｔ':'t','ｕ':'u','ｖ':'v','ｗ':'w','ｘ':'x',
    'ｙ':'y','ｚ':'z',
    # Fullwidth uppercase
    'Ａ':'A','Ｂ':'B','Ｃ':'C','Ｄ':'D','Ｅ':'E','Ｆ':'F','Ｇ':'G','Ｈ':'H',
    'Ｉ':'I','Ｊ':'J','Ｋ':'K','Ｌ':'L','Ｍ':'M','Ｎ':'N','Ｏ':'O','Ｐ':'P',
    'Ｑ':'Q','Ｒ':'R','Ｓ':'S','Ｔ':'T','Ｕ':'U','Ｖ':'V','Ｗ':'W','Ｘ':'X',
    'Ｙ':'Y','Ｚ':'Z',
}

def normalize_name(name: str) -> str:
    """Fancy Unicode fonts ko normal ASCII mein convert karo"""
    if not name:
        return ''
    result = ''
    for char in str(name):
        if char in FANCY_CHAR_MAP:
            result += FANCY_CHAR_MAP[char]
        elif ord(char) < 128:
            result += char
        else:
            result += char
    normalized = unicodedata.normalize('NFKD', result)
    ascii_name = ''.join(c for c in normalized if not unicodedata.combining(c))
    cleaned = ''.join(c for c in ascii_name if c.isprintable())
    return cleaned.strip() if cleaned.strip() else name


def detect_gender(name: str) -> str:
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
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Welcome to Gender Welcome Bot!</b>\n\n"
        "🔗 <b>Setup:</b>\n"
        "1. Bot ko group mein Admin banao\n"
        "2. Group mein <code>/connect</code> chalao\n"
        "3. Bot ke DM mein sab set karo!\n\n"
        "📋 <b>Commands:</b>\n"
        "/connect - Group connect karo\n"
        "/disconnect - Connection hatao\n"
        "/setwelcome male &lt;msg&gt;\n"
        "/setwelcome female &lt;msg&gt;\n"
        "/setwelcome neutral &lt;msg&gt;\n"
        "/setvideowelcome male - Video reply karke\n"
        "/setvideowelcome female - Video reply karke\n"
        "/showwelcome - Settings dekho\n"
        "/resetwelcome - Sab reset\n"
        "/testgender &lt;name&gt; - Gender test\n"
        "/admincheck - Admin check\n",
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


async def set_welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = await get_target_chat_id(update, context)
    if not chat_id:
        return

    override = int(chat_id) if update.effective_chat.type == 'private' else None
    if not await is_admin(update, context, chat_id_override=override):
        await update.message.reply_text("❌ Only admins can use this!")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ <b>Usage:</b>\n"
            "<code>/setwelcome male Welcome {name} bhai!</code>\n"
            "<code>/setwelcome female Welcome {name} didi!</code>\n"
            "<code>/setwelcome neutral Welcome {name}!</code>",
            parse_mode='HTML'
        )
        return

    gender = context.args[0].lower()
    if gender not in ['male', 'female', 'neutral']:
        await update.message.reply_text("❌ male, female, ya neutral likhao")
        return

    msg = ' '.join(context.args[1:])
    data = load_data()
    data.setdefault(chat_id, {}).setdefault('welcome_messages', {})[gender] = msg
    save_data(data)

    await update.message.reply_text(
        f"✅ <b>{gender.upper()} message set!</b>\n📝 {msg}",
        parse_mode='HTML'
    )


async def set_video_welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = await get_target_chat_id(update, context)
    if not chat_id:
        return

    override = int(chat_id) if update.effective_chat.type == 'private' else None
    if not await is_admin(update, context, chat_id_override=override):
        await update.message.reply_text("❌ Only admins can use this!")
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ Video reply karke:\n"
            "<code>/setvideowelcome male</code>\n"
            "<code>/setvideowelcome female</code>\n"
            "<code>/setvideowelcome neutral</code>",
            parse_mode='HTML'
        )
        return

    gender = context.args[0].lower()
    if gender not in ['male', 'female', 'neutral']:
        await update.message.reply_text("❌ male, female, ya neutral likhao")
        return

    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("❌ Kisi video ko reply karke ye command chalao!")
        return

    video = update.message.reply_to_message.video
    data = load_data()
    vlist = data.setdefault(chat_id, {}).setdefault('welcome_videos', {}).setdefault(gender, [])
    vlist.append({'file_id': video.file_id, 'caption': update.message.reply_to_message.caption or ''})
    save_data(data)

    await update.message.reply_text(
        f"✅ <b>{gender.upper()} video added!</b>\n"
        f"📹 Total {gender} videos: <b>{len(vlist)}</b>",
        parse_mode='HTML'
    )


async def show_welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = await get_target_chat_id(update, context)
    if not chat_id:
        return

    override = int(chat_id) if update.effective_chat.type == 'private' else None
    if not await is_admin(update, context, chat_id_override=override):
        await update.message.reply_text("❌ Only admins can use this!")
        return

    data = load_data()
    if chat_id not in data:
        await update.message.reply_text("ℹ️ Koi settings nahi hain abhi.")
        return

    msgs = data[chat_id].get('welcome_messages', {})
    vids = data[chat_id].get('welcome_videos', {})

    try:
        chat = await context.bot.get_chat(int(chat_id))
        title = chat.title
    except:
        title = chat_id

    resp = f"📋 <b>{title} — Settings</b>\n\n"
    for g in ['male', 'female', 'neutral']:
        e = '👨' if g == 'male' else '👩' if g == 'female' else '🧑'
        resp += f"<b>{e} {g.upper()}:</b>\n"
        resp += f"📝 {msgs.get(g, 'Not set')}\n"
        vc = len(vids.get(g, []))
        resp += f"🎥 {vc} video {'✅' if vc else '❌'}\n\n"

    await update.message.reply_text(resp, parse_mode='HTML')


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

    await update.message.reply_text("✅ Saari settings reset ho gayi!")


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
    gender = detect_gender(name)

    await update.message.reply_text(
        f"🔍 <b>Gender Test</b>\n\n"
        f"👤 Original: <b>{name}</b>\n"
        f"✏️ Normalized: <b>{normalized}</b>\n"
        f"⚡ Result: <b>{gender.upper()}</b>",
        parse_mode='HTML'
    )


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

    full_name = f"{new_member.first_name} {new_member.last_name}".strip() if new_member.last_name else new_member.first_name or "New Member"
    username = f"@{new_member.username}" if new_member.username else full_name
    user_mention = f'<a href="tg://user?id={new_member.id}">{full_name}</a>'

    gender = detect_gender(full_name)
    logger.info(f"NEW MEMBER: '{full_name}' | gender={gender}")

    if gender == 'neutral':
        data = load_data()
        group_data = data.get(chat_id, {})
        neutral_msg = group_data.get('welcome_messages', {}).get('neutral', '')

        if neutral_msg:
            neutral_msg = replace_vars(neutral_msg, full_name, username, user_mention, 'neutral')
        else:
            neutral_msg = f"👋 Welcome {user_mention}!\n\nHamare group mein swagat hai! 🙏"

        neutral_videos = group_data.get('welcome_videos', {}).get('neutral', [])

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("👨 Ladka Hoon", callback_data=f"gm|{new_member.id}|{chat_id}"),
            InlineKeyboardButton("👩 Ladki Hoon", callback_data=f"gf|{new_member.id}|{chat_id}")
        ]])

        question = f"\n\n❓ {user_mention} aap kaun hain?\n👇 Neeche click karo!"

        try:
            if neutral_videos:
                vd = random.choice(neutral_videos)
                cap = replace_vars(vd.get('caption', ''), full_name, username, user_mention, 'neutral')
                final_cap = f"{neutral_msg}\n\n{cap}{question}" if cap else f"{neutral_msg}{question}"
                await context.bot.send_video(
                    chat_id=int(chat_id), video=vd['file_id'],
                    caption=final_cap, reply_markup=keyboard, parse_mode='HTML'
                )
            else:
                await context.bot.send_message(
                    chat_id=int(chat_id),
                    text=f"{neutral_msg}{question}",
                    reply_markup=keyboard, parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Neutral welcome error: {e}")
    else:
        await send_gender_welcome(context, chat_id, new_member.id, full_name, username, gender)


async def gender_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('|')
    if len(parts) < 3:
        await query.answer("❌ Invalid button!")
        return

    gender = 'male' if parts[0] == 'gm' else 'female'
    target_user_id = int(parts[1])
    chat_id = parts[2]

    if query.from_user.id != target_user_id:
        await query.answer("❌ Ye button sirf naye member ke liye hai!", show_alert=True)
        return

    await query.answer("✅ Shukriya!")

    try:
        await query.message.delete()
    except:
        pass

    user = query.from_user
    full_name = f"{user.first_name} {user.last_name}".strip() if user.last_name else user.first_name or "New Member"
    username = f"@{user.username}" if user.username else full_name

    await send_gender_welcome(context, chat_id, target_user_id, full_name, username, gender)


def main():
    print("🤖 Starting Gender Welcome Bot...")
    print("✅ 3-Layer Gender Detection Active!")
    print("✅ Bot is running!")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("connect", connect_command))
    application.add_handler(CommandHandler("disconnect", disconnect_command))
    application.add_handler(CommandHandler("setwelcome", set_welcome_command))
    application.add_handler(CommandHandler("setvideowelcome", set_video_welcome_command))
    application.add_handler(CommandHandler("showwelcome", show_welcome_command))
    application.add_handler(CommandHandler("resetwelcome", reset_welcome_command))
    application.add_handler(CommandHandler("admincheck", admincheck_command))
    application.add_handler(CommandHandler("testgender", testgender_command))
    application.add_handler(CallbackQueryHandler(gender_button_callback, pattern=r'^g[mf]\|'))
    application.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
