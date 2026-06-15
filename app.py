import os
import requests
import jdatetime
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from config import BOT_TOKEN, BASE_URL

app = Flask(__name__)
# حافظه دائمی (SQLite)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lottery_data.db'
db = SQLAlchemy(app)

scheduler = BackgroundScheduler()
scheduler.start()

# --- مدل دیتابیس برای ذخیره قرعه‌کشی‌ها ---
class Lottery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50))
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    channel_id = db.Column(db.String(100))
    image_file_id = db.Column(db.String(200), nullable=True)
    post_link = db.Column(db.String(300), nullable=True) # برای قرعه‌کشی روی کامنت
    exec_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending') # pending, done

with app.app_context():
    db.create_all()

# دیکشنری موقت برای مراحل ساخت
user_states = {}

def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown', 'reply_markup': reply_markup}
    return requests.post(url, json=payload).json()

def send_photo(chat_id, file_id, caption, reply_markup=None):
    url = f"{BASE_URL}/sendPhoto"
    payload = {'chat_id': chat_id, 'photo': file_id, 'caption': caption, 'reply_markup': reply_markup}
    return requests.post(url, json=payload).json()

def shamsi_to_miladi(shamsi_str):
    try:
        # ورودی: 1403/03/25 19:10
        date_p, time_p = shamsi_str.split(' ')
        y, m, d = map(int, date_p.split('/'))
        hh, mm = map(int, time_p.split(':'))
        miladi = jdatetime.datetime(y, m, d, hh, mm).togregorian()
        return miladi
    except: return None

# --- منطق اجرای قرعه‌کشی در زمان مقرر ---
def run_lottery_task(lottery_id):
    with app.app_context():
        lott = Lottery.query.get(lottery_id)
        if not lott or lott.status != 'pending': return
        
        # در اینجا لیست شرکت‌کنندگان (از دیتابیس یا کامنت‌ها) استخراج می‌شود
        # برای سادگی، فعلاً اعلام پایان قرعه‌کشی:
        result_msg = f"🎉 **قرعه‌کشی انجام شد!**\n\n📌 موضوع: {lott.title}\n🎁 برنده‌ها به زودی در همین کانال اعلام می‌شوند."
        send_message(lott.channel_id, result_msg)
        
        lott.status = 'done'
        db.session.commit()

@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()
    if 'message' in data:
        msg = data['message']
        u_id = str(msg['from']['id'])
        chat_id = msg['chat']['id']
        text = msg.get('text', '')

        if text == '/start':
            kb = {"inline_keyboard": [
                [{"text": "🎁 قرعه‌کشی جدید", "callback_data": "start_new"}],
                [{"text": "💬 قرعه‌کشی روی کامنت پست", "callback_data": "start_comment_mode"}],
                [{"text": "📊 قرعه‌کشی‌های من", "callback_data": "my_lots"}]
            ]}
            send_message(chat_id, "خوش آمدید! مدیریت قرعه‌کشی‌های خود را شروع کنید:", kb)
            return jsonify({'ok': True})

        # --- هندل کردن آپلود عکس در مرحله آخر ---
        state = user_states.get(u_id, {}).get('step')
        if state == 'WAITING_FOR_PHOTO':
            if 'photo' in msg:
                # گرفتن بزرگترین سایز عکس
                file_id = msg['photo'][-1]['file_id']
                user_states[u_id]['image_id'] = file_id
                send_message(chat_id, "✅ تصویر دریافت شد. در حال آماده‌سازی پیش‌نمایش...")
            else:
                send_message(chat_id, "تصویری دریافت نشد، قرعه‌کشی بدون تصویر ثبت می‌شود.")
            
            # انتقال به مرحله پیش‌نمایش
            user_states[u_id]['step'] = 'PREVIEW'
            # (نمایش دکمه تایید نهایی)

    elif 'callback_query' in data:
        cb = data['callback_query']
        u_id, chat_id, cmd = str(cb['from']['id']), cb['message']['chat']['id'], cb['data']

        if cmd == "my_lots":
            lots = Lottery.query.filter_by(user_id=u_id).all()
            if not lots:
                send_message(chat_id, "شما هنوز قرعه‌کشی‌ای ثبت نکرده‌اید.")
            else:
                btns = []
                for l in lots:
                    icon = "✅" if l.status == 'done' else "⏳"
                    btns.append([{"text": f"{icon} {l.title}", "callback_data": f"manage_{l.id}"}])
                send_message(chat_id, "لیست قرعه‌کشی‌های شما (برای مدیریت کلیک کنید):", {"inline_keyboard": btns})

        elif cmd.startswith("manage_"):
            l_id = cmd.split("_")[1]
            l = Lottery.query.get(l_id)
            text = f"📌 عنوان: {l.title}\nوضعیت: {l.status}\nزمان اجرا: {l.exec_time}"
            kb = {"inline_keyboard": [
                [{"text": "🗑 حذف قرعه‌کشی", "callback_data": f"del_{l.id}"}],
                [{"text": "✏️ ویرایش عنوان", "callback_data": f"edit_{l.id}"}]
            ]}
            send_message(chat_id, text, kb)

        elif cmd.startswith("del_"):
            l_id = cmd.split("_")[1]
            l = Lottery.query.get(l_id)
            db.session.delete(l)
            db.session.commit()
            send_message(chat_id, "🗑 قرعه‌کشی با موفقیت حذف شد.")

        elif cmd == "start_comment_mode":
            user_states[u_id] = {'step': 'GET_POST_LINK'}
            send_message(chat_id, "🔗 لطفاً لینک پست کانال بله را بفرستید:\n(ربات باید در کانال ادمین باشد)")

    return jsonify({'ok': True})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
