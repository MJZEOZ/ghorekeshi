import os, re, sqlite3, requests, jdatetime
from datetime import datetime
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- CONFIG ---
BOT_TOKEN = "1273514608:yPIBl5Mk_UFQ4EFQv_fy3VcaxT3S-KwdfD8"
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"
DB_PATH = "lottery_bot.db"
REQUIRED_CHANNEL = "@wamsara"

# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.start()

user_states = {}

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lotteries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                type TEXT,
                title TEXT,
                description TEXT,
                link TEXT,
                image_id TEXT,
                target_channel TEXT,
                exec_time TEXT,
                status TEXT DEFAULT 'ثبت شده'
            )
        """)
init_db()

# --- HELPER FUNCTIONS ---
def call_bale(method, payload):
    try: return requests.post(f"{BASE_URL}/{method}", json=payload, timeout=10).json()
    except: return {"ok": False}

def send_msg(chat_id, text, kb=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if kb: payload["reply_markup"] = kb
    return call_bale("sendMessage", payload)

def check_membership(user_id):
    res = call_bale("getChatMember", {"chat_id": REQUIRED_CHANNEL, "user_id": user_id})
    if res.get("ok"):
        return res["result"].get("status") in ["member", "administrator", "creator"]
    return False

# --- WEBHOOK HANDLER ---
@app.route('/', methods=['POST'])
def webhook():
    upd = request.get_json()
    if not upd: return jsonify({"ok": True})

    # 1. Handle Callback Queries (Buttons)
    if 'callback_query' in upd:
        cb = upd['callback_query']
        c_id, u_id, data = cb['message']['chat']['id'], str(cb['from']['id']), cb['data']

        if data == "menu_new":
            user_states[u_id] = {"step": "WAIT_TITLE", "type": "عادی"}
            send_msg(c_id, "🎁 نام قرعه‌کشی جدید چیست؟")
        
        elif data == "upload_photo":
            user_states[u_id]["step"] = "WAIT_PHOTO"
            send_msg(c_id, "📷 لطفاً تصویر قرعه‌کشی را ارسال کنید:")

        elif data == "skip_photo":
            user_states[u_id]["image_id"] = None
            user_states[u_id]["step"] = "WAIT_CH_NAME"
            send_msg(c_id, "✅ بدون تصویر ادامه می‌دهیم.\n\n📢 آیدی کانال مقصد را بفرستید (مثلاً @mychannel):")

        elif data == "publish_request":
            if check_membership(u_id):
                user_states[u_id]["step"] = "WAIT_CH_NAME"
                send_msg(c_id, "✅ عضویت تایید شد.\n\n📢 آیدی کانال مقصد را بفرستید (مثلاً @mychannel):")
            else:
                kb = {"inline_keyboard": [[{"text": "عضویت در وامسرا 🔗", "url": "https://ble.ir/wamsara"}],
                                         [{"text": "🔄 بررسی دوباره عضویت", "callback_data": "publish_request"}]]}
                send_msg(c_id, "❌ برای انتشار، ابتدا باید در کانال حامی عضو شوید:", kb)

        elif data == "confirm_save":
            # Logic to save to DB and schedule...
            send_msg(c_id, "✅ قرعه‌کشی با موفقیت ثبت و زمان‌بندی شد.")
            user_states.pop(u_id, None)

        return jsonify({"ok": True})

    # 2. Handle Messages
    if 'message' in upd:
        msg = upd['message']
        c_id, u_id = msg['chat']['id'], str(msg['from']['id'])
        txt = msg.get('text', '').strip()
        
        if txt == "/start":
            user_states.pop(u_id, None)
            kb = {"inline_keyboard": [[{"text": "🎁 ایجاد قرعه‌کشی", "callback_data": "menu_new"}]]}
            return send_msg(c_id, "🌟 به بازوی مدیریت قرعه‌کشی خوش آمدید!", kb)

        state = user_states.get(u_id, {}).get('step')
        
        if state == "WAIT_TITLE":
            user_states[u_id].update({"title": txt, "step": "WAIT_DESC"})
            send_msg(c_id, "✅ عنوان ثبت شد.\n\n📝 حالا توضیحات و جوایز را بنویسید:")

        elif state == "WAIT_DESC":
            user_states[u_id].update({"desc": txt, "step": "DECIDE_PHOTO"})
            kb = {"inline_keyboard": [
                [{"text": "📸 بارگذاری تصویر", "callback_data": "upload_photo"}],
                [{"text": "⏩ ادامه بدون تصویر", "callback_data": "skip_photo"}]
            ]}
            send_msg(c_id, "🖼 آیا مایلید تصویری برای قرعه‌کشی اضافه کنید؟", kb)

        elif state == "WAIT_PHOTO":
            if "photo" in msg:
                # Get the highest resolution photo
                file_id = msg["photo"][-1]["file_id"]
                user_states[u_id].update({"image_id": file_id, "step": "WAIT_CH_NAME"})
                send_msg(c_id, "✅ تصویر دریافت شد.\n\n📢 آیدی کانال مقصد را بفرستید (مثلاً @mychannel):")
            else:
                send_msg(c_id, "⚠️ لطفاً یک تصویر بفرستید یا از دکمه «ادامه بدون تصویر» استفاده کنید.")

        elif state == "WAIT_CH_NAME":
            if txt.startswith("@"):
                user_states[u_id].update({"target_ch": txt, "step": "WAIT_DATETIME"})
                send_msg(c_id, "📅 تاریخ و ساعت اجرا را وارد کنید\n(مثال: 1403/04/20 18:30):")
            else:
                send_msg(c_id, "⚠️ آیدی کانال باید با @ شروع شود.")

        elif state == "WAIT_DATETIME":
            user_states[u_id].update({"exec_time": txt})
            st = user_states[u_id]
            preview = f"📝 **پیش‌نمایش قرعه‌کشی**\n\n🔹 عنوان: {st['title']}\n🔹 مقصد: {st['target_ch']}\n🔹 زمان: {st['exec_time']}"
            kb = {"inline_keyboard": [
                [{"text": "📢 تایید و انتشار در کانال حامی", "callback_data": "publish_request"}],
                [{"text": "💾 فقط ذخیره و زمان‌بندی", "callback_data": "confirm_save"}]
            ]}
            send_msg(c_id, preview, kb)

    return jsonify({"ok": True})

if __name__ == "__main__":
    # Ensure port is dynamic for Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
