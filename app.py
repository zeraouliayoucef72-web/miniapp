import os
import sqlite3
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# جلب المعلومات الحساسة من بيئة تشغيل Render بأمان
ADMIN_ID = os.environ.get('ADMIN_ID')  # الـ Telegram ID الخاص بك كأدمن
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') # توكن البوت لإرسال الردود

# دالة لإنشاء قاعدة البيانات والجداول إذا لم تكن موجودة
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # جدول الأكواد
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS iptv_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE
        )
    ''')
    # جدول المستخدمين لنظام التدوير
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id TEXT PRIMARY KEY,
            current_index INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# تشغيل تهيئة قاعدة البيانات عند إقلاع السيرفر
init_db()

# دالة مساعدة لإرسال رسائل للمشرف عبر التليجرام
def send_telegram_reply(chat_id, text):
    if TELEGRAM_BOT_TOKEN:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            requests.post(url, json=payload)
        except Exception as e:
            print(f"Error sending telegram message: {e}")

# 1. الـ API الخاص بالـ Mini App لجلب الأكواد للمستخدمين بنظام التدوير (Rotation)
@app.route('/get_code', methods=['POST'])
def get_code():
    data = request.get_json() or {}
    telegram_id = str(data.get('telegram_id', ''))
    ad_completed = data.get('ad_completed', False)

    if not telegram_id:
        return jsonify({"error": "معرف التليجرام مطلوب"}), 400

    if not ad_completed:
        return jsonify({"error": "يجب إنهاء الإعلان أولاً"}), 400

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    try:
        # جلب أو إنشاء المستخدم لمعرفة الـ index الحالي له
        cursor.execute("SELECT current_index FROM users WHERE telegram_id = ?", (telegram_id,))
        user = cursor.fetchone()
        
        if user is None:
            cursor.execute("INSERT INTO users (telegram_id, current_index) VALUES (?, 0)", (telegram_id,))
            conn.commit()
            current_index = 0
        else:
            current_index = user[0]

        # جلب جميع الأكواد المتوفرة مرتبة حسب تاريخ إضافتها
        cursor.execute("SELECT code FROM iptv_codes ORDER BY id ASC")
        all_codes = cursor.fetchall()

        if not all_codes:
            return jsonify({"error": "لا توجد أكواد متوفرة حالياً في النظام"}), 404

        # نظام الـ Rotation (إذا وصل لآخر كود يعود للكود الأول تلقائياً)
        target_index = current_index % len(all_codes)
        selected_code = all_codes[target_index][0]

        # تحديث الـ index للمستخدم للطلبات القادمة
        cursor.execute("UPDATE users SET current_index = ? WHERE telegram_id = ?", (current_index + 1, telegram_id))
        conn.commit()

        return jsonify({"code": selected_code})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# 2. 🛠️ لوحة تحكم الأدمن عبر الـ Webhook (تستقبل وتنفذ الأوامر ديريكت من التليجرام)
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json() or {}
    
    if "message" in update:
        message = update["message"]
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()

        # التحقق من هوية المرسل (لازم يكون أنت برك صاحب الـ ADMIN_ID)
        if chat_id == str(ADMIN_ID):
            
            # [1] أمر إضافة كود جديد للبوت: /add_code هنا_تكتب_الكود
            if text.startswith('/add_code '):
                new_code = text.replace('/add_code ', '').strip()
                if new_code:
                    conn = sqlite3.connect('database.db')
                    cursor = conn.cursor()
                    try:
                        cursor.execute("INSERT OR IGNORE INTO iptv_codes (code) VALUES (?)", (new_code,))
                        conn.commit()
                        send_telegram_reply(chat_id, "✅ تم حفظ الكود بنجاح في قاعدة البيانات (SQLite)!")
                    except Exception as e:
                        conn.rollback()
                        send_telegram_reply(chat_id, f"❌ حدث خطأ أثناء الحفظ: {str(e)}")
                    finally:
                        conn.close()
                else:
                    send_telegram_reply(chat_id, "⚠️ يرجى كتابة الكود بعد الأمر مباشرة.")
            
            # [2] أمر تفقد الأكواد الحالية: /view_codes
            elif text == '/view_codes':
                conn = sqlite3.connect('database.db')
                cursor = conn.cursor()
                cursor.execute("SELECT id, code FROM iptv_codes ORDER BY id ASC")
                rows = cursor.fetchall()
                conn.close()
                
                if not rows:
                    send_telegram_reply(chat_id, "📭 قاعدة البيانات فارغة حالياً، لا توجد أكواد.")
                else:
                    response = "📊 **الأكواد المتوفرة حالياً في قاعدة البيانات:**\n\n"
                    for row in rows:
                        response += f"🆔 **ID:** `{row[0]}`\n🔑 **الكود:** `{row[1]}`\n-------------------\n"
                    send_telegram_reply(chat_id, response)

            # [3] أمر مسح جميع الأكواد: /clear_codes
            elif text == '/clear_codes':
                conn = sqlite3.connect('database.db')
                cursor = conn.cursor()
                try:
                    cursor.execute("DELETE FROM iptv_codes")
                    cursor.execute("UPDATE users SET current_index = 0")  # تصفير عداد تدوير المستخدمين أيضاً
                    conn.commit()
                    send_telegram_reply(chat_id, "🗑️ تم مسح جميع الأكواد وتصفير عدادات المستخدمين بنجاح!")
                except Exception as e:
                    conn.rollback()
                    send_telegram_reply(chat_id, f"❌ حدث خطأ أثناء مسح البيانات: {str(e)}")
                finally:
                    conn.close()
                        
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
