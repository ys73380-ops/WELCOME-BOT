"""
╔══════════════════════════════════════════════════════════╗
║           ADVANCED TELEGRAM WELCOME BOT                  ║
║   Male/Female alag video + Genderize.io API support      ║
╚══════════════════════════════════════════════════════════╝
"""

import logging
import json
import os
import re
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
)
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

# ══════════════════════════════════════════════════════════
#  CONFIG — .env se aata hai (Railway / local dono mein)
# ══════════════════════════════════════════════════════════
BOT_TOKEN       = os.environ.get("BOT_TOKEN", "")
GENDERIZE_API   = os.environ.get("GENDERIZE_API_KEY", "")   # optional, free tier bhi kaam karta hai
SETTINGS_FILE   = os.environ.get("SETTINGS_FILE", "bot_settings.json")

# ══════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
#  SETTINGS MANAGER
# ══════════════════════════════════════════════════════════
def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_settings(data: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_group_settings(group_id: int) -> dict:
    return load_settings().get(str(group_id), {})

def set_group_key(group_id: int, key: str, value):
    settings = load_settings()
    gid = str(group_id)
    if gid not in settings:
        settings[gid] = {}
    settings[gid][key] = value
    save_settings(settings)

def delete_group_key(group_id: int, key: str = None):
    settings = load_settings()
    gid = str(group_id)
    if gid in settings:
        if key:
            settings[gid].pop(key, None)
        else:
            del settings[gid]
    save_settings(settings)


# ══════════════════════════════════════════════════════════
#  ADMIN CHECK
# ══════════════════════════════════════════════════════════
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, group_id: int = None) -> bool:
    user_id = update.effective_user.id
    chat_id = group_id or update.effective_chat.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except TelegramError:
        return False


# ══════════════════════════════════════════════════════════
#  GENDER DETECTION
#  Layer 1 → Genderize.io API
#  Layer 2 → Local name database (fallback)
# ══════════════════════════════════════════════════════════
MALE_NAMES = {
    "aarav","aditya","akash","amit","ankit","arjun","aryan","ayush","deepak",
    "dev","dhruv","gaurav","harsh","kartik","karan","kunal","manish","mohit",
    "nikhil","nishant","pranav","rahul","raj","rajesh","ravi","rishabh","rohit",
    "rohan","sachin","sahil","sanjay","shubham","siddharth","sumit","suraj",
    "tarun","tushar","uday","varun","vikas","vikram","vivek","yash","yuvraj",
    "abhishek","advait","aman","vishal","piyush","mukesh","ramesh","suresh",
    "dinesh","mahesh","naresh","lokesh","hitesh","ritesh","rakesh","nilesh",
    "girish","kamlesh","brijesh","shailesh","yogesh","rajat","ronit","kush",
    "om","param","parth","pratik","chirag","bhavesh","hardik","jatin","lalit",
    "manan","neel","paras","ruchit","sagar","tej","umang","james","john",
    "robert","michael","william","david","richard","thomas","charles",
    "christopher","daniel","matthew","anthony","mark","liam","noah","oliver",
    "elijah","lucas","mason","ethan","logan","ali","muhammad","omar","hassan",
    "ibrahim","karim","yusuf","ahmed","rajan","qasim",
}

FEMALE_NAMES = {
    "aisha","alka","ananya","anjali","ankita","anushka","arpita","deepika",
    "divya","garima","ishita","kajal","kavya","khushi","komal","kritika",
    "mansi","megha","meera","muskan","namrata","neha","nikita","nisha",
    "pallavi","pooja","prachi","pragya","preeti","priya","radha","ritu","riya",
    "sakshi","sandhya","shruti","simran","sneha","sonam","srishti","swati",
    "tanvi","tanya","trisha","vandana","vidya","zara","diya","yukta","amrita",
    "ayesha","bhavna","charu","damini","ekta","falak","gunjan","harshita",
    "indira","janvi","kamini","lavanya","madhu","nandini","parul","rekha",
    "savita","taruna","uma","vaishnavi","sarah","emily","emma","olivia","ava",
    "sophia","isabella","mia","amelia","harper","evelyn","abigail","elizabeth",
    "sofia","ella","grace","chloe","penelope","layla","fatima","maryam",
    "amina","hana","sara","leila","yasmin","noor","zainab","chanchal","dimple",
    "esha","heena","isha","jyoti","kiran","lata","minal","nitu","payal",
    "reena","seema","usha","yamini",
}


async def detect_gender_api(first_name: str) -> str | None:
    """
    Genderize.io API se gender detect karta hai.
    Returns: 'male', 'female', ya None
    Probability 0.7 se kam ho toh None return karta hai (uncertain).
    """
    if not first_name:
        return None

    clean_name = re.sub(r"[^a-zA-Z]", "", first_name).lower()
    if not clean_name:
        return None

    try:
        url    = "https://api.genderize.io"
        params = {"name": clean_name}
        if GENDERIZE_API:
            params["apikey"] = GENDERIZE_API

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                data        = await resp.json()
                gender      = data.get("gender")          # 'male' / 'female' / null
                probability = data.get("probability", 0)  # 0.0 – 1.0

                if gender and probability >= 0.70:
                    logger.info(f"Genderize: {first_name} → {gender} ({probability:.0%})")
                    return gender
                else:
                    logger.info(f"Genderize: {first_name} → uncertain ({probability:.0%})")
                    return None

    except Exception as e:
        logger.warning(f"Genderize API error: {e}")
        return None


def detect_gender_db(first_name: str, last_name: str = "") -> str | None:
    """Local name database se gender detect karta hai (fallback)."""
    full  = f"{first_name} {last_name}".lower().strip()
    words = re.findall(r"[a-z]+", full)
    for word in words:
        if word in MALE_NAMES:
            return "male"
        if word in FEMALE_NAMES:
            return "female"
    return None


async def detect_gender(first_name: str, last_name: str = "") -> str | None:
    """
    Gender detect karta hai — pehle API, phir DB fallback.
    Returns: 'male', 'female', ya None (dono se pata nahi chala)
    """
    # Layer 1: Genderize.io API
    gender = await detect_gender_api(first_name)
    if gender:
        return gender

    # Layer 2: Local database
    gender = detect_gender_db(first_name, last_name)
    if gender:
        logger.info(f"DB fallback: {first_name} {last_name} → {gender}")
        return gender

    return None


# ══════════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════════
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 *Namaste, {user.first_name}!*\n\n"
        "Main *Advanced Welcome Bot* hoon 🤖\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *Commands:*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔗 `/connect`\n"
        "   Group se DM mein aao setup ke liye\n\n"
        "🎬 `/setvideo_male`\n"
        "   Male ka video + welcome msg set karo\n"
        "   _Video ko reply karo is command se_\n\n"
        "🎀 `/setvideo_female`\n"
        "   Female ka video + welcome msg set karo\n"
        "   _Video ko reply karo is command se_\n\n"
        "👁 `/showset`\n"
        "   Current settings dekho\n\n"
        "🗑 `/delete`\n"
        "   Settings delete karo\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *Tip:* Welcome msg mein `{name}` aur `{username}` likhoge\n"
        "toh automatically replace ho jayega!\n\n"
        "⚠️ _Sirf group admin/owner commands use kar sakte hain_",
        parse_mode="Markdown"
    )


# ══════════════════════════════════════════════════════════
#  /connect
# ══════════════════════════════════════════════════════════
async def connect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        gid   = context.user_data.get("active_group_id")
        gname = context.user_data.get("active_group_name", "—")
        status = f"*Active Group:* {gname}" if gid else "⚠️ Koi group connected nahi.\nPehle group mein /connect chalao."
        await update.message.reply_text(
            f"🔗 *Bot Connection Status*\n\n{status}\n\n"
            "Ab `/setvideo_male` ya `/setvideo_female` se settings karo.",
            parse_mode="Markdown"
        )
        return

    if not await is_admin(update, context):
        await update.message.reply_text("❌ Sirf admin/owner yeh command use kar sakte hain.")
        return

    context.user_data["active_group_id"]   = chat.id
    context.user_data["active_group_name"] = chat.title

    bot_me = await context.bot.get_me()
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("🤖 Bot DM Mein Kholo", url=f"https://t.me/{bot_me.username}?start=setup")
    ]])
    await update.message.reply_text(
        f"🔗 *{chat.title}* ke liye setup shuru karo!\n\n"
        "Neeche button dabao — DM mein jao aur settings karo 👇",
        reply_markup=btn,
        parse_mode="Markdown"
    )


# ══════════════════════════════════════════════════════════
#  /setvideo_male  &  /setvideo_female
# ══════════════════════════════════════════════════════════
async def _setvideo(update: Update, context: ContextTypes.DEFAULT_TYPE, gender: str):
    chat = update.effective_chat
    user = update.effective_user
    msg  = update.message

    if chat.type == "private":
        group_id   = context.user_data.get("active_group_id")
        group_name = context.user_data.get("active_group_name", "Group")
        if not group_id:
            await msg.reply_text("⚠️ Pehle group mein `/connect` chalao, phir yahan aao.", parse_mode="Markdown")
            return
    else:
        if not await is_admin(update, context):
            await msg.reply_text("❌ Sirf admin/owner yeh command use kar sakte hain.")
            return
        group_id   = chat.id
        group_name = chat.title

    reply     = msg.reply_to_message
    video_fid = None
    if reply:
        if reply.video:
            video_fid = reply.video.file_id
        elif reply.animation:
            video_fid = reply.animation.file_id
        elif reply.document and reply.document.mime_type and "video" in reply.document.mime_type:
            video_fid = reply.document.file_id

    welcome_text = " ".join(context.args).strip() if context.args else ""

    emoji = "🎬" if gender == "male" else "🎀"
    label = "Male (Boy)" if gender == "male" else "Female (Girl)"

    if video_fid:
        set_group_key(group_id, f"{gender}_video_id", video_fid)
    if welcome_text:
        set_group_key(group_id, f"{gender}_welcome_msg", welcome_text)

    lines = [
        f"{emoji} *{label} Settings Updated!*\n",
        f"🏠 *Group:* {group_name}\n",
        f"📹 *Video:*    {'✅ Save ho gaya' if video_fid else '⚠️ Video reply nahi ki — purana rahega'}",
        f"💬 *Msg:*      {'✅ Save ho gaya' if welcome_text else 'ℹ️ Nahi diya — purana rahega'}",
    ]
    if welcome_text:
        lines.append(f"\n📝 *Saved Msg:*\n`{welcome_text}`")

    await msg.reply_text("\n".join(lines), parse_mode="Markdown")
    logger.info(f"[{group_name}] {label} settings updated by @{user.username or user.id}")


async def setvideo_male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _setvideo(update, context, "male")

async def setvideo_female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _setvideo(update, context, "female")


# ══════════════════════════════════════════════════════════
#  /showset
# ══════════════════════════════════════════════════════════
async def showset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type == "private":
        group_id   = context.user_data.get("active_group_id")
        group_name = context.user_data.get("active_group_name", "Group")
        if not group_id:
            await update.message.reply_text("⚠️ Pehle group mein `/connect` chalao.", parse_mode="Markdown")
            return
    else:
        if not await is_admin(update, context):
            await update.message.reply_text("❌ Sirf admin/owner settings dekh sakte hain.")
            return
        group_id   = chat.id
        group_name = chat.title

    s = get_group_settings(group_id)
    ok = lambda v: "✅ Set hai" if v else "❌ Set nahi"

    await update.message.reply_text(
        f"📋 *Settings — {group_name}*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎬 *Male (Boy) Settings:*\n"
        f"   📹 Video  : {ok(s.get('male_video_id'))}\n"
        f"   💬 Msg    :\n"
        f"   `{s.get('male_welcome_msg', '❌ Set nahi')}`\n\n"
        "🎀 *Female (Girl) Settings:*\n"
        f"   📹 Video  : {ok(s.get('female_video_id'))}\n"
        f"   💬 Msg    :\n"
        f"   `{s.get('female_welcome_msg', '❌ Set nahi')}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )


# ══════════════════════════════════════════════════════════
#  /delete
# ══════════════════════════════════════════════════════════
async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type == "private":
        group_id   = context.user_data.get("active_group_id")
        group_name = context.user_data.get("active_group_name", "Group")
        if not group_id:
            await update.message.reply_text("⚠️ Pehle group mein `/connect` chalao.", parse_mode="Markdown")
            return
    else:
        if not await is_admin(update, context):
            await update.message.reply_text("❌ Sirf admin/owner delete kar sakte hain.")
            return
        group_id   = chat.id
        group_name = chat.title

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Male Delete",   callback_data=f"del_male_{group_id}"),
            InlineKeyboardButton("🎀 Female Delete", callback_data=f"del_female_{group_id}"),
        ],
        [InlineKeyboardButton("🗑 Sab Delete Karo", callback_data=f"del_all_{group_id}")],
        [InlineKeyboardButton("❌ Cancel",           callback_data="del_cancel")],
    ])
    await update.message.reply_text(
        f"🗑 *{group_name}* — Kya delete karna hai?",
        reply_markup=kb,
        parse_mode="Markdown"
    )


async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if data == "del_cancel":
        await query.edit_message_text("✅ Delete cancel kar diya.")
        return

    parts    = data.split("_")
    action   = parts[1]
    group_id = int(parts[2])

    if action == "male":
        delete_group_key(group_id, "male_video_id")
        delete_group_key(group_id, "male_welcome_msg")
        await query.edit_message_text("✅ Male settings delete ho gayi!")
    elif action == "female":
        delete_group_key(group_id, "female_video_id")
        delete_group_key(group_id, "female_welcome_msg")
        await query.edit_message_text("✅ Female settings delete ho gayi!")
    elif action == "all":
        delete_group_key(group_id)
        await query.edit_message_text("✅ Saari settings delete ho gayi!")


# ══════════════════════════════════════════════════════════
#  WELCOME SENDER
# ══════════════════════════════════════════════════════════
async def send_welcome(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user,
    gender: str,
    group_name: str
):
    s         = get_group_settings(chat_id)
    video_id  = s.get(f"{gender}_video_id")
    saved_msg = s.get(f"{gender}_welcome_msg", "")

    name     = user.full_name or user.first_name or "Dost"
    username = f"@{user.username}" if user.username else name
    emoji    = "💙" if gender == "male" else "💗"
    bhai_ben = "Bhai" if gender == "male" else "Behen"

    if saved_msg:
        final = saved_msg.replace("{name}", name).replace("{username}", username)
    else:
        final = (
            f"{emoji} *Swagat hai, {name}!*\n\n"
            f"👤 Username : {username}\n"
            f"🏠 Group    : *{group_name}*\n\n"
            f"Apne group mein tumhara dil se swagat hai, {bhai_ben}! 🎉\n\n"
            f"📌 Rules follow karo, masti karo aur seekhte raho! 🚀"
        )

    if video_id:
        try:
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_id,
                caption=final,
                parse_mode="Markdown"
            )
            return
        except TelegramError as e:
            logger.warning(f"Video send error: {e}")

    await context.bot.send_message(chat_id=chat_id, text=final, parse_mode="Markdown")


# ══════════════════════════════════════════════════════════
#  GENDER BUTTON CALLBACK
#  Format: gender_GENDER_USERID_CHATID
#  Sirf wahi user click kar sakta hai jiske liye button hai
# ══════════════════════════════════════════════════════════
async def gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    data    = query.data
    clicker = update.effective_user.id

    parts = data.split("_")
    if len(parts) < 4:
        await query.answer()
        return

    gender   = parts[1]
    user_id  = int(parts[2])
    chat_id  = int(parts[3])

    # ✅ Sirf wahi user click kare jiske liye button hai
    if clicker != user_id:
        await query.answer(
            "❌ Yeh button sirf naye member ke liye hai!",
            show_alert=True
        )
        return

    await query.answer(f"{'👦 Boy' if gender == 'male' else '👧 Girl'} select kiya!")

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        user   = member.user
    except TelegramError:
        user = update.effective_user

    try:
        chat_obj   = await context.bot.get_chat(chat_id)
        group_name = chat_obj.title or "Group"
    except TelegramError:
        group_name = "Group"

    # Button wala message delete karo
    try:
        await query.message.delete()
    except TelegramError:
        pass

    await send_welcome(context, chat_id, user, gender, group_name)
    logger.info(f"Gender selected: {gender} for {user.full_name} in {group_name}")


# ══════════════════════════════════════════════════════════
#  NEW MEMBER JOIN HANDLER
# ══════════════════════════════════════════════════════════
async def greet_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result     = update.chat_member
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    joined = (
        new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR) and
        old_status not in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)
    )
    if not joined:
        return

    user = result.new_chat_member.user
    chat = update.effective_chat

    if user.is_bot:
        return

    group_name = chat.title or "Group"
    name       = user.full_name or user.first_name or "Dost"
    username   = f"@{user.username}" if user.username else name

    logger.info(f"New member: {name} ({username}) in {group_name}")

    # Gender detect — API + DB fallback
    gender = await detect_gender(user.first_name or "", user.last_name or "")

    if gender:
        await send_welcome(context, chat.id, user, gender, group_name)
    else:
        # Gender unknown → sirf us member ko button dikhao
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("👦 Boy hoon",  callback_data=f"gender_male_{user.id}_{chat.id}"),
            InlineKeyboardButton("👧 Girl hoon", callback_data=f"gender_female_{user.id}_{chat.id}"),
        ]])

        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                f"👋 *{name}* ka swagat!\n"
                f"👤 Username: {username}\n\n"
                f"Hame batao tum kaun ho? 😊\n"
                f"_Sirf tum hi yeh button daba sakte ho_ 👇"
            ),
            reply_markup=kb,
            parse_mode="Markdown"
        )


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════
def main():
    if not BOT_TOKEN:
        print("\n" + "=" * 52)
        print("  ❌  BOT_TOKEN set nahi hai!")
        print("  Railway pe: Variables mein BOT_TOKEN daalo")
        print("  Local pe:   .env file mein BOT_TOKEN=xxx likhो")
        print("=" * 52 + "\n")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",           start_command))
    app.add_handler(CommandHandler("connect",         connect_command))
    app.add_handler(CommandHandler("setvideo_male",   setvideo_male))
    app.add_handler(CommandHandler("setvideo_female", setvideo_female))
    app.add_handler(CommandHandler("showset",         showset_command))
    app.add_handler(CommandHandler("delete",          delete_command))

    app.add_handler(CallbackQueryHandler(gender_callback, pattern=r"^gender_"))
    app.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del_"))

    app.add_handler(ChatMemberHandler(greet_new_member, ChatMemberHandler.CHAT_MEMBER))

    logger.info("🤖 Welcome Bot chal raha hai! (Ctrl+C se band karo)")
    app.run_polling(allowed_updates=["message", "chat_member", "callback_query"])


if __name__ == "__main__":
    main()
