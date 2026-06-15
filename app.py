from flask import Flask, request, jsonify
import requests
from config import BOT_TOKEN, BASE_URL, REQUIRED_CHANNEL

app = Flask(__name__)

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
        if response.get('ok'):
            status = response['result'].get('status')
            return status in ['member', 'administrator', 'creator']
    except: return False
    return False

def is_bot_admin(channel_id):
    url = f"{BASE_URL}/getChatMember"
    # آیدی عددی ربات شما از روی توکن (بخش اول توکن)
    bot_user_id = BOT_TOKEN.split(':')[0]
    params = {'chat_id': channel_id, 'user_id': bot_user_id}
    try:
        response = requests.get(url, params=params).json()
        if response.get('ok'):
            return response['result'].get('status') == 'administrator'
    except: return False
    return False

@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'status': 'ok'}), 200

    message = data['message']
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    text = message.get('text', '')

    if text == '/start':
        send_message(chat_id, "سلام! به ربات قرعه‌کشی خوش آمدید.\nبرای ساخت قرعه‌کشی جدید، عنوان قرعه‌کشی را ارسال کنید.")

    elif text:
        # فرض می‌کنیم هر متنی غیر از /start، عنوان قرعه‌کشی است
        if not check_membership(user_id):
            msg = f"⚠️ برای انتشار قرعه‌کشی، شما باید ابتدا عضو کانال ما باشید:\n{REQUIRED_CHANNEL}\n\nپس از عضویت، دوباره تلاش کنید."
            send_message(chat_id, msg)
        else:
            msg = "✅ قرعه‌کشی ساخته شد!\n\nحالا برای انتشار در کانال خودتان:\n۱. ربات را در کانال مقصد ادمین کنید.\n۲. آیدی کانال را با @ ارسال کنید (مثلاً @my_channel)."
            send_message(chat_id, msg)
            
    # در این مرحله اگر کاربر آیدی کانال فرستاد، ادمین بودن ربات چک می‌شود
    if text.startswith('@') and text != REQUIRED_CHANNEL:
        if is_bot_admin(text):
            send_message(chat_id, f"🚀 ربات در کانال {text} ادمین است. قرعه‌کشی با موفقیت منتشر شد!")
            # اینجا کد ارسال پیام قرعه‌کشی به کانال مقصد اضافه می‌شود
            send_message(text, "🎉 قرعه‌کشی جدید در این کانال آغاز شد!")
        else:
            send_message(chat_id, f"❌ خطا: من هنوز در کانال {text} ادمین نشده‌ام.")

    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
