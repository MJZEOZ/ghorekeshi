from flask import Flask, request, jsonify
import requests
from config import BOT_TOKEN, BASE_URL, REQUIRED_CHANNEL

app = Flask(__name__)

def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text}
    return requests.post(url, json=payload)

def check_membership(user_id):
    url = f"{BASE_URL}/getChatMember"
    params = {'chat_id': REQUIRED_CHANNEL, 'user_id': user_id}
    try:
        response = requests.get(url, params=params).json()
        if response.get('ok'):
            status = response['result'].get('status')
            return status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Error checking membership: {e}")
    return False

@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'status': 'no message'}), 200

    message = data['message']
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    text = message.get('text', '')

    if text == '/start':
        if check_membership(user_id):
            send_message(chat_id, "✅ شما عضو کانال هستید و می‌توانید در قرعه‌کشی شرکت کنید!")
        else:
            msg = f"❌ برای استفاده از ربات باید ابتدا عضو کانال زیر شوید:\n\n{REQUIRED_CHANNEL}\n\nبعد از عضویت دوباره /start را بزنید."
            send_message(chat_id, msg)
    
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
