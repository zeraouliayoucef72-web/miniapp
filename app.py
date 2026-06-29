import os
import sqlite3
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
DB_FILE = "database.db"


def init_db():
    """إنشاء جدول المستخدمين إذا لم يكن موجوداً"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            telegram_id TEXT PRIMARY KEY,
            current_index INTEGER DEFAULT 0
        )
    """
    )
    conn.commit()
    conn.close()


def get_all_codes():
    """قراءة الأكواد من ملف codes.txt وتقسيمها بناءً على الفاصل ---"""
    if not os.path.exists("codes.txt"):
        return []
    with open("codes.txt", "r", encoding="utf-8") as f:
        content = f.read()
    # تقسيم الأكواد وتنظيف الفراغات السطرية
    codes = [c.strip() for c in content.split("---") if c.strip()]
    return codes


@app.route("/")
def index():
    """عرض الواجهة الرئيسية للتطبيق"""
    return render_template("index.html")


@app.route("/get_code", methods=["POST"])
def get_code():
    """صرف الكود التالي للمستخدم بعد التأكد من تخطي الإعلان"""
    data = request.json or {}
    tg_id = data.get("telegram_id")
    ad_completed = data.get("ad_completed")

    if not tg_id:
        return jsonify({"error": "معرف التليجرام مفقود!"}), 400

    if not ad_completed:
        return jsonify({"error": "يجب مشاهدة الإعلان كاملاً أولاً!"}), 400

    codes = get_all_codes()
    if not codes:
        return jsonify({"error": "لا توجد أكواد متاحة حالياً في السيرفر."}), 404

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # التحقق من وجود المستخدم أو إنشائه
    cursor.execute(
        "SELECT current_index FROM users WHERE telegram_id = ?", (str(tg_id),)
    )
    row = cursor.fetchone()

    if row is None:
        current_index = 0
        cursor.execute(
            "INSERT INTO users (telegram_id, current_index) VALUES (?, ?)",
            (str(tg_id), current_index),
        )
    else:
        current_index = row[0]

    # الحماية في حال تم تعديل ملف الأكواد وحذف بعضها لتفادي خطأ خارج النطاق
    if current_index >= len(codes):
        current_index = 0

    # اختيار الكود الحالي للمستخدم
    selected_code = codes[current_index]

    # تحديث الترتيب للمرة القادمة (والعودة للصفر إذا انتهت الأكواد)
    next_index = (current_index + 1) % len(codes)
    cursor.execute(
        "UPDATE users SET current_index = ? WHERE telegram_id = ?",
        (next_index, str(tg_id)),
    )

    conn.commit()
    conn.close()

    return jsonify({"code": selected_code})


# تفعيل قاعدة البيانات عند بدء التشغيل
init_db()

if __name__ == "__main__":
    app.run(debug=True)
