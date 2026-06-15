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

# اضافه کردن متد GET برای جلوگیری از خطای 405 و تست سلامت
@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "Bot is running! Webhook is active.", 200

    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'status': 'no message'}), 200

    message = data['message']
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    text = message.get('text', '')

    if text == '/start':
        send_message(chat_id, "سلام! به ربات قرعه‌کشی خوش آمدید.\nبرای ساخت قرعه‌کشی، ابتدا باید عضو کانال حامی باشید.")
        if check_membership(user_id):
            send_message(chat_id, "✅ عضویت تایید شد. عنوان قرعه‌کشی خود را بنویسید:")
        else:
            send_message(chat_id, f"❌ لطفاً ابتدا عضو کانال {REQUIRED_CHANNEL} شوید و دوباره /start بزنید.")

    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    # استفاده از پورت رندر
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
