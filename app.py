import os
import re
import sqlite3
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- تنظیمات ---
BOT_TOKEN = "1273514608:yPIBl5Mk_UFQ4EFQv_fy3VcaxT3S-KwdfD8"
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"
DB_PATH = "lottery_bot.db"

user_states = {}

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
            status TEXT DEFAULT 'فعال',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# توابع ارتباط با بله
# ---------------------------------------------------------
def send_msg(chat_id, text, kb=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if kb: payload["reply_markup"] = kb
    return requests.post(f"{BASE_URL}/sendMessage", json=payload).json()

def send_img(chat_id, file_id, caption, kb=None):
    payload = {"chat_id": chat_id, "photo": file_id, "caption": caption, "parse_mode": "Markdown"}
    if kb: payload["reply_markup"] = kb
    return requests.post(f"{BASE_URL}/sendPhoto", json=payload).json()

# ---------------------------------------------------------
# اصلاح تشخیص لینک بله (حل مشکل تصویر ارسالی شما)
# ---------------------------------------------------------
def validate_bale_link(url):
    # این الگو اجازه می‌دهد اعداد منفی طولانی و اسلش‌های اضافی هم قبول شوند
    pattern = r'https?://ble\.ir/[^/\s]+/-?\d+(/\d+)?'
    return re.search(pattern, url.strip())

# ---------------------------------------------------------
# اصلاح منوی اصلی (نمایش تمام گزینه‌ها)
# ---------------------------------------------------------
def show_main_menu(chat_id):
    kb = {
        "inline_keyboard": [
            [{"text": "🎁 ایجاد قرعه‌کشی جدید", "callback_data": "menu_new"}],
            [{"text": "💬 قرعه‌کشی روی کامنت پست", "callback_data": "menu_comment"}],
            [{"text": "📊 لیست قرعه‌کشی‌های من", "callback_data": "menu_list"}]
        ]
    }
    send_msg(chat_id, "🌟 **به پنل مدیریت قرعه‌کشی خوش آمدید**\n\nلطفاً اقدام مورد نظر خود را انتخاب کنید:", kb)

# ---------------------------------------------------------
# هسته پردازش
# ---------------------------------------------------------
@app.route('/', methods=['POST'])
def webhook():
    update = request.get_json()
    if not update: return jsonify({"ok": True})

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

        if state == "WAIT_TITLE":
            user_states[u_id].update({"title": text, "step": "WAIT_DESC"})
            send_msg(chat_id, "📝 خوب! حالا **توضیحات یا لیست جوایز** را بنویسید:")
        
        elif state == "WAIT_DESC":
            user_states[u_id].update({"desc": text, "step": "WAIT_PHOTO"})
            kb = {"inline_keyboard": [[{"text": "⏩ بدون عکس ادامه بده", "callback_data": "skip_photo"}]]}
            send_msg(chat_id, "🖼 اگر مایلید یک **تصویر** بفرستید، در غیر این صورت روی دکمه زیر بزنید:", kb)

        elif state == "WAIT_LINK":
            if validate_bale_link(text):
                user_states[u_id].update({"link": text, "step": "WAIT_PHOTO"})
                kb = {"inline_keyboard": [[{"text": "⏩ بدون عکس ادامه بده", "callback_data": "skip_photo"}]]}
                send_msg(chat_id, "✅ لینک تایید شد.\n\n🖼 حالا اگر مایلید برای قرعه‌کشی **تصویر** بفرستید یا دکمه رد کردن را بزنید:", kb)
            else:
                send_msg(chat_id, "❌ **خطا در تایید لینک!**\n\nلینک ارسالی با ساختار بله همخوانی ندارد. لطفاً دوباره امتحان کنید.")

        elif state == "WAIT_PHOTO":
            if 'photo' in msg:
                user_states[u_id]["img"] = msg['photo'][-1]['file_id']
                finalize_preview(chat_id, u_id)
            else:
                send_msg(chat_id, "⚠️ لطفاً یا یک عکس بفرستید یا دکمه **بدون عکس** را بزنید.")

    elif 'callback_query' in update:
        cb = update['callback_query']
        chat_id = cb['message']['chat']['id']
        u_id = str(cb['from']['id'])
        data = cb['data']

        if data == "menu_new":
            user_states[u_id] = {"step": "WAIT_TITLE", "type": "عادی"}
            send_msg(chat_id, "🎁 **عنوان** قرعه‌کشی را وارد کنید:")

        elif data == "menu_comment":
            user_states[u_id] = {"step": "WAIT_LINK", "type": "روی کامنت"}
            send_msg(chat_id, "🔗 لطفاً **لینک پست** مورد نظر را بفرستید:\n(لینک را از گزینه کپی لینک در بله بردارید)")

        elif data == "skip_photo":
            if u_id in user_states:
                user_states[u_id]["img"] = None
                finalize_preview(chat_id, u_id)

        elif data == "confirm_save":
            save_to_db(u_id)
            send_msg(chat_id, "✅ با موفقیت در لیست ذخیره شد.")
            show_main_menu(chat_id)

        elif data == "menu_list":
            show_user_list(chat_id, u_id)

        elif data.startswith("del_"):
            lot_id = data.split("_")[1]
            delete_lottery(lot_id)
            send_msg(chat_id, "🗑 حذف شد.")
            show_main_menu(chat_id)

    return jsonify({"ok": True})

def finalize_preview(chat_id, u_id):
    st = user_states[u_id]
    preview = f"🧐 **تایید اطلاعات نهایی**\n\n🔹 نوع: {st['type']}\n"
    if st.get('title'): preview += f"🔹 عنوان: {st['title']}\n"
    if st.get('desc'): preview += f"🔹 توضیحات: {st['desc']}\n"
    if st.get('link'): preview += f"🔗 لینک: {st['link']}\n"
    
    kb = {"inline_keyboard": [[{"text": "🚀 ثبت نهایی", "callback_data": "confirm_save"}],
                             [{"text": "❌ شروع مجدد", "callback_data": "menu_new"}]]}
    
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
        send_msg(chat_id, "📭 لیست شما خالی است.")
        return
    kb = {"inline_keyboard": [[{"text": f"🗑 حذف: {r[1] or r[2]}", "callback_data": f"del_{r[0]}"}] for r in rows]}
    send_msg(chat_id, "📋 لیست قرعه‌کشی‌های ثبت شده:", kb)

def delete_lottery(lot_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM lotteries WHERE id = ?", (lot_id,))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

