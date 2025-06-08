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
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = telebot.TeleBot(BOT_TOKEN)
client = MongoClient(MONGO_URI)
db = client["telegram_bot_db_2"]
users = db["users"]

# قائمة القنوات التي يجب الاشتراك بها بالترتيب
REQUIRED_CHANNELS = [
    "https://t.me/R2M199",
    "https://t.me/Nedfd_Root",
    "https://t.me/SNOKER_VIP",
]
CHANNEL_EMOJIS = ["📫", "👾", "📚"]
REWARDS = {
    "1": {"name": "🎁 كود شحن", "cost": 10},
    "2": {"name": "🎫 بطاقة هدية", "cost": 25},
}

# Flask لإبقاء البوت حيًا
app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running!', 200

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def run_bot():
    bot.infinity_polling()

# دالة لإنشاء أو جلب المستخدم مع تخزين حالة التحقق من القنوات
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

# تحقق الاشتراك في قناة
def check_channel_membership(user_id, channel):
    try:
        chat = bot.get_chat(channel)
        status = bot.get_chat_member(chat.id, user_id).status
        return status in ["member", "creator", "administrator"]
    except:
        return False

@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    args = msg.text.split()
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    user = get_or_create_user(user_id, ref)

    current_check_index = user.get("current_check_index", 0)

    if current_check_index >= len(REQUIRED_CHANNELS):
        invite_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
        text = (
            f"👋 أهلاً بك {msg.from_user.first_name}!\n\n"
            f"🎯 نقاطك: {user['points']}\n"
            f"👥 عدد الإحالات: {user['referrals']}\n\n"
            f"🔗 رابط دعوتك: {invite_link}\n\nاختر من القائمة:"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📊 رصيدي", callback_data="mypoints"))
        markup.add(InlineKeyboardButton("🎁 استبدال نقاط", callback_data="rewards"))
        markup.add(InlineKeyboardButton("🕓 نقاطي اليومية", callback_data="daily_points"))
        bot.send_message(user_id, text, reply_markup=markup)
        return

    channel_to_check = REQUIRED_CHANNELS[current_check_index]
    emoji = CHANNEL_EMOJIS[current_check_index]

    if not check_channel_membership(user_id, channel_to_check):
        text = (
            f"لطفاً اشترك بالقناة التالية ثم اضغط /start مرة أخرى:\n\n"
            f"{emoji} {channel_to_check}"
        )
        bot.send_message(user_id, text)
        return

    users.update_one({"_id": user_id}, {"$set": {"current_check_index": current_check_index + 1}})
    start(msg)

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
                bot.send_message(ADMIN_ID, f"📥 مستخدم {user_id} استبدل {reward['name']}")
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

@bot.message_handler(commands=['addpoints'])
def add_points(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split()
    if len(parts) != 3:
        bot.reply_to(msg, "❌ الصيغة: /addpoints <user_id> <amount>")
        return
    user_id = int(parts[1])
    amount = int(parts[2])
    users.update_one({"_id": user_id}, {"$inc": {"points": amount}})
    bot.send_message(user_id, f"✅ تم إضافة {amount} نقطة إلى حسابك!")
    bot.reply_to(msg, "✅ تم الشحن.")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    threading.Thread(target=run_bot).start()
    threading.Event().wait()
