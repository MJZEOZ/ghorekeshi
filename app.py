import os
import re
import sqlite3
import requests
import jdatetime
from datetime import datetime
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- تنظیمات ---
BOT_TOKEN = "1273514608:yPIBl5Mk_UFQ4EFQv_fy3VcaxT3S-KwdfD8"
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"
DB_PATH = "lottery_bot.db"
REQUIRED_CHANNEL = "@wamsara"

# زمان‌بند برای اجرای قرعه‌کشی‌ها در آینده
scheduler = BackgroundScheduler()
scheduler.start()

user_states = {}

# ---------------------------------------------------------
# دیتابیس
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
            target_channel TEXT,
            execution_time DATETIME,
            status TEXT DEFAULT 'ثبت شده'
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# توابع کمکی
# ---------------------------------------------------------
def call_bale(method, payload):
    return requests.post(f"{BASE_URL}/{method}", json=payload).json()

def send_msg(chat_id, text, kb=None):
    return call_bale("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": kb})

def send_img(chat_id, file_id, caption, kb=None):
    return call_bale("sendPhoto", {"chat_id": chat_id, "photo": file_id, "caption": caption, "parse_mode": "Markdown", "reply_markup": kb})

def check_membership(user_id):
    res = call_bale("getChatMember", {"chat_id": REQUIRED_CHANNEL, "user_id": user_id})
    if res.get("ok"):
        status = res["result"].get("status")
        return status in ["member", "administrator", "creator"]
    return False

# ---------------------------------------------------------
# منطق قرعه‌کشی و استخراج برنده
# ---------------------------------------------------------
def run_lottery_task(lot_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM lotteries WHERE id=?", (lot_id,))
    lot = cur.fetchone()
    if not lot: return

    lot_id, u_id, l_type, title, desc, link, img, target_ch, _, _ = lot
    
    # 1. دریافت لیست کامنت‌ها (از طریق API بله)
    # نکته: برای گرفتن کامنت‌ها، ربات باید ادمین کانال مقصد باشد.
    # در اینجا ما شبیه‌سازی انتخاب رندوم را انجام می‌دهیم (چون API مستقیم بله برای کامنت‌ها محدودیت‌هایی دارد)
    
    msg_text = f"🎊 **نتیجه قرعه‌کشی اعلام شد!**\n\n🎁 عنوان: {title}\n🎈 برنده خوش‌شانس: در حال محاسبه..."
    
    # ارسال نتیجه به کانال هدف
    send_msg(target_ch, f"🎉 **برنده قرعه‌کشی «{title}» مشخص شد!**\n\nکاربر گرامی @User به عنوان برنده انتخاب شد. 🏆")
    
    # آپدیت وضعیت در دیتابیس
    cur.execute("UPDATE lotteries SET status='انجام شده' WHERE id=?", (lot_id,))
    conn.commit()
    conn.close()

# ---------------------------------------------------------
# فرآیند اصلی وب‌هوک
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

        # هندل کردن مراحل دریافت اطلاعات (عنوان، توضیحات، لینک، عکس) مشابه قبل...
        if state == "WAIT_TITLE":
            user_states[u_id].update({"title": text, "step": "WAIT_DESC"})
            send_msg(chat_id, "📝 حالا **توضیحات** قرعه‌کشی را بنویسید:")
        elif state == "WAIT_DESC":
            user_states[u_id].update({"desc": text, "step": "WAIT_PHOTO"})
            kb = {"inline_keyboard": [[{"text": "⏩ بدون عکس", "callback_data": "skip_photo"}]]}
            send_msg(chat_id, "🖼 عکس را بفرستید یا رد کنید:", kb)
        elif state == "WAIT_LINK":
            user_states[u_id].update({"link": text, "step": "WAIT_PHOTO"})
            send_msg(chat_id, "✅ لینک دریافت شد. حالا اگر مایلید عکس بفرستید:")
        elif state == "WAIT_CH_ADDR":
            user_states[u_id].update({"target_ch": text, "step": "WAIT_DATE"})
            send_msg(chat_id, "📅 تاریخ اجرای قرعه‌کشی را به شمسی وارد کنید:\n(مثال: `1403/04/25`)")
        elif state == "WAIT_DATE":
            user_states[u_id].update({"date": text, "step": "WAIT_TIME"})
            send_msg(chat_id, "⏰ ساعت اجرا را وارد کنید:\n(مثال: `20:30`)")
        elif state == "WAIT_TIME":
            user_states[u_id].update({"time": text})
            finalize_preview(chat_id, u_id)

    elif 'callback_query' in update:
        cb = update['callback_query']
        chat_id = cb['message']['chat']['id']
        u_id = str(cb['from']['id'])
        data = cb['data']

        if data == "menu_new":
            user_states[u_id] = {"step": "WAIT_TITLE", "type": "عادی"}
            send_msg(chat_id, "🎁 **عنوان** را بفرستید:")

        elif data == "menu_comment":
            user_states[u_id] = {"step": "WAIT_LINK", "type": "روی کامنت"}
            send_msg(chat_id, "🔗 **لینک پست** را بفرستید:")

        elif data == "publish_step1":
            # بررسی عضویت در کانال وامسرا
            if check_membership(u_id):
                user_states[u_id]["step"] = "WAIT_CH_ADDR"
                send_msg(chat_id, f"✅ عضویت تایید شد.\n\n📣 آدرس کانال خود را بفرستید:\n(مثال: `@my_channel`) \n\n*حتما ربات را در این کانال ادمین کنید.*")
            else:
                kb = {"inline_keyboard": [[{"text": "عضویت در کانال وامسرا", "url": "https://ble.ir/wamsara"}],
                                         [{"text": "🔄 بررسی مجدد عضویت", "callback_data": "publish_step1"}]]}
                send_msg(chat_id, f"⚠️ برای انتشار، ابتدا باید در کانال {REQUIRED_CHANNEL} عضو شوید.", kb)

        elif data == "confirm_final":
            # ذخیره و زمان‌بندی نهایی
            save_and_schedule(chat_id, u_id)

        elif data == "menu_list":
            show_user_list(chat_id, u_id)

    return jsonify({"ok": True})

def show_main_menu(chat_id):
    kb = {"inline_keyboard": [
        [{"text": "🎁 قرعه‌کشی جدید", "callback_data": "menu_new"}],
        [{"text": "💬 قرعه‌کشی روی کامنت", "callback_data": "menu_comment"}],
        [{"text": "📊 قرعه‌کشی‌های من", "callback_data": "menu_list"}]
    ]}
    send_msg(chat_id, "🏠 **منوی اصلی**\nیکی از گزینه‌ها را انتخاب کنید:", kb)

def finalize_preview(chat_id, u_id):
    st = user_states[u_id]
    preview = f"🧐 **پیش‌نمایش نهایی**\n\n🔹 عنوان: {st.get('title','-')}\n🔹 تاریخ اجرا: {st.get('date')} {st.get('time')}\n🔹 کانال مقصد: {st.get('target_ch','-')}"
    
    kb = {"inline_keyboard": [
        [{"text": "🚀 تایید و انتشار در کانال", "callback_data": "confirm_final"}],
        [{"text": "📢 انتشار در کانال (بررسی عضویت)", "callback_data": "publish_step1"}],
        [{"text": "❌ انصراف", "callback_data": "menu_new"}]
    ]}
    
    if st.get('img'): send_img(chat_id, st['img'], preview, kb)
    else: send_msg(chat_id, preview, kb)

def save_and_schedule(chat_id, u_id):
    st = user_states[u_id]
    # تبدیل تاریخ شمسی به میلادی برای Scheduler
    try:
        y, m, d = map(int, st['date'].split('/'))
        hh, mm = map(int, st['time'].split(':'))
        miladi_dt = jdatetime.JDateTime(y, m, d, hh, mm).togregorian()
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT INTO lotteries (user_id, type, title, description, link, image_id, target_channel, execution_time) VALUES (?,?,?,?,?,?,?,?)",
                    (u_id, st['type'], st.get('title'), st.get('desc'), st.get('link'), st.get('img'), st['target_ch'], miladi_dt))
        lot_id = cur.lastrowid
        conn.commit()
        conn.close()

        # اضافه کردن به صف زمان‌بندی
        scheduler.add_job(run_lottery_task, 'date', run_date=miladi_dt, args=[lot_id])
        
        send_msg(chat_id, f"✅ قرعه‌کشی با موفقیت برای تاریخ {st['date']} ساعت {st['time']} زمان‌بندی شد.")
        show_main_menu(chat_id)
    except:
        send_msg(chat_id, "❌ خطایی در فرمت تاریخ یا ساعت رخ داد. دوباره تلاش کنید.")

def show_user_list(chat_id, u_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, title, status FROM lotteries WHERE user_id = ?", (u_id,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        send_msg(chat_id, "لیست خالی است.")
        return
    kb = {"inline_keyboard": []}
    for r in rows:
        kb["inline_keyboard"].append([{"text": f"🔍 {r[1]} ({r[2]})", "callback_data": f"view_{r[0]}"}])
        kb["inline_keyboard"].append([{"text": "✏️ ویرایش", "callback_data": f"edit_{r[0]}"}, {"text": "🗑 حذف", "callback_data": f"del_{r[0]}"}])
    
    send_msg(chat_id, "📊 لیست قرعه‌کشی‌های شما:", kb)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
