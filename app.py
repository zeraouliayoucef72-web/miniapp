import os
import sqlite3
from flask import Flask, request, jsonify
import telebot

app = Flask(__name__)

# ⚙️ إعدادات البوت والمسؤول
# يمكنك وضع التوكن والـ ID هنا مباشرة أو عبر الـ Environment Variables في Render
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'ضع_هنا_توكن_البوت_الخاص_بك')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 'ضع_هنا_رقم_حسابك_Id'))

bot = telebot.TeleBot(BOT_TOKEN)

# 🗄️ دالة لتهيئة قاعدة البيانات وإنشاء الجدول إذا لم يكن موجوداً
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# تهيئة قاعدة البيانات عند تشغيل السيرفر
init_db()

# 🌐 1. الرابط الرئيسي للميني أب (حل مشكلة Not Found)
@app.route('/')
def home():
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "⚠️ خطأ: ملف index.html غير موجود في مجلد المشروع!", 404

# 📊 2. رابط API تستدعيه صفحة index.html لجلب الأكواد وعرضها لداخل التطبيق
@app.route('/api/codes', methods=['GET'])
def get_codes():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, url, username, password FROM codes")
    rows = cursor.fetchall()
    conn.close()
    
    # تحويل البيانات إلى صيغة JSON لتسهيل قراءتها بـ JavaScript
    codes_list = []
    for row in rows:
        codes_list.append({
            "id": row[0],
            "url": row[1],
            "username": row[2],
            "password": row[3]
        })
    return jsonify(codes_list)

# 🤖 3. رابط استقبال تحديثات التليجرام (Webhook)
@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "OK", 200

# 🛠️ أوامر البوت لداخل التليجرام

# أمر ترحيبي
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 مرحباً بك في بوت إدارة أكواد Xtream IPTV!\nاضغط على زر Mini App لرؤية الأكواد الحالية.")

# عرض كل الأكواد (للأدمن فقط)
@bot.message_handler(commands=['view_codes'])
def view_codes(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ عذراً، هذا الأمر مخصص للمسؤول فقط.")
        return
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, url, username, password FROM codes")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(message, "📭 قاعدة البيانات فارغة، لا توجد أكواد حالياً.")
        return
    
    res = "📋 **الأكواد المخزنة حالياً:**\n\n"
    for r in rows:
        res += f"🆔 **ID:** `{r[0]}`\n🔗 **URL:** {r[1]}\n👤 **User:** `{r[2]}`\n🔑 **Pass:** `{r[3]}`\n"
        res += "────────────────\n"
    
    bot.send_message(message.chat.id, res, parse_mode='Markdown')

# إضافة كود جديد
@bot.message_handler(commands=['add_code'])
def add_code(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ عذراً، هذا الأمر مخصص للمسؤول فقط.")
        return
    
    parts = message.text.split()
    if len(parts) < 4:
        bot.reply_to(message, "⚠️ طريقة خاطئة! أرسل الأمر كالتالي:\n`/add_code <الرابط> <المستخدم> <الكلمة>`", parse_mode='Markdown')
        return
    
    url = parts[1]
    username = parts[2]
    password = parts[3]
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO codes (url, username, password) VALUES (?, ?, ?)", (url, username, password))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, "✅ تم حفظ الكود الجديد بنجاح!")

# حذف كود معين بواسطة الـ ID
@bot.message_handler(commands=['delete_code'])
def delete_code(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ عذراً، هذا الأمر مخصص للمسؤول فقط.")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ يرجى تحديد رقم الكود لحذفه. مثال:\n`/delete_code 1`", parse_mode='Markdown')
        return
    
    target_id = parts[1]
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM codes WHERE id = ?", (target_id,))
    conn.commit()
    deleted = conn.total_changes
    conn.close()
    
    if deleted > 0:
        bot.reply_to(message, f"🗑️ تم حذف الكود رقم {target_id} بنجاح!")
    else:
        bot.reply_to(message, "❌ لم يتم العثور على كود بهذا الرقم.")

# مسح جميع الأكواد دفعة واحدة
@bot.message_handler(commands=['clear_codes'])
def clear_codes(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ عذراً، هذا الأمر مخصص للمسؤول فقط.")
        return
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM codes")
    conn.commit()
    conn.close()
    
    bot.reply_to(message, "🗑️ تم إفراغ قاعدة البيانات ومسح جميع الأكواد بنجاح!")

if __name__ == '__main__':
    # تشغيل السيرفر
    # تأكد من إعداد المنفذ (Port) ليتناسب مع Render تلقائياً
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
