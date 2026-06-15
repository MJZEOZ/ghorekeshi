from flask import Flask, request
import requests
import time
import threading
from config import BASE_URL, REQUIRED_CHANNEL
from lottery import pick_winners

app = Flask(__name__)

lotteries = {}


def send_message(chat_id, text):

    url = f"{BASE_URL}/sendMessage"

    data = {
        "chat_id": chat_id,
        "text": text
    }

    requests.post(url, json=data)


def check_channel_member(user_id):

    url = f"{BASE_URL}/getChatMember"

    data = {
        "chat_id": REQUIRED_CHANNEL,
        "user_id": user_id
    }

    r = requests.post(url, json=data).json()

    if r["result"]["status"] in ["member", "administrator", "creator"]:
        return True

    return False


@app.route("/", methods=["POST"])
def webhook():

    data = request.json

    if "message" not in data:
        return "ok"

    message = data["message"]

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "")

    if text == "/start":

        send_message(
            chat_id,
            "به ربات قرعه کشی خوش آمدید\nبرای ایجاد قرعه کشی /newlottery"
        )

    elif text == "/newlottery":

        lotteries[chat_id] = {
            "users": [],
            "prizes": ["100 هزار", "50 هزار", "20 هزار"],
            "time": time.time() + 3600
        }

        send_message(chat_id, "قرعه کشی ایجاد شد ✅")

    elif text == "/join":

        if not check_channel_member(user_id):

            send_message(chat_id, "ابتدا عضو کانال وامسرا شوید")
            return "ok"

        lotteries[chat_id]["users"].append(user_id)

        send_message(chat_id, "در قرعه کشی ثبت شدید ✅")

    return "ok"


def scheduler():

    while True:

        now = time.time()

        for chat_id in list(lotteries.keys()):

            lot = lotteries[chat_id]

            if now >= lot["time"]:

                winners = pick_winners(
                    lot["users"],
                    lot["prizes"]
                )

                text = "🎉 نتیجه قرعه کشی\n\n"

                for w in winners:

                    text += f"{w['user']} ➜ {w['prize']}\n"

                send_message(chat_id, text)

                del lotteries[chat_id]

        time.sleep(30)


threading.Thread(target=scheduler).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
