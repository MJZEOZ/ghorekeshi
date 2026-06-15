import os
import re
import sqlite3
import requests
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

DB_PATH = "lottery_data.db"

# حافظه موقت وضعیت کاربران
user_states = {}

# ---------------------------
# دیتابیس
# ---------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lotteries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT,
            description TEXT,
            channel TEXT,
            post_id TEXT,
            message_id TEXT,
            image_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------------------
# ابزارهای ارسال پیام
# ---------------------------
def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return requests.post(f"{BASE_URL}/sendMessage", json=payload).json()

def send_photo(chat_id, photo, caption, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return requests.post(f"{BASE_URL}/sendPhoto", json=payload).json()

# ---------------------------
# دیتابیس
# ---------------------------
def save_lottery(user_id, lot_type, title=None, description=None, channel=None, post_id=None, message_id=None, image_id=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lotteries (user_id, type, title, description, channel, post_id, message_id, image_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    """, (user_id, lot_type, title, description, channel, post_id, message_id, image_id))
    conn.commit()
    conn.close()

def get_user_lotteries(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, type, title, status, created_at
        FROM lotteries
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

# ---------------------------
# تشخیص لینک بله
# ---------------------------
def extract_ble_post_link(link):
    """
    فرمت‌های قابل قبول:
    https://ble.ir/channel/post_id/message_id
    https://ble.ir/channel/post_id
    """
    pattern = r'^https?://ble\.ir/([^/\s]+)/(-?\d+)(?:/(\d+))?/?$'
    m = re.match(pattern, link.strip())
    if not m:
        return None

    return {
        "channel": m.group(1),
        "post_id": m.group(2),
        "message_id": m.group(3)
    }

# ---------------------------
# منوی اصلی
# ---------------------------
def main_menu(chat_id):
    kb = {
        "inline_keyboard": [
            [{"text": "🎁 قرعه‌کشی جدید", "callback_data": "new_lottery"}],
            [{"text": "💬 قرعه‌کشی روی کامنت پست", "callback_data": "comment_lottery"}],
            [{"text": "📊 قرعه‌کشی‌های من", "callback_data": "my_lotteries"}]
        ]
    }
    send_message(chat_id, "خوش آمدید! مدیریت قرعه‌کشی‌های خود را از اینجا شروع کنید:", kb)

# ---------------------------
# مرحله عکس اختیاری
# ---------------------------
def ask_for_photo(chat_id, user_id):
    user_states[user_id]["step"] = "WAITING_FOR_PHOTO"
    kb = {
        "inline_keyboard": [
            [{"text": "⏩ بدون عکس ادامه بده", "callback_data": "skip_photo"}]
        ]
    }
    send_message(
        chat_id,
        "🖼 اگر دوست داری یک **عکس** برای قرعه‌کشی بفرست.\nاگر نه، روی دکمه زیر بزن یا فقط ادامه بده:",
        kb
    )

# ---------------------------
# پیش‌نمایش
# ---------------------------
def show_preview(chat_id, user_id):
    data = user_states[user_id]
    text = (
        "📝 *پیش‌نمایش قرعه‌کشی*\n\n"
        f"📌 نوع: {data.get('lot_type', '-')}\n"
        f"🔗 لینک پست: {data.get('post_link', '-')}\n"
        f"🆔 کانال: @{data.get('channel', '-')}\n"
        f"🆔 post_id: {data.get('post_id', '-')}\n"
        f"🖼 عکس: {'دارد ✅' if data.get('image_id') else 'ندارد ❌'}\n"
    )

    kb = {
        "inline_keyboard": [
            [{"text": "✅ تایید و ذخیره", "callback_data": "confirm_save"}],
            [{"text": "🗑 انصراف", "callback_data": "cancel_flow"}]
        ]
    }

    if data.get("image_id"):
        send_photo(chat_id, data["image_id"], text, kb)
    else:
        send_message(chat_id, text, kb)

# ---------------------------
# Flask webhook
# ---------------------------
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json(force=True, silent=True) or {}

    # ---------------- message ----------------
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        user_id = str(msg["from"]["id"])
        text = msg.get("text", "").strip()

        if text == "/start":
            main_menu(chat_id)
            return jsonify({"ok": True})

        state = user_states.get(user_id, {}).get("step")

        # شروع قرعه‌کشی جدید
        if state == "NEW_LOTTERY_TITLE":
            user_states[user_id]["title"] = text
            user_states[user_id]["step"] = "NEW_LOTTERY_DESC"
            send_message(chat_id, "✍️ حالا توضیحات قرعه‌کشی را بفرست:")
            return jsonify({"ok": True})

        if state == "NEW_LOTTERY_DESC":
            user_states[user_id]["description"] = text
            user_states[user_id]["step"] = "NEW_LOTTERY_IMAGE"
            ask_for_photo(chat_id, user_id)
            return jsonify({"ok": True})

        if state == "WAITING_FOR_PHOTO":
            if "photo" in msg:
                file_id = msg["photo"][-1]["file_id"]
                user_states[user_id]["image_id"] = file_id
                user_states[user_id]["step"] = "PREVIEW"
                show_preview(chat_id, user_id)
            else:
                # اگر متن فرستاد، یعنی عکس نمی‌خواهد
                user_states[user_id]["image_id"] = None
                user_states[user_id]["step"] = "PREVIEW"
                show_preview(chat_id, user_id)
            return jsonify({"ok": True})

        # قرعه‌کشی روی کامنت پست
        if state == "COMMENT_WAIT_LINK":
            info = extract_ble_post_link(text)
            if not info:
                send_message(
                    chat_id,
                    "❌ لینک ارسالی معتبر نیست.\n\n"
                    "فرمت درست باید شبیه این باشد:\n"
                    "`https://ble.ir/dailybahar/-3904237544190906269/1759920415664`"
                )
                return jsonify({"ok": True})

            user_states[user_id]["post_link"] = text
            user_states[user_id]["channel"] = info["channel"]
            user_states[user_id]["post_id"] = info["post_id"]
            user_states[user_id]["message_id"] = info["message_id"]

            user_states[user_id]["step"] = "WAITING_FOR_PHOTO"
            send_message(chat_id, "✅ لینک دریافت شد و معتبر است.")
            ask_for_photo(chat_id, user_id)
            return jsonify({"ok": True})

        return jsonify({"ok": True})

    # ---------------- callback ----------------
    if "callback_query" in data:
        cb = data["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        user_id = str(cb["from"]["id"])
        cmd = cb["data"]

        if cmd == "new_lottery":
            user_states[user_id] = {"step": "NEW_LOTTERY_TITLE", "lot_type": "قرعه‌کشی جدید"}
            send_message(chat_id, "🎁 عنوان قرعه‌کشی را بفرست:")
            return jsonify({"ok": True})

        if cmd == "comment_lottery":
            user_states[user_id] = {"step": "COMMENT_WAIT_LINK", "lot_type": "قرعه‌کشی روی کامنت پست"}
            send_message(
                chat_id,
                "🔗 لطفاً لینک پست مورد نظر را بفرستید:\n\n"
                "مثال:\n"
                "`https://ble.ir/dailybahar/-3904237544190906269/1759920415664`"
            )
            return jsonify({"ok": True})

        if cmd == "my_lotteries":
            rows = get_user_lotteries(user_id)
            if not rows:
                send_message(chat_id, "هنوز هیچ قرعه‌کشی‌ای ثبت نکرده‌ای.")
            else:
                btns = []
                for rid, typ, title, status, created_at in rows:
                    label = f"#{rid} | {title or typ} | {status}"
                    btns.append([{"text": label[:60], "callback_data": f"lot_{rid}"}])
                send_message(chat_id, "📊 قرعه‌کشی‌های شما:", {"inline_keyboard": btns})
            return jsonify({"ok": True})

        if cmd == "skip_photo":
            user_states[user_id]["image_id"] = None
            user_states[user_id]["step"] = "PREVIEW"
            show_preview(chat_id, user_id)
            return jsonify({"ok": True})

        if cmd == "confirm_save":
            data = user_states.get(user_id, {})
            save_lottery(
                user_id=user_id,
                lot_type=data.get("lot_type"),
                title=data.get("title"),
                description=data.get("description"),
                channel=data.get("channel"),
                post_id=data.get("post_id"),
                message_id=data.get("message_id"),
                image_id=data.get("image_id")
            )
            user_states.pop(user_id, None)
            send_message(chat_id, "✅ قرعه‌کشی با موفقیت ذخیره شد.")
            main_menu(chat_id)
            return jsonify({"ok": True})

        if cmd == "cancel_flow":
            user_states.pop(user_id, None)
            send_message(chat_id, "لغو شد.")
            main_menu(chat_id)
            return jsonify({"ok": True})

        if cmd.startswith("lot_"):
            lot_id = cmd.split("_", 1)[1]
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id, type, title, description, channel, post_id, message_id, image_id, status, created_at FROM lotteries WHERE id = ? AND user_id = ?", (lot_id, user_id))
            row = cur.fetchone()
            conn.close()

            if not row:
                send_message(chat_id, "این قرعه‌کشی پیدا نشد.")
                return jsonify({"ok": True})

            _, typ, title, desc, channel, post_id, message_id, image_id, status, created_at = row
            text = (
                f"🧾 *جزئیات قرعه‌کشی*\n\n"
                f"ID: {lot_id}\n"
                f"نوع: {typ}\n"
                f"عنوان: {title or '-'}\n"
                f"وضعیت: {status}\n"
                f"کانال: @{channel or '-'}\n"
                f"post_id: {post_id or '-'}\n"
                f"message_id: {message_id or '-'}\n"
                f"تاریخ ثبت: {created_at}"
            )
            send_message(chat_id, text)
            return jsonify({"ok": True})

    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
