import os
import requests
from flask import Flask, request, jsonify
from config import BOT_TOKEN, BASE_URL, REQUIRED_CHANNEL

app = Flask(__name__)

# ذخیره وضعیت و اطلاعات هر کاربر
user_states = {}

def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return requests.post(url, json=payload)

def check_membership(user_id):
    url = f"{BASE_URL}/getChatMember"
    params = {'chat_id': REQUIRED_CHANNEL, 'user_id': user_id}
    try:
        response = requests.get(url, params=params).json()
        status = response.get('result', {}).get('status')
        return status in ['member', 'administrator', 'creator']
    except:
        return False

@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "Bot is running!", 200

    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'status': 'ok'}), 200

    message = data['message']
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    text = message.get('text', '')

    # ۱. شروع و خوش‌آمدگویی
    if text == '/start':
        user_states[user_id] = {'step': 'START'}
        welcome_msg = "سلام! به ربات قرعه‌کشی خوش آمدید. 😊"
        keyboard = {
            "inline_keyboard": [[
                {"text": "قرعه‌کشی جدید", "callback_data": "new_lottery"},
                {"text": "روی پست کانال", "callback_data": "post_lottery"}
            ]]
        }
        send_message(chat_id, welcome_msg, keyboard)
        return jsonify({'status': 'ok'}), 200

    # بررسی دکمه‌های کلیک شده (Callback Query)
    if 'callback_query' in data:
        cq = data['callback_query']
        user_id = cq['from']['id']
        chat_id = cq['message']['chat']['id']
        choice = cq['data']

        if choice == "new_lottery":
            user_states[user_id] = {'step': 'GET_TITLE', 'type': 'new'}
            send_message(chat_id, "لطفاً **عنوان** قرعه‌کشی را بنویسید:")
        
        elif choice == "post_lottery":
            user_states[user_id] = {'step': 'GET_POST_LINK', 'type': 'post'}
            send_message(chat_id, "لطفاً **لینک پست بله** را ارسال کنید:")
        
        elif choice == "publish":
            if check_membership(user_id):
                send_message(chat_id, "✅ قرعه‌کشی با موفقیت تایید و آماده انتشار شد.")
            else:
                send_message(chat_id, f"❌ خطا! شما هنوز عضو کانال {REQUIRED_CHANNEL} نشده‌اید.")
        
        return jsonify({'status': 'ok'}), 200

    # منطق مراحل (Steps)
    state = user_states.get(user_id, {}).get('step')

    if state == 'GET_TITLE':
        user_states[user_id].update({'title': text, 'step': 'GET_DESC'})
        send_message(chat_id, "حالا **توضیحات و متن** قرعه‌کشی را بفرستید:")

    elif state == 'GET_DESC':
        user_states[user_id].update({'desc': text, 'step': 'GET_PHOTO'})
        send_message(chat_id, "اگر مایلید یک **عکس** بفرستید، در غیر این صورت بنویسید 'ندارم':")

    elif state == 'GET_PHOTO':
        # در اینجا فرض بر ساده‌سازی است (دریافت عکس یا متن 'ندارم')
        user_states[user_id].update({'step': 'GET_WINNERS_COUNT'})
        send_message(chat_id, "تعداد **نفرات برنده** را به عدد وارد کنید:")

    elif state == 'GET_WINNERS_COUNT':
        user_states[user_id].update({'winners_count': text, 'step': 'GET_PRIZES'})
        send_message(chat_id, f"لطفاً جوایز را به ترتیب برای {text} نفر بنویسید:")

    elif state == 'GET_PRIZES':
        user_states[user_id].update({'prizes': text, 'step': 'GET_TIME'})
        send_message(chat_id, "تاریخ و ساعت قرعه‌کشی را وارد کنید (مثلاً: فردا ساعت ۱۸):")

    elif state == 'GET_TIME':
        user_states[user_id].update({'time': text, 'step': 'PREVIEW'})
        s = user_states[user_id]
        preview = f"📋 **پیش‌نمایش قرعه‌کشی**\n\n🔹 عنوان: {s['title']}\n🔹 توضیحات: {s['desc']}\n🔹 جوایز: {s['prizes']}\n🔹 زمان: {s['time']}"
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "📢 انتشار در کانال", "callback_data": "publish"}],
                [{"text": "🔗 عضویت در وام‌سرا", "url": "https://ble.ir/wamsara"}]
            ]
        }
        send_message(chat_id, preview, keyboard)

    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
