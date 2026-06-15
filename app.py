import os
import requests
import jdatetime
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from config import BOT_TOKEN, BASE_URL

app = Flask(__name__)
# دیتابیس برای ذخیره قرعه‌کشی‌ها
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lottery_bot.db'
db = SQLAlchemy(app)

# زمان‌بند برای اجرای خودکار قرعه‌کشی‌ها
scheduler = BackgroundScheduler()
scheduler.start()

# --- مدل دیتابیس ---
class Lottery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50))
    title = db.Column(db.String(100))
    winners_count = db.Column(db.Integer)
    channel_id = db.Column(db.String(100))
    exec_time = db.Column(db.DateTime) # ذخیره به میلادی
    status = db.Column(db.String(20), default='pending') # pending, done

with app.app_context():
    db.create_all()

# --- توابع کمکی ---
def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown', 'reply_markup': reply_markup}
    return requests.post(url, json=payload).json()

def shamsi_to_miladi(shamsi_str):
    """ تبدیل رشته '1403/03/25 19:30' به شیء datetime میلادی """
    try:
        date_part, time_part = shamsi_str.split(' ')
        y, m, d = map(int, date_part.split('/'))
        hh, mm = map(int, time_part.split(':'))
        # تبدیل شمسی به میلادی
        miladi_date = jdatetime.date(y, m, d).togregorian()
        return datetime(miladi_date.year, miladi_date.month, miladi_date.day, hh, mm)
    except:
        return None

def run_automated_lottery(lottery_id):
    """ این تابع توسط Scheduler در زمان مقرر صدا زده می‌شود """
    with app.app_context():
        lott = Lottery.query.get(lottery_id)
        if lott and lott.status == 'pending':
            # اینجا منطق انتخاب برنده از کامنت‌ها یا لیست شرکت‌کنندگان
            res_text = f"🎊 **نتیجه قرعه‌کشی فرارسید!**\n📌 عنوان: {lott.title}\n\n🏆 برندگان خوش‌شانس انتخاب شدند."
            send_message(lott.channel_id, res_text)
            
            lott.status = 'done'
            db.session.commit()

# --- مدیریت پیام‌ها ---
@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()
    if 'message' in data:
        msg = data['message']
        u_id, chat_id, text = str(msg['from']['id']), msg['chat']['id'], msg.get('text', '')

        if text == '/start':
            kb = {"inline_keyboard": [
                [{"text": "➕ قرعه‌کشی جدید", "callback_data": "new_lot"}],
                [{"text": "📋 قرعه‌کشی‌های من", "callback_data": "my_lots"}],
                [{"text": "💬 قرعه‌کشی روی پست (کامنت)", "callback_data": "comment_lot"}]
            ]}
            send_message(chat_id, "سلام! به ربات قرعه‌کشی خوش آمدید. یکی از گزینه‌ها را انتخاب کنید:", kb)

    elif 'callback_query' in data:
        cb = data['callback_query']
        u_id, chat_id, cmd = str(cb['from']['id']), cb['message']['chat']['id'], cb['data']

        if cmd == "my_lots":
            lots = Lottery.query.filter_by(user_id=u_id).all()
            if not lots:
                send_message(chat_id, "❌ شما هیچ قرعه‌کشی فعالی ندارید.")
            else:
                btns = [[{"text": f"{'⏳' if l.status=='pending' else '✅'} {l.title}", "callback_data": f"view_{l.id}"}] for l in lots]
                send_message(chat_id, "لیست قرعه‌کشی‌های شما:", {"inline_keyboard": btns})

        elif cmd.startswith("view_"):
            l_id = cmd.split("_")[1]
            l = Lottery.query.get(l_id)
            status_text = "در انتظار اجرا" if l.status == 'pending' else "انجام شده"
            msg_text = f"📌 عنوان: {l.title}\n⏰ زمان اجرا: {l.exec_time}\nوضعیت: {status_text}"
            btns = {"inline_keyboard": [[{"text": "🗑 حذف قرعه‌کشی", "callback_data": f"del_{l.id}"}]]}
            send_message(chat_id, msg_text, btns)

        elif cmd.startswith("del_"):
            l_id = cmd.split("_")[1]
            l = Lottery.query.get(l_id)
            db.session.delete(l)
            db.session.commit()
            send_message(chat_id, "🗑 قرعه‌کشی با موفقیت حذف شد.")

        elif cmd == "confirm_final":
            # این بخش زمانی اجرا می‌شود که کاربر دکمه تایید نهایی را بزند
            # فرض می‌کنیم اطلاعات در یک دیکشنری موقت user_temp_data ذخیره شده
            # miladi_dt = shamsi_to_miladi(user_temp_data[u_id]['time_str'])
            
            # ثبت در دیتابیس
            new_l = Lottery(user_id=u_id, title="تست", winners_count=1, channel_id="@test", exec_time=datetime.now()) # مقادیر فرضی
            db.session.add(new_l)
            db.session.commit()
            
            # اضافه کردن به صف زمان‌بندی
            scheduler.add_job(run_automated_lottery, 'date', run_date=new_l.exec_time, args=[new_l.id])
            send_message(chat_id, "✅ قرعه‌کشی ثبت و زمان‌بندی شد.")

    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
