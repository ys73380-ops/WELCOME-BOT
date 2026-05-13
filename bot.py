"""
╔══════════════════════════════════════════════════════════════╗
║ ADVANCED TELEGRAM WELCOME BOT v2.1                         ║
║ Gender-based Welcome · Genderize.io · Redis + JSON         ║
╚══════════════════════════════════════════════════════════════╝

STORAGE: Redis (primary) + JSON (fallback)
Railway: Add Redis plugin → auto REDIS_URL
Local: pip install redis
"""

import asyncio, aiohttp, logging, json, os, re
from pathlib import Path
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ChatMemberHandler, ContextTypes,
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GENDERIZE_API_KEY = os.environ.get("GENDERIZE_API_KEY", "")
SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "bot_settings.json")
REDIS_URL = os.environ.get("REDIS_URL", "")

logging.basicConfig(
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
# MARKDOWN ESCAPER — Unicode names/groups ke liye
# ══════════════════════════════════════════════════════════
def esc(text: str) -> str:
    """Escape special chars for Telegram Markdown so Unicode names don't crash."""
    if not text:
        return text
    return (text
        .replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("~", "\\~")
        .replace("|", "\\|")
        .replace(">", "\\>")
        .replace("#", "\\#")
        .replace("-", "\\-")
        .replace("+", "\\+")
        .replace("=", "\\=")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace(".", "\\.")
        .replace("!", "\\!"))


# ══════════════════════════════════════════════════════════
# STORAGE: Redis + JSON dual storage
# ══════════════════════════════════════════════════════════
_redis_conn = None
_json_lock = asyncio.Lock()


async def _get_redis():
    global _redis_conn
    if _redis_conn is None and REDIS_URL:
        try:
            import redis.asyncio as aioredis
            _redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
            await _redis_conn.ping()
            logger.info("Redis connected")
        except Exception as e:
            logger.error(f"Redis failed: {e}")
            _redis_conn = False
    return _redis_conn if _redis_conn else None


def _load_json() -> dict:
    path = Path(SETTINGS_FILE)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


async def _save_json(data: dict):
    async with _json_lock:
        path = Path(SETTINGS_FILE)
        try:
            tmp = path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except OSError as e:
            logger.error(f"JSON save error: {e}")


async def get_group_settings(group_id: int) -> dict:
    gid = str(group_id)
    r = await _get_redis()
    if r:
        try:
            raw = await r.get(f"wb:{gid}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return _load_json().get(gid, {})


async def set_group_key(group_id: int, key: str, value):
    gid = str(group_id)
    r = await _get_redis()
    settings = {}
    if r:
        try:
            raw = await r.get(f"wb:{gid}")
            if raw:
                settings = json.loads(raw)
        except Exception:
            pass
    if not settings:
        settings = _load_json().get(gid, {})

    settings[key] = value
    js = json.dumps(settings, ensure_ascii=False)

    if r:
        try:
            await r.set(f"wb:{gid}", js)
        except Exception:
            pass
    all_s = _load_json()
    all_s[gid] = settings
    await _save_json(all_s)
    logger.info(f"[{gid}] Saved {key}")


async def delete_group_key(group_id: int, key: str = None):
    gid = str(group_id)
    r = await _get_redis()

    if key:
        s = await get_group_settings(group_id)
        s.pop(key, None)
        if not s:
            if r:
                try: await r.delete(f"wb:{gid}")
                except: pass
            all_s = _load_json()
            all_s.pop(gid, None)
            await _save_json(all_s)
        else:
            js = json.dumps(s, ensure_ascii=False)
            if r:
                try: await r.set(f"wb:{gid}", js)
                except: pass
            all_s = _load_json()
            all_s[gid] = s
            await _save_json(all_s)
    else:
        if r:
            try: await r.delete(f"wb:{gid}")
            except: pass
        all_s = _load_json()
        all_s.pop(gid, None)
        await _save_json(all_s)


# ══════════════════════════════════════════════════════════
# ADMIN CHECK
# ══════════════════════════════════════════════════════════
async def is_admin(update, context, group_id=None) -> bool:
    uid = update.effective_user.id
    cid = group_id or update.effective_chat.id
    try:
        m = await context.bot.get_chat_member(cid, uid)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except TelegramError:
        return False


# ══════════════════════════════════════════════════════════
# GENDER DETECTION
# ══════════════════════════════════════════════════════════
MALE_NAMES = {
    "aarav","aditya","akash","amit","ankit","arjun","aryan","ayush",
    "deepak","dev","dhruv","gaurav","harsh","kartik","karan","kunal",
    "manish","mohit","nikhil","nishant","pranav","rahul","raj","rajesh",
    "ravi","rishabh","rohit","rohan","sachin","sahil","sanjay","shubham",
    "siddharth","sumit","suraj","tarun","tushar","uday","varun","vikas",
    "vikram","vivek","yash","yuvraj","abhishek","advait","aman","vishal",
    "piyush","mukesh","ramesh","suresh","dinesh","mahesh","naresh",
    "lokesh","hitesh","ritesh","rakesh","nilesh","girish","kamlesh",
    "brijesh","shailesh","yogesh","rajat","ronit","kush","om","param",
    "parth","pratik","chirag","bhavesh","hardik","jatin","lalit",
    "manan","neel","paras","ruchit","sagar","tej","umang",
    "james","john","robert","michael","william","david","richard",
    "thomas","charles","christopher","daniel","matthew","anthony",
    "mark","liam","noah","oliver","elijah","lucas","mason","ethan",
    "logan","alex","ben","jack","ryan","nathan","samuel","andrew",
    "ali","muhammad","omar","hassan","ibrahim","karim","yusuf",
    "ahmed","rajan","qasim",
}
FEMALE_NAMES = {
    "aisha","alka","ananya","anjali","ankita","anushka","arpita",
    "deepika","divya","garima","ishita","kajal","kavya","khushi",
    "komal","kritika","mansi","megha","meera","muskan","namrata",
    "neha","nikita","nisha","pallavi","pooja","prachi","pragya",
    "preeti","priya","radha","ritu","riya","sakshi","sandhya",
    "shruti","simran","sneha","sonam","srishti","swati","tanvi",
    "tanya","trisha","vandana","vidya","zara","diya","yukta",
    "amrita","ayesha","bhavna","charu","damini","ekta","falak",
    "gunjan","harshita","indira","janvi","kamini","lavanya","madhu",
    "nandini","parul","rekha","savita","taruna","uma","vaishnavi",
    "chanchal","dimple","esha","heena","isha","jyoti","kiran",
    "lata","minal","nitu","payal","reena","seema","usha","yamini",
    "sarah","emily","emma","olivia","ava","sophia","isabella",
    "mia","amelia","harper","evelyn","abigail","elizabeth","sofia",
    "ella","grace","chloe","penelope","layla","lily","zoe",
    "fatima","maryam","amina","hana","sara","leila","yasmin",
    "noor","zainab",
}


async def detect_gender_api(name: str) -> Optional[str]:
    if not name:
        return None
    clean = re.sub(r"[^a-zA-Z]", "", name).lower()
    if not clean:
        return None
    try:
        p = {"name": clean}
        if GENDERIZE_API_KEY:
            p["apikey"] = GENDERIZE_API_KEY
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.genderize.io", params=p, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status != 200:
                    return None
                d = await r.json()
                g, prob = d.get("gender"), d.get("probability", 0)
                if g and prob >= 0.70:
                    return g
                return None
    except Exception:
        return None


def detect_gender_db(first: str, last: str = "") -> Optional[str]:
    for w in re.findall(r"[a-z]+", f"{first} {last}".lower()):
        if w in MALE_NAMES: return "male"
        if w in FEMALE_NAMES: return "female"
    return None


async def detect_gender(first: str, last: str = "") -> Optional[str]:
    g = await detect_gender_api(first)
    if g: return g
    return detect_gender_db(first, last)


# ══════════════════════════════════════════════════════════
# MESSAGE FORMATTER — escapes dynamic content
# ══════════════════════════════════════════════════════════
def fmt(template: str, name: str, username: str, group: str) -> str:
    return (template
        .replace("{name}", esc(name))
        .replace("{username}", esc(username))
        .replace("{group}", esc(group)))

DEFAULT_MALE = (
    "💙 *Swagat hai, {name}!*\n\n"
    "👤 Username: {username}\n"
    "🏠 Group: *{group}*\n\n"
    "Bhai group mein tumhara dil se swagat hai! 🎉\n\n"
    "📌 Rules follow karo, masti karo aur seekhte raho! 🚀"
)
DEFAULT_FEMALE = (
    "💗 *Swagat hai, {name}!*\n\n"
    "👤 Username: {username}\n"
    "🏠 Group: *{group}*\n\n"
    "Behen group mein tumhara dil se swagat hai! 🎉\n\n"
    "📌 Rules follow karo, masti karo aur seekhte raho! 🚀"
)


# ══════════════════════════════════════════════════════════
# SAFE SEND HELPER — auto fallback if Markdown fails
# ══════════════════════════════════════════════════════════
async def safe_send(context, chat_id, text, reply_markup=None, **kwargs):
    """Try Markdown, fallback to plain text on parse error."""
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    except TelegramError:
        # Strip all Markdown and send plain
        clean = text.replace("*", "").replace("_", "").replace("`", "").replace("\\", "")
        await context.bot.send_message(
            chat_id=chat_id, text=clean,
            reply_markup=reply_markup
        )


# ══════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    n = esc(u.first_name or "Dost")
    await safe_send(context, update.effective_chat.id,
        f"👋 *Namaste, {n}!*\n\n"
        "Main *Welcome Bot* hoon 🤖\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *Commands:*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔗 `/connect` — Group → DM\n"
        "🎬 `/setvideo_male` — Boy video+msg\n"
        "🎀 `/setvideo_female` — Girl video+msg\n"
        "👁 `/showset` — Settings dekho\n"
        "🗑 `/delete` — Delete\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ _Admin/owner only_"
    )


# ══════════════════════════════════════════════════════════
# /connect
# ══════════════════════════════════════════════════════════
async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = esc(context.user_data.get("active_group_name", "—"))
        if gid:
            txt = f"✅ *Connected:* {gn}\n📁 ID: `{gid}`"
        else:
            txt = "⚠️ Koi group connected nahi.\n_Pehle group mein `/connect` chalao._"
        await safe_send(context, chat.id, f"🔗 *Status*\n\n{txt}")
        return

    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Sirf admin/owner.")
    context.user_data["active_group_id"] = chat.id
    context.user_data["active_group_name"] = chat.title
    me = await context.bot.get_me()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🤖 DM Kholo", url=f"https://t.me/{me.username}?start=setup")]])
    await safe_send(context, chat.id,
        f"🔗 *{esc(chat.title)}* connected!\n📁 ID: `{chat.id}`\n\nDM mein jaake settings karo 👇",
        reply_markup=kb
    )
    logger.info(f"Connected: {chat.title} ({chat.id})")


# ══════════════════════════════════════════════════════════
# /setvideo_male & /setvideo_female
# ══════════════════════════════════════════════════════════
async def _setvideo(update: Update, context: ContextTypes.DEFAULT_TYPE, gender: str):
    chat = update.effective_chat
    msg = update.message

    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = context.user_data.get("active_group_name", "Group")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ Pehle group mein `/connect` chalao.")
    else:
        if not await is_admin(update, context):
            return await msg.reply_text("❌ Sirf admin/owner.")
        gid, gn = chat.id, chat.title

    reply = msg.reply_to_message
    vid = None
    if reply:
        if reply.video: vid = reply.video.file_id
        elif reply.animation: vid = reply.animation.file_id
        elif reply.document and reply.document.mime_type and "video" in reply.document.mime_type:
            vid = reply.document.file_id

    wmsg = " ".join(context.args).strip() if context.args else ""

    emoji = "🎬" if gender == "male" else "🎀"
    label = "Male (Boy)" if gender == "male" else "Female (Girl)"

    if vid:
        await set_group_key(gid, f"{gender}_video_id", vid)
    if wmsg:
        await set_group_key(gid, f"{gender}_welcome_msg", wmsg)

    # Verify
    check = await get_group_settings(gid)
    got_vid = check.get(f"{gender}_video_id")
    got_msg = check.get(f"{gender}_welcome_msg", "")

    logger.info(f"[{gn}] SET {label}: video={'YES' if got_vid else 'NO'}, msg={'YES' if got_msg else 'NO'} (gid={gid})")

    lines = [
        f"{emoji} *{label} Updated!*\n",
        f"🏠 Group: *{esc(gn)}* `{gid}`\n",
        f"📹 Video: {'✅ Saved' if got_vid else '❌ Not saved'}",
        f"💬 Message: {'✅ Saved' if got_msg else '❌ Not saved'}",
    ]
    if got_msg:
        preview = fmt(got_msg, "Sample Name", "@sample", gn)
        lines.append(f"\n📝 *Preview:*\n{preview}")
    if not vid and not wmsg:
        lines.append("\n⚠️ Kuch save nahi hua! Video reply ya message likho.")

    await safe_send(context, chat.id, "\n".join(lines))


async def setvideo_male(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _setvideo(update, context, "male")

async def setvideo_female(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _setvideo(update, context, "female")


# ══════════════════════════════════════════════════════════
# /showset
# ══════════════════════════════════════════════════════════
async def showset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = context.user_data.get("active_group_name", "Group")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ `/connect` pehle.")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Sirf admin/owner.")
        gid, gn = chat.id, chat.title

    s = await get_group_settings(gid)
    ok = lambda v: "✅" if v else "❌"

    await safe_send(context, chat.id,
        f"📋 *Settings — {esc(gn)}*\n"
        f"📁 ID: `{gid}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎬 *Male:*\n"
        f"   📹 {ok(s.get('male_video_id'))}\n"
        f"   💬 {ok(s.get('male_welcome_msg'))}\n"
        f"   └─ `{esc(s.get('male_welcome_msg', '(default)'))}`\n\n"
        f"🎀 *Female:*\n"
        f"   📹 {ok(s.get('female_video_id'))}\n"
        f"   💬 {ok(s.get('female_welcome_msg'))}\n"
        f"   └─ `{esc(s.get('female_welcome_msg', '(default)'))}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━"
    )


# ══════════════════════════════════════════════════════════
# /delete
# ══════════════════════════════════════════════════════════
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        gid = context.user_data.get("active_group_id")
        gn = context.user_data.get("active_group_name", "Group")
        if not gid:
            return await safe_send(context, chat.id, "⚠️ `/connect` pehle.")
    else:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ Sirf admin/owner.")
        gid, gn = chat.id, chat.title

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Male", callback_data=f"del_male_{gid}"),
         InlineKeyboardButton("🎀 Female", callback_data=f"del_female_{gid}")],
        [InlineKeyboardButton("🗑 Sab", callback_data=f"del_all_{gid}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="del_cancel")],
    ])
    await safe_send(context, chat.id, f"🗑 *{esc(gn)}* — Kya delete?", reply_markup=kb)


async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    if d == "del_cancel":
        return await q.edit_message_text("✅ Cancelled.")
    parts = d.split("_")
    act, gid = parts[1], int(parts[2])
    if act == "male":
        await delete_group_key(gid, "male_video_id")
        await delete_group_key(gid, "male_welcome_msg")
        await q.edit_message_text("✅ Male deleted!")
    elif act == "female":
        await delete_group_key(gid, "female_video_id")
        await delete_group_key(gid, "female_welcome_msg")
        await q.edit_message_text("✅ Female deleted!")
    elif act == "all":
        await delete_group_key(gid)
        await q.edit_message_text("✅ Sab deleted!")


# ══════════════════════════════════════════════════════════
# WELCOME SENDER
# ══════════════════════════════════════════════════════════
async def send_welcome(context, chat_id, user, gender, group_name):
    s = await get_group_settings(chat_id)
    vid = s.get(f"{gender}_video_id")
    msg = s.get(f"{gender}_welcome_msg", "")

    name = user.full_name or user.first_name or "Dost"
    uname = f"@{user.username}" if user.username else name

    logger.info(f"[WELCOME] group={chat_id} gender={gender} video={'YES' if vid else 'NO'} msg={'YES' if msg else 'NO'}")

    if msg:
        final = fmt(msg, name, uname, group_name)
    else:
        template = DEFAULT_MALE if gender == "male" else DEFAULT_FEMALE
        final = fmt(template, name, uname, group_name)

    if vid:
        try:
            await context.bot.send_video(
                chat_id=chat_id, video=vid,
                caption=final, parse_mode=ParseMode.MARKDOWN
            )
            return
        except TelegramError:
            logger.warning("Video Markdown fail → plain text")
            try:
                clean = final.replace("*", "").replace("_", "").replace("\\", "")
                await context.bot.send_video(
                    chat_id=chat_id, video=vid, caption=clean
                )
                return
            except TelegramError as e:
                logger.warning(f"Video send fail: {e}")

    # Text fallback
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=final,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramError:
        clean = final.replace("*", "").replace("_", "").replace("\\", "")
        await context.bot.send_message(chat_id=chat_id, text=clean)


# ══════════════════════════════════════════════════════════
# GENDER CALLBACK
# ══════════════════════════════════════════════════════════
async def gender_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    clicker = update.effective_user.id
    parts = d.split("_")
    if len(parts) < 4:
        await q.answer(); return

    gender, uid, cid = parts[1], int(parts[2]), int(parts[3])

    if clicker != uid:
        return await q.answer("❌ Sirf naye member ke liye!", show_alert=True)

    await q.answer(f"{'👦 Boy' if gender == 'male' else '👧 Girl'}!")

    try:
        user = (await context.bot.get_chat_member(cid, uid)).user
    except TelegramError:
        user = update.effective_user
    try:
        gn = (await context.bot.get_chat(cid)).title or "Group"
    except TelegramError:
        gn = "Group"
    try:
        await q.message.delete()
    except TelegramError:
        pass

    await send_welcome(context, cid, user, gender, gn)


# ══════════════════════════════════════════════════════════
# NEW MEMBER HANDLER
# ══════════════════════════════════════════════════════════
async def greet_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r = update.chat_member
    old, new = r.old_chat_member.status, r.new_chat_member.status
    if not (new in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)
            and old not in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)):
        return

    user = r.new_chat_member.user
    chat = update.effective_chat
    if user.is_bot:
        return

    gn = chat.title or "Group"
    name = user.full_name or user.first_name or "Dost"
    uname = f"@{user.username}" if user.username else name

    logger.info(f"New: {name} ({uname}) in {gn} [cid={chat.id}]")

    gender = await detect_gender(user.first_name or "", user.last_name or "")

    if gender:
        await send_welcome(context, chat.id, user, gender, gn)
    else:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("👦 Boy hoon", callback_data=f"gender_male_{user.id}_{chat.id}"),
            InlineKeyboardButton("👧 Girl hoon", callback_data=f"gender_female_{user.id}_{chat.id}"),
        ]])
        await safe_send(context, chat.id,
            f"👋 *{esc(name)}* ka swagat!\n"
            f"👤 {esc(uname)}\n\n"
            f"Batao tum kaun ho? 😊\n"
            f"_Sirf tum hi click kar sakte ho_ 👇",
            reply_markup=kb
        )


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════
def main():
    if not BOT_TOKEN:
        print("\n" + "=" * 50)
        print("  BOT_TOKEN set nahi hai!")
        print("=" * 50 + "\n")
        return

    Path(SETTINGS_FILE).write_text("{}") if not Path(SETTINGS_FILE).exists() else None

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("connect", connect_cmd))
    app.add_handler(CommandHandler("setvideo_male", setvideo_male))
    app.add_handler(CommandHandler("setvideo_female", setvideo_female))
    app.add_handler(CommandHandler("showset", showset_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CallbackQueryHandler(gender_cb, pattern=r"^gender_"))
    app.add_handler(CallbackQueryHandler(delete_cb, pattern=r"^del_"))
    app.add_handler(ChatMemberHandler(greet_member, ChatMemberHandler.CHAT_MEMBER))

    async def err_handler(update, context):
        logger.error(f"Error: {context.error}", exc_info=context.error)
    app.add_error_handler(err_handler)

    logger.info("Welcome Bot v2.1 running!")
    app.run_polling(allowed_updates=["message", "chat_member", "callback_query"])


if __name__ == "__main__":
    main()
