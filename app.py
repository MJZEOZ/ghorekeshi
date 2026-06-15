import os
import requests
import re
from flask import Flask, request, jsonify
# در صورت نیاز کتابخانه‌های دیتابیس و زمان‌بندی را که قبلاً داشتید اینجا اضافه کنید

app = Flask(__name__)

# توکن و آدرس پایه (این مقادیر را از config خود بخوانید)
BOT_TOKEN = "1273514608:yPIBl5Mk_UFQ4EFQv_fy3VcaxT3S-KwdfD8"
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

# حافظه موقت برای وضعیت کاربران
user_states = {}

def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown', 'reply_markup': reply_markup}
    return requests.post(url, json=payload).json()

def extract_post_info(link):
    # فرمت لینک بله: https://ble.ir/channel_name/post_id
    pattern = r"ble\.ir/([^/]+)/(\d+)"
    match = re.search(pattern, link)
    if match:
        return match.group(1), match.group(2) # (channel, post_id)
    return None, None

@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()
    if 'message' in data:
        msg = data['message']
        u_id = str(msg['from']['id'])
        chat_id = msg['chat']['id']
        text = msg.get('text', '').strip()

        # --- شروع فرآیند با دکمه یا دستور ---
        if text == '/start':
            kb = {"inline_keyboard": [
                [{"text": "💬 قرعه‌کشی روی کامنت پست", "callback_data": "start_comment_mode"}]
            ]}
            send_message(chat_id, "خوش آمدید! لطفاً نوع قرعه‌کشی را انتخاب کنید:", kb)
            return jsonify({'ok': True})

        # --- مدیریت مراحل (State Machine) ---
        state = user_states.get(u_id, {}).get('step')

        # مرحله 1: دریافت لینک پست
        if state == 'GET_POST_LINK':
            channel, post_id = extract_post_info(text)
            if channel and post_id:
                user_states[u_id]['post_link'] = text
                user_states[u_id]['channel_id'] = channel
                user_states[u_id]['post_id'] = post_id
                
                # رفتن به مرحله بعد: عکس
                user_states[u_id]['step'] = 'WAITING_FOR_PHOTO'
                kb = {"inline_keyboard": [[{"text": "⏩ بدون عکس ادامه بده", "callback_data": "skip_photo"}]]}
                send_message(chat_id, "✅ لینک تایید شد.\n\n🖼 حالا اگر مایل هستید یک **تصویر** بفرستید، در غیر این صورت روی دکمه زیر بزنید:", kb)
            else:
                send_message(chat_id, "❌ لینک ارسالی معتبر نیست. لطفاً لینک پست را از بله کپی کرده و بفرستید.")

        # مرحله 2: دریافت عکس (اگر کاربر عکس فرستاد)
        elif state == 'WAITING_FOR_PHOTO':
            if 'photo' in msg:
                file_id = msg['photo'][-1]['file_id']
                user_states[u_id]['image_id'] = file_id
                send_message(chat_id, "✅ تصویر ذخیره شد.")
                proceed_to_final(chat_id, u_id)
            else:
                send_message(chat_id, "لطفاً عکس بفرستید یا دکمه «بدون عکس» را بزنید.")

    elif 'callback_query' in data:
        cb = data['callback_query']
        u_id = str(cb['from']['id'])
        chat_id = cb['message']['chat']['id']
        cmd = cb['data']

        if cmd == "start_comment_mode":
            user_states[u_id] = {'step': 'GET_POST_LINK'}
            send_message(chat_id, "🔗 لطفاً لینک پست مورد نظر را بفرستید:\n(مثال: https://ble.ir/dailybahar/12345)")

        elif cmd == "skip_photo":
            user_states[u_id]['image_id'] = None
            proceed_to_final(chat_id, u_id)

    return jsonify({'ok': True})

def proceed_to_final(chat_id, u_id):
    data = user_states[u_id]
    user_states[u_id]['step'] = 'FINAL_CONFIRM'
    
    preview_text = (
        "📝 **پیش‌نمایش قرعه‌کشی کامنت**\n\n"
        f"🔗 لینک پست: {data['post_link']}\n"
        f"🆔 کانال: @{data['channel_id']}\n"
        "🖼 وضعیت عکس: " + ("دارد ✅" if data.get('image_id') else "ندارد ❌") + "\n\n"
        "آیا اطلاعات مورد تایید است؟"
    )
    
    kb = {"inline_keyboard": [
        [{"text": "🚀 تایید و انتشار در کانال", "callback_data": "publish_now"}],
        [{"text": "🗑 انصراف", "callback_data": "cancel"}]
    ]}
    
    send_message(chat_id, preview_text, kb)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
