import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from datetime import datetime, timedelta
from flask import Flask
import threading
import os

# إعدادات البيئة
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_ID = os.getenv("ADMIN_ID")

# تحقق من الإعدادات
if not all([BOT_TOKEN, MONGO_URI, ADMIN_ID]):
    raise ValueError("❌ تأكد من ضبط متغيرات البيئة: BOT_TOKEN, MONGO_URI, ADMIN_ID")

ADMIN_ID = int(ADMIN_ID)
bot = telebot.TeleBot(BOT_TOKEN)
client = MongoClient(MONGO_URI)
db = client["telegram_bot_db_2"]
users = db["users"]

# القنوات المطلوبة بصيغة @username
REQUIRED_CHANNELS = [
    "@R2M199",
    "@Nedfd_Root",
    "@SNOKER_VIP",
]
CHANNEL_EMOJIS = ["📫", "👾", "📚"]
REWARDS = {
    "1": {"name": "🎁 كود شحن", "cost": 10},
    "2": {"name": "🎫 بطاقة هدية", "cost": 25},
}

FUNDING_TIERS = {
    "5": {"followers": 5, "cost": 10},
    "10": {"followers": 10, "cost": 18},
    "20": {"followers": 20, "cost": 35},
}

def show_funding_options(user_id):
    text = "💰 اختر باقة التمويل:\n"
    markup = InlineKeyboardMarkup()
    for key, option in FUNDING_TIERS.items():
        text += f"{option['followers']} متابع = {option['cost']} نقطة\n"
        markup.add(InlineKeyboardButton(f"{option['followers']} متابع", callback_data=f"buy_followers_{key}"))
    bot.send_message(user_id, text, reply_markup=markup)
# Flask لإبقاء البوت حي
app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running!', 200

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def run_bot():
    bot.infinity_polling()

# دالة إنشاء المستخدم
def get_or_create_user(user_id, ref=None):
    user = users.find_one({"_id": user_id})
    if not user:
        users.insert_one({
            "_id": user_id,
            "points": 0,
            "referrals": 0,
            "invited_by": ref,
            "last_daily": None,
            "current_check_index": 0
        })
        if ref and ref != user_id:
            users.update_one({"_id": ref}, {"$inc": {"points": 1, "referrals": 1}})
        user = users.find_one({"_id": user_id})
    return user

# التحقق من الاشتراك
def check_channel_membership(user_id, channel):
    try:
        status = bot.get_chat_member(channel, user_id).status
        return status in ["member", "creator", "administrator"]
    except:
        return False

# رسالة القنوات
def send_channel_message(user_id, index):
    channel = REQUIRED_CHANNELS[index]
    emoji = CHANNEL_EMOJIS[index]
    text = (
        f"لطفاً اشترك في القناة التالية ثم اضغط /start مرة أخرى:\n\n"
        f"{emoji} : https://t.me/{channel.lstrip('@')}"
    )
    bot.send_message(user_id, text)

# دالة بدء الاستخدام
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    args = msg.text.split()
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    user = get_or_create_user(user_id, ref)

    # ✅ تصحيح المؤشر إذا خرج عن الحد
    if user.get("current_check_index", 0) > len(REQUIRED_CHANNELS):
        users.update_one({"_id": user_id}, {"$set": {"current_check_index": 0}})
        user["current_check_index"] = 0

    index = user.get("current_check_index", 0)

    if index < len(REQUIRED_CHANNELS):
        channel = REQUIRED_CHANNELS[index]
        if not check_channel_membership(user_id, channel):
            send_channel_message(user_id, index)
            return
        users.update_one({"_id": user_id}, {"$set": {"current_check_index": index + 1}})
        start(msg)  # لا بأس بالتكرار مرة واحدة فقط بعد تحديث القناة
        return

    # القائمة الرئيسية ...

    # القائمة الرئيسية
    invite_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    text = f"👋 أهلاً بك {msg.from_user.first_name}!\n\n"
    text += f"🎯 نقاطك: {user['points']}\n👥 عدد الإحالات: {user['referrals']}\n\n"
    text += f"🔗 رابط دعوتك: {invite_link}\n\nاختر من القائمة:"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📊 رصيدي", callback_data="mypoints"))
    markup.add(InlineKeyboardButton("🎁 استبدال نقاط", callback_data="rewards"))
    markup.add(InlineKeyboardButton("🕓 نقاطي اليومية", callback_data="daily_points"))
    markup.add(InlineKeyboardButton("🚀 تمويل قناتي", callback_data="fund_channel"))

    bot.send_message(user_id, text, reply_markup=markup)

# عرض القنوات المطلوبة
@bot.message_handler(commands=['channels'])
def show_channels(msg):
    text = "📢 القنوات التي يجب الاشتراك بها:\n\n"
    for emoji, ch in zip(CHANNEL_EMOJIS, REQUIRED_CHANNELS):
        text += f"{emoji} https://t.me/{ch.lstrip('@')}\n"
    bot.send_message(msg.chat.id, text)

# الأزرار التفاعلية
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data
    user = get_or_create_user(user_id)

    if data == "mypoints":
        text = f"🎯 نقاطك: {user['points']}\n👥 عدد الإحالات: {user['referrals']}"
        bot.send_message(user_id, text)

    elif data == "rewards":
        text = "🎁 الجوائز المتاحة:\n"
        markup = InlineKeyboardMarkup()
        for key, reward in REWARDS.items():
            text += f"{key}- {reward['name']} - {reward['cost']} نقطة\n"
            markup.add(InlineKeyboardButton(f"استبدل {reward['name']}", callback_data=f"redeem_{key}"))
        bot.send_message(user_id, text, reply_markup=markup)

    elif data.startswith("redeem_"):
        reward_id = data.split("_")[1]
        reward = REWARDS.get(reward_id)
        if reward:
            if user['points'] >= reward['cost']:
                users.update_one({"_id": user_id}, {"$inc": {"points": -reward['cost']}})
                bot.send_message(user_id, f"✅ تم استبدال {reward['name']}! سيتم التواصل معك قريبًا.")
                bot.send_message(ADMIN_ID, f"📥 المستخدم @{call.from_user.username or 'بدون_اسم'} (ID: {user_id}) استبدل {reward['name']}")
            else:
                bot.send_message(user_id, "❌ لا تملك نقاط كافية!")

    elif data == "daily_points":
        now = datetime.utcnow()
        last_claim = user.get("last_daily")
        if not last_claim or now - last_claim >= timedelta(hours=24):
            users.update_one({"_id": user_id}, {"$inc": {"points": 1}, "$set": {"last_daily": now}})
            bot.send_message(user_id, "✅ تم منحك 1 نقطة يومية!")
        else:
            remaining = timedelta(hours=24) - (now - last_claim)
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            bot.send_message(user_id, f"⏳ يمكنك الحصول على نقاطك اليومية بعد {hours} ساعة و {minutes} دقيقة.")

    elif data == "fund_channel":
        bot.send_message(user_id, "📢 أرسل رابط قناتك (يجب أن يكون البوت مشرفًا فيها).")
        bot.register_next_step_handler(call.message, handle_channel_link)

    elif data.startswith("buy_followers_"):
        tier_key = data.split("_")[-1]
        tier = FUNDING_TIERS.get(tier_key)
        if tier:
            if user['points'] >= tier['cost']:
                users.update_one({"_id": user_id}, {"$inc": {"points": -tier['cost']}})
                channel = user.get("fund_channel", "❓ لم يتم تحديد قناة")
                bot.send_message(user_id, "✅ تم إرسال طلبك وسيتم تنفيذ التمويل قريبًا.")
                bot.send_message(ADMIN_ID, (
                    f"📢 طلب تمويل جديد:\n"
                    f"👤 المستخدم: @{call.from_user.username or 'بدون_اسم'} (ID: {user_id})\n"
                    f"📣 القناة: {channel}\n"
                    f"📌 المتابعين المطلوبين: {tier['followers']}\n"
                    f"🎯 النقاط المخصومة: {tier['cost']}"
                ))
            else:
                bot.send_message(user_id, "❌ لا تملك نقاط كافية لهذه الباقة.")
###هنا ارسل رابط قناتك 
def handle_channel_link(msg):
    user_id = msg.from_user.id
    link = msg.text.strip()

    if not link.startswith("https://t.me/"):
        bot.send_message(user_id, "❌ رابط غير صحيح. تأكد أن الرابط يبدأ بـ https://t.me/")
        return

    channel_username = link.replace("https://t.me/", "@")

    try:
        member = bot.get_chat_member(channel_username, bot.get_me().id)
        if member.status not in ["administrator", "creator"]:
            bot.send_message(user_id, "❌ يجب أن يكون البوت مشرفًا في القناة أولاً.")
            return
    except Exception as e:
        bot.send_message(user_id, "❌ حدث خطأ. تأكد أن الرابط صحيح وأن البوت في القناة.")
        return

    # حفظ القناة مؤقتًا في قاعدة البيانات
    users.update_one({"_id": user_id}, {"$set": {"fund_channel": channel_username}})

    # عرض باقات التمويل
    show_funding_options(user_id)
# أمر شحن النقاط من قبل المالك
@bot.message_handler(commands=['addpoints'])
def add_points(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split()
    if len(parts) != 3:
        bot.reply_to(msg, "❌ الصيغة: /addpoints <user_id> <amount>")
        return
    try:
        user_id = int(parts[1])
        amount = int(parts[2])
        users.update_one({"_id": user_id}, {"$inc": {"points": amount}})
        bot.send_message(user_id, f"✅ تم إضافة {amount} نقطة إلى حسابك!")
        bot.reply_to(msg, "✅ تم الشحن.")
    except:
        bot.reply_to(msg, "❌ حدث خطأ، تأكد من المعرف والقيمة.")

# تشغيل Flask والبوت
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    threading.Thread(target=run_bot).start()
    threading.Event().wait()
