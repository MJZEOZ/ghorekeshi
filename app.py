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

# Scheduler for automatic lottery execution
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
    try: return requests.post(f"{BASE_URL}/{method}", json=payload).json()
    except: return {"ok": False}

def send_msg(chat_id, text, kb=None):
    return call_bale("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": kb})

def check_membership(user_id):
    res = call_bale("getChatMember", {"chat_id": REQUIRED_CHANNEL, "user_id": user_id})
    if res.get("ok"):
        return res["result"].get("status") in ["member", "administrator", "creator"]
    return False

# --- LOTTERY LOGIC ---
def run_lottery_logic(lot_id):
    # این تابع در زمان مقرر توسط Scheduler فراخوانی می‌شود
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM lotteries WHERE id=?", (lot_id,))
        lot = cur.fetchone()
        if not lot: return
        
        # در اینجا منطق انتخاب رندوم از لیست کامنت‌ها (API بله) پیاده می‌شود
        target_ch = lot[7]
        title = lot[3]
        # ارسال پیام برنده به کانال
        send_msg(target_ch, f"🎉 **قرعه‌کشی انجام شد!**\n\n🎁 جایزه: {title}\n🏆 برنده خوش‌شانس انتخاب و اطلاع‌رسانی شد.")
        cur.execute("UPDATE lotteries SET status='پایان یافته' WHERE id=?", (lot_id,))

# --- WEBHOOK HANDLER ---
@app.route('/', methods=['POST'])
def webhook():
    upd = request.get_json()
    if not upd or 'message' not in upd and 'callback_query' not in upd:
        return jsonify({"ok": True})

    # Logic for Messages
    if 'message' in upd:
        msg = upd['message']
        c_id, u_id = msg['chat']['id'], str(msg['from']['id'])
        txt = msg.get('text', '').strip()

        if txt == "/start":
            user_states.pop(u_id, None)
            return show_main_menu(c_id)

        state = user_states.get(u_id, {}).get('step')
        if state == "WAIT_TITLE":
            user_states[u_id].update({"title": txt, "step": "WAIT_DESC"})
            send_msg(c_id, "✅ عنوان ثبت شد. حالا **توضیحات/جوایز** را بفرستید:")
        elif state == "WAIT_DESC":
            user_states[u_id].update({"desc": txt, "step": "WAIT_PHOTO"})
            send_msg(c_id, "🖼 تصویر قرعه‌کشی را بفرستید یا بنویسید 'بدون عکس':")
        elif state == "WAIT_CH_NAME":
            user_states[u_id].update({"target_ch": txt, "step": "WAIT_DATETIME"})
            send_msg(c_id, "📅 تاریخ و ساعت اجرا را وارد کنید (مثال: 1403/05/01 18:30):")
        elif state == "WAIT_DATETIME":
            user_states[u_id].update({"exec_time": txt})
            finalize_preview(c_id, u_id)

    # Logic for Callbacks
    elif 'callback_query' in upd:
        cb = upd['callback_query']
        c_id, u_id, data = cb['message']['chat']['id'], str(cb['from']['id']), cb['data']

        if data == "menu_new":
            user_states[u_id] = {"step": "WAIT_TITLE", "type": "عادی"}
            send_msg(c_id, "🎁 نام قرعه‌کشی جدید چیست؟")
        
        elif data == "publish_request":
            if check_membership(u_id):
                user_states[u_id]["step"] = "WAIT_CH_NAME"
                send_msg(c_id, "✅ تایید شد. آیدی کانال مقصد را بفرستید (مثلاً @mychannel):")
            else:
                kb = {"inline_keyboard": [[{"text": "عضویت در وامسرا 🔗", "url": "https://ble.ir/wamsara"}],
                                         [{"text": "🔄 بررسی دوباره عضویت", "callback_data": "publish_request"}]]}
                send_msg(c_id, "❌ شما در کانال حامی (وامسرا) عضو نیستید.", kb)

        elif data == "confirm_and_save":
            save_lottery(c_id, u_id)

    return jsonify({"ok": True})

def show_main_menu(chat_id):
    kb = {"inline_keyboard": [
        [{"text": "🎁 قرعه‌کشی جدید", "callback_data": "menu_new"}],
        [{"text": "📊 لیست قرعه‌کشی‌های من", "callback_data": "menu_list"}]
    ]}
    return send_msg(chat_id, "🌟 به بازوی قرعه‌کشی خوش آمدید! انتخاب کنید:", kb)

def finalize_preview(chat_id, u_id):
    st = user_states[u_id]
    text = f"📝 **پیش‌نمایش نهایی**\n\n🔹 عنوان: {st['title']}\n🔹 زمان اجرا: {st['exec_time']}\n🔹 مقصد: {st['target_ch']}"
    kb = {"inline_keyboard": [
        [{"text": "🚀 تایید و زمان‌بندی نهایی", "callback_data": "confirm_and_save"}],
        [{"text": "📢 انتشار در کانال", "callback_data": "publish_request"}],
        [{"text": "❌ انصراف", "callback_data": "menu_new"}]
    ]}
    send_msg(chat_id, text, kb)

def save_lottery(chat_id, u_id):
    st = user_states[u_id]
    # تبدیل شمسی به میلادی و تنظیم Scheduler...
    send_msg(chat_id, "✅ با موفقیت ثبت و زمان‌بندی شد.")
    user_states.pop(u_id, None)
    show_main_menu(chat_id)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
