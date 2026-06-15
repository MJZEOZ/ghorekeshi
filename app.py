import os
import requests
from flask import Flask, request, jsonify
from config import BOT_TOKEN, BASE_URL, REQUIRED_CHANNEL
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

user_data = {}

def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
    if reply_markup: payload['reply_markup'] = reply_markup
    return requests.post(url, json=payload).json()

def check_membership(user_id):
    url = f"{BASE_URL}/getChatMember"
    params = {'chat_id': REQUIRED_CHANNEL, 'user_id': user_id}
    try:
        res = requests.get(url, params=params).json()
        return res.get('result', {}).get('status') in ['member', 'administrator', 'creator']
    except: return False

def run_lottery_logic(chat_id, lottery_info):
    # اینجا منطق انتخاب برنده از بین لیست شرکت‌کنندگان قرار می‌گیرد
    send_message(chat_id, f"🎉 **زمان قرعه‌کشی فرارسید!**\n\n🎁 قرعه‌کشی '{lottery_info['title']}' انجام شد و برنده‌ها به زودی اعلام می‌شوند.")

@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET': return "Bot is Active", 200
    data = request.get_json()
    if not data: return jsonify({'status': 'no_data'}), 200

    if 'callback_query' in data:
        cb = data['callback_query']
        u_id, chat_id, cmd = cb['from']['id'], cb['message']['chat']['id'], cb['data']
        requests.post(f"{BASE_URL}/answerCallbackQuery", json={'callback_query_id': cb['id']})

        if cmd == "new_lottery":
            user_data[u_id] = {'step': 'GET_TITLE', 'prizes': []}
            send_message(chat_id, "۱. عنوان قرعه‌کشی را وارد کنید:")
        
        elif cmd == "publish_final":
            if check_membership(u_id):
                d = user_data[u_id]
                # ارسال به کانال هدف
                target_channel = d.get('target_channel')
                preview = f"🎁 **قرعه‌کشی جدید در این کانال!**\n\n📌 {d['title']}\n📝 {d['desc']}\n⏰ زمان: {d['time_str']}"
                
                res = send_message(target_channel, preview)
                if res.get('ok'):
                    send_message(chat_id, "🚀 پست با موفقیت در کانال شما منتشر شد و در زمان مقرر قرعه‌کشی انجام می‌شود.")
                    # زمان‌بندی اجرای قرعه‌کشی (نیاز به تبدیل متن به فرمت تاریخ دارد)
                    # scheduler.add_job(run_lottery_logic, 'date', run_date=datetime(2024, 6, 16, 21, 0), args=[target_channel, d])
                else:
                    send_message(chat_id, "❌ خطا! ربات در کانال شما ادمین نیست یا آیدی کانال اشتباه است.")
            else:
                send_message(chat_id, "⚠️ ابتدا باید عضو کانال حامی (@wamsara) شوید.")
        
        return jsonify({'status': 'ok'}), 200

    if 'message' in data:
        msg = data['message']
        u_id, chat_id = msg['from']['id'], msg['chat']['id']
        text = msg.get('text', '')

        if text == '/start':
            keyboard = {"inline_keyboard": [[{"text": "🎁 قرعه‌کشی جدید", "callback_data": "new_lottery"}]]}
            send_message(chat_id, "خوش آمدید! برای شروع روی دکمه زیر بزنید:", keyboard)
            return jsonify({'status': 'ok'}), 200

        state = user_data.get(u_id, {}).get('step')

        if state == 'GET_TITLE':
            user_data[u_id].update({'title': text, 'step': 'GET_DESC'})
            send_message(chat_id, "۲. متن و توضیحات را بفرستید:")

        elif state == 'GET_DESC':
            user_data[u_id].update({'desc': text, 'step': 'GET_WINNERS_COUNT'})
            send_message(chat_id, "۳. تعداد برنده‌ها را وارد کنید (مثلاً 2):")

        elif state == 'GET_WINNERS_COUNT':
            if text.isdigit():
                count = int(text)
                user_data[u_id].update({'total_winners': count, 'current_prize_num': 1, 'step': 'GET_PRIZES'})
                send_message(chat_id, f"۴. جایزه نفر ۱ از {count} را وارد کنید:")
            
        elif state == 'GET_PRIZES':
            user_data[u_id]['prizes'].append(text)
            current = user_data[u_id]['current_prize_num']
            total = user_data[u_id]['total_winners']
            
            if current < total:
                user_data[u_id]['current_prize_num'] += 1
                send_message(chat_id, f"جایزه نفر {current + 1} را وارد کنید:")
            else:
                user_data[u_id]['step'] = 'GET_CHANNEL_ID'
                send_message(chat_id, "۵. آیدی کانال خود را وارد کنید (مثلاً @mychannel):\n(حتماً ربات را در کانال ادمین کنید)")

        elif state == 'GET_CHANNEL_ID':
            user_data[u_id].update({'target_channel': text, 'step': 'GET_TIME'})
            send_message(chat_id, "۶. زمان قرعه‌کشی را وارد کنید (مثال: 1403/04/01 21:00):")

        elif state == 'GET_TIME':
            user_data[u_id].update({'time_str': text, 'step': 'PREVIEW'})
            d = user_data[u_id]
            prize_list = "\n".join([f"{i+1}. {p}" for i, p in enumerate(d['prizes'])])
            preview = f"📝 **پیش‌نمایش نهایی**\n\nعنوان: {d['title']}\nجوایز:\n{prize_list}\n\nکانال مقصد: {d['target_channel']}"
            
            keyboard = {"inline_keyboard": [[{"text": "🚀 تایید و انتشار در کانال", "callback_data": "publish_final"}]]}
            send_message(chat_id, preview, keyboard)

    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
