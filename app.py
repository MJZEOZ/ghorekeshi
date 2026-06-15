import os
import re
import sqlite3
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- تنظیمات توکن (توکن خود را اینجا بگذارید) ---
BOT_TOKEN = "1273514608:yPIBl5Mk_UFQ4EFQv_fy3VcaxT3S-KwdfD8"
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"
DB_PATH = "lottery_bot.db"

# --- مدیریت حافظه موقت وضعیت کاربران ---
user_states = {}

# ---------------------------------------------------------
# بخش دیتابیس (SQLite)
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lotteries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            type TEXT,
            title TEXT,
            description TEXT,
            link TEXT,
            image_id TEXT,
            status TEXT DEFAULT 'در جریان',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# متدهای ارتباطی با بله
# ---------------------------------------------------------
def call_bale(method, payload):
    return requests.post(f"{BASE_URL}/{method}", json=payload).json()

def send_msg(chat_id, text, kb=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if kb: payload["reply_markup"] = kb
    return call_bale("sendMessage", payload)

def send_img(chat_id, file_id, caption, kb=None):
    payload = {"chat_id": chat_id, "photo": file_id, "caption": caption, "parse_mode": "Markdown"}
    if kb: payload["reply_markup"] = kb
    return call_bale("sendPhoto", payload)

# ---------------------------------------------------------
# منطق تشخیص لینک بله
# ---------------------------------------------------------
def validate_bale_link(url):
    # این Regex لینک‌های پیچیده بله با اعداد منفی را هم شناسایی می‌کند
    pattern = r'https?://ble\.ir/([^/]+)/(-?\d+)(?:/(\d+))?/?'
    return re.search(pattern, url)

# ---------------------------------------------------------
# منوها و پیام‌ها
# ---------------------------------------------------------
def show_main_menu(chat_id):
    kb = {
        "inline_keyboard": [
            [{"text": "🎁 قرعه‌کشی جدید", "callback_data": "menu_new"}],
            [{"text": "💬 قرعه‌کشی روی کامنت پست", "callback_data": "menu_comment"}],
            [{"text": "📊 قرعه‌کشی‌های من", "callback_data": "menu_list"}]
        ]
    }
    send_msg(chat_id, "👋 **خوش آمدید!**\n\nلطفاً یکی از گزینه‌های زیر را برای مدیریت قرعه‌کشی انتخاب کنید:", kb)

def ask_photo(chat_id, u_id):
    kb = {"inline_keyboard": [[{"text": "⏩ بدون عکس ادامه بده", "callback_data": "skip_photo"}]]}
    send_msg(chat_id, "🖼 (اختیاری) اگر مایل هستید یک **تصویر** بفرستید.\nدر غیر این صورت دکمه مرحله بعد را بزنید:", kb)

# ---------------------------------------------------------
# هسته اصلی پردازش Webhook
# ---------------------------------------------------------
@app.route('/', methods=['POST'])
def webhook():
    update = request.get_json()
    if not update: return jsonify({"ok": True})

    # --- پردازش پیام‌های متنی و فایل ---
    if 'message' in update:
        msg = update['message']
        chat_id = msg['chat']['id']
        u_id = str(msg['from']['id'])
        text = msg.get('text', '').strip()

        if text == "/start":
            user_states.pop(u_id, None)
            show_main_menu(chat_id)
            return jsonify({"ok": True})

        state = user_states.get(u_id, {}).get('step')

        # الف) فرآیند قرعه‌کشی عادی
        if state == "WAIT_TITLE":
            user_states[u_id].update({"title": text, "step": "WAIT_DESC"})
            send_msg(chat_id, "📝 حالا **توضیحات** یا جوایز قرعه‌کشی را بنویسید:")
        
        elif state == "WAIT_DESC":
            user_states[u_id].update({"desc": text, "step": "WAIT_PHOTO"})
            ask_photo(chat_id, u_id)

        # ب) فرآیند قرعه‌کشی روی کامنت
        elif state == "WAIT_LINK":
            if validate_bale_link(text):
                user_states[u_id].update({"link": text, "step": "WAIT_PHOTO"})
                send_msg(chat_id, "✅ لینک تایید شد.")
                ask_photo(chat_id, u_id)
            else:
                send_msg(chat_id, "❌ **خطا!** لینک ارسالی معتبر نیست.\nلطفاً لینک پست را به درستی کپی کرده و ارسال کنید.")

        # ج) دریافت عکس (مشترک برای هر دو نوع)
        elif state == "WAIT_PHOTO":
            if 'photo' in msg:
                user_states[u_id]["img"] = msg['photo'][-1]['file_id']
                send_msg(chat_id, "✅ تصویر دریافت شد.")
            else:
                user_states[u_id]["img"] = None
            
            # نمایش پیش‌نمایش نهایی
            finalize_preview(chat_id, u_id)

    # --- پردازش کلیک روی دکمه‌ها ---
    elif 'callback_query' in update:
        cb = update['callback_query']
        chat_id = cb['message']['chat']['id']
        u_id = str(cb['from']['id'])
        data = cb['data']

        if data == "menu_new":
            user_states[u_id] = {"step": "WAIT_TITLE", "type": "عادی"}
            send_msg(chat_id, "🎁 لطفاً **عنوان** قرعه‌کشی را وارد کنید:")

        elif data == "menu_comment":
            user_states[u_id] = {"step": "WAIT_LINK", "type": "روی کامنت"}
            send_msg(chat_id, "🔗 لطفاً **لینک پست** مورد نظر در کانال بله را ارسال کنید:")

        elif data == "skip_photo":
            if u_id in user_states:
                user_states[u_id]["img"] = None
                finalize_preview(chat_id, u_id)

        elif data == "confirm_save":
            save_to_db(u_id)
            send_msg(chat_id, "🎉 قرعه‌کشی شما با موفقیت ثبت شد و در لیست «قرعه‌کشی‌های من» قرار گرفت.")
            show_main_menu(chat_id)

        elif data == "menu_list":
            show_user_list(chat_id, u_id)

        elif data.startswith("del_"):
            lot_id = data.split("_")[1]
            delete_lottery(lot_id)
            send_msg(chat_id, "🗑 قرعه‌کشی حذف شد.")
            show_main_menu(chat_id)

    return jsonify({"ok": True})

# ---------------------------------------------------------
# توابع کمکی نهایی‌سازی
# ---------------------------------------------------------
def finalize_preview(chat_id, u_id):
    st = user_states[u_id]
    st["step"] = "FINISHED"
    
    preview = f"📋 **پیش‌نمایش نهایی**\n\n"
    preview += f"🔹 نوع: {st['type']}\n"
    if st.get('title'): preview += f"🔹 عنوان: {st['title']}\n"
    if st.get('desc'): preview += f"🔹 توضیحات: {st['desc']}\n"
    if st.get('link'): preview += f"🔗 لینک پست: {st['link']}\n"
    
    kb = {"inline_keyboard": [[{"text": "🚀 تایید و ثبت نهایی", "callback_data": "confirm_save"}],
                             [{"text": "❌ انصراف", "callback_data": "menu_new"}]]}
    
    if st.get('img'):
        send_img(chat_id, st['img'], preview, kb)
    else:
        send_msg(chat_id, preview, kb)

def save_to_db(u_id):
    st = user_states[u_id]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO lotteries (user_id, type, title, description, link, image_id) VALUES (?,?,?,?,?,?)",
                (u_id, st['type'], st.get('title'), st.get('desc'), st.get('link'), st.get('img')))
    conn.commit()
    conn.close()
    user_states.pop(u_id, None)

def show_user_list(chat_id, u_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, title, type FROM lotteries WHERE user_id = ?", (u_id,))
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        send_msg(chat_id, "📭 شما هنوز قرعه‌کشی‌ای ثبت نکرده‌اید.")
        return

    kb = {"inline_keyboard": []}
    for r in rows:
        label = f"{r[1] or 'بدون عنوان'} ({r[2]})"
        kb["inline_keyboard"].append([{"text": f"🗑 حذف {label}", "callback_data": f"del_{r[0]}"}])
    
    send_msg(chat_id, "📊 لیست قرعه‌کشی‌های شما:\n(برای حذف روی دکمه‌ها کلیک کنید)", kb)

def delete_lottery(lot_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM lotteries WHERE id = ?", (lot_id,))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
