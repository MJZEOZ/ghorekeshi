import os
import requests
from flask import Flask, request, jsonify
from config import BOT_TOKEN, BASE_URL, REQUIRED_CHANNEL

app = Flask(__name__)

# دیکشنری برای ذخیره داده‌های موقت کاربران
user_data = {}

def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return requests.post(url, json=payload)

def send_photo(chat_id, file_id, caption, reply_markup=None):
    url = f"{BASE_URL}/sendPhoto"
    payload = {'chat_id': chat_id, 'photo': file_id, 'caption': caption, 'parse_mode': 'Markdown'}
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
        return "Bot is Live!", 200

    data = request.get_json()
    if not data: return jsonify({'status': 'no_data'}), 200

    # مدیریت کلیک بر روی دکمه‌ها
    if 'callback_query' in data:
        cb = data['callback_query']
        u_id = cb['from']['id']
        chat_id = cb['message']['chat']['id']
        cmd = cb['data']
        
        requests.post(f"{BASE_URL}/answerCallbackQuery", json={'callback_query_id': cb['id']})

        if cmd == "new_lottery":
            user_data[u_id] = {'step': 'GET_TITLE', 'type': 'new'}
            send_message(chat_id, "✅ مسیر قرعه‌کشی جدید انتخاب شد.\n\n۱. لطفاً **عنوان قرعه‌کشی** را وارد کنید:")
        
        elif cmd == "post_lottery":
            user_data[u_id] = {'step': 'GET_LINK', 'type': 'post'}
            send_message(chat_id, "✅ مسیر قرعه‌کشی روی پست انتخاب شد.\n\n۱. لطفاً **لینک پست بله** را ارسال کنید:")
        
        elif cmd == "check_and_publish":
            if check_membership(u_id):
                send_message(chat_id, "🚀 تبریک! عضویت شما تایید شد. قرعه‌کشی در صف انتشار قرار گرفت.")
            else:
                keyboard = {"inline_keyboard": [[{"text": "📢 عضویت در وام‌سرا", "url": "https://ble.ir/wamsara"}],
                                              [{"text": "✅ عضو شدم (بررسی مجدد)", "callback_data": "check_and_publish"}]]}
                send_message(chat_id, "⚠️ شما هنوز عضو کانال حامی نشده‌اید. برای انتشار باید ابتدا عضو شوید:", keyboard)
        
        return jsonify({'status': 'ok'}), 200

    # مدیریت پیام‌های متنی و فایل‌ها
    if 'message' in data:
        msg = data['message']
        u_id = msg['from']['id']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')

        if text == '/start':
            user_data[u_id] = {'step': 'START'}
            keyboard = {
                "inline_keyboard": [[
                    {"text": "🎁 قرعه‌کشی جدید", "callback_data": "new_lottery"},
                    {"text": "📝 روی پست کانال", "callback_data": "post_lottery"}
                ]]
            }
            send_message(chat_id, "سلام! به ربات قرعه‌کشی خوش آمدید. 😊\nلطفاً انتخاب کنید که قصد انجام چه نوع قرعه‌کشی را دارید؟", keyboard)
            return jsonify({'status': 'ok'}), 200

        state = user_data.get(u_id, {}).get('step')

        # مرحله دریافت لینک (مخصوص مسیر دوم)
        if state == 'GET_LINK':
            user_data[u_id].update({'post_link': text, 'step': 'GET_WINNERS_COUNT'})
            send_message(chat_id, "لینک دریافت شد.\n\n۲. تعداد **نفرات برنده** را وارد کنید:")

        # مرحله دریافت عنوان (مخصوص مسیر اول)
        elif state == 'GET_TITLE':
            user_data[u_id].update({'title': text, 'step': 'GET_DESC'})
            send_message(chat_id, "۲. حالا **متن و توضیحات** قرعه‌کشی را بنویسید:")

        # دریافت توضیحات
        elif state == 'GET_DESC':
            user_data[u_id].update({'desc': text, 'step': 'GET_PHOTO'})
            send_message(chat_id, "۳. (اختیاری) یک **عکس** برای قرعه‌کشی بفرستید.\nاگر عکسی ندارید، عبارت 'ندارم' را بفرستید.")

        # دریافت عکس (اختیاری)
        elif state == 'GET_PHOTO':
            photo = msg.get('photo')
            if photo:
                user_data[u_id]['photo'] = photo[-1]['file_id']
            user_data[u_id]['step'] = 'GET_WINNERS_COUNT'
            send_message(chat_id, "۴. تعداد **نفرات برنده** (خروجی آیدی‌ها) را به عدد وارد کنید:")

        # دریافت تعداد برنده‌ها
        elif state == 'GET_WINNERS_COUNT':
            if text.isdigit():
                user_data[u_id].update({'count': text, 'step': 'GET_PRIZES'})
                send_message(chat_id, f"۵. لطفاً جوایز را برای این {text} نفر به ترتیب بنویسید:")
            else:
                send_message(chat_id, "لطفاً فقط عدد بفرستید.")

        # دریافت جوایز
        elif state == 'GET_PRIZES':
            user_data[u_id].update({'prizes': text, 'step': 'GET_TIME'})
            send_message(chat_id, "۶. تاریخ و ساعت قرعه‌کشی را بنویسید (مثلاً: فردا ساعت ۲۱):")

        # دریافت زمان و نمایش پیش‌نمایش
        elif state == 'GET_TIME':
            user_data[u_id].update({'time': text, 'step': 'PREVIEW'})
            d = user_data[u_id]
            
            # ساخت متن پیش‌نمایش
            preview_text = f"📋 **پیش‌نمایش قرعه‌کشی**\n\n"
            preview_text += f"🔹 عنوان: {d.get('title', 'قرعه‌کشی پست بله')}\n"
            preview_text += f"📝 توضیحات: {d.get('desc', 'بررسی دیدگاه‌های پست')}\n"
            preview_text += f"🎁 جوایز: {d['prizes']}\n"
            preview_text += f"👥 تعداد برنده‌ها: {d['count']} نفر\n"
            preview_text += f"⏰ زمان اجرا: {d['time']}"

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🚀 تایید و انتشار", "callback_data": "check_and_publish"}],
                    [{"text": "📢 عضویت در وام‌سرا", "url": "https://ble.ir/wamsara"}]
                ]
            }

            if d.get('photo'):
                send_photo(chat_id, d['photo'], preview_text, keyboard)
            else:
                send_message(chat_id, preview_text, keyboard)

    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
