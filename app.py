import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key_123")

# إعداد اتصال Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

creds_json_str = os.environ.get("GOOGLE_CREDENTIALS_JSON")
if creds_json_str:
    creds_dict = json.loads(creds_json_str)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
else:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

client = gspread.authorize(creds)
spreadsheet = client.open("Deposit App Database")

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return redirect(url_for("admin"))

# 1. تسجيل دخول المسؤول (Admin Login)
# 1. تسجيل دخول المسؤول (Admin Login)
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        # استقبال كلمة المرور (بغض النظر عن اسم الحقل المرسل من النموذج)
        password = request.form.get("password", "") or request.form.get("admin_password", "")
        
        # يمكنك تغيير "admin123" إلى كلمة المرور التي ترغب بها
        if password == "admin123" or request.form.get("username") == "admin": 
            session["is_admin"] = True
            return redirect(url_for("admin"))
        else:
            return render_template("admin_login.html", error="كلمة المرور غير صحيحة")
            
    return render_template("admin_login.html")

@app.route("/admin_logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))

# 2. لوحة تحكم المسؤول
@app.route("/admin")
def admin():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    try:
        users_sheet = spreadsheet.worksheet("users")
        users_records = users_sheet.get_all_records()
    except Exception:
        users_records = []

    try:
        trans_sheet = spreadsheet.worksheet("transactions")
    except Exception:
        try:
            trans_sheet = spreadsheet.worksheet("Main_User")
        except Exception:
            trans_sheet = spreadsheet.add_worksheet(title="transactions", rows="100", cols="5")
            trans_sheet.append_row(["Main_User", "Agent", "Type", "Amount", "Date"])

    try:
        trans_rows = trans_sheet.get_all_values()
        trans_data = trans_rows[1:] if len(trans_rows) > 1 else []
    except Exception:
        trans_data = []

    users_list = []
    for u in users_records:
        user_id = str(u.get("User_ID") or u.get("id") or "").strip()
        user_name = str(u.get("Name") or u.get("اسم") or "").strip()
        profile_img = str(u.get("Profile_Image") or u.get("image") or "")

        balance = 0.0
        target_name = user_name.lower()

        for row in trans_data:
            if len(row) < 4:
                continue
            t_main_user = str(row[0]).strip().lower()
            
            if target_name and (target_name == t_main_user or target_name in t_main_user or t_main_user in target_name):
                amt_str = str(row[3]).strip() if len(row) > 3 else "0"
                try:
                    val = float(amt_str.replace(",", "").strip())
                except ValueError:
                    val = 0.0
                
                t_type = str(row[2]).strip() if len(row) > 2 else ""
                if "سحب" in t_type or "(-)" in t_type:
                    balance -= val
                else:
                    balance += val

        users_list.append({
            "User_ID": user_id,
            "Name": user_name,
            "Profile_Image": profile_img,
            "Balance": balance
        })

    return render_template("admin_dashboard.html", users=users_list)

# 3. واجهة تفاصيل المستخدم الخاصة بالأدمن
@app.route("/user/<user_id>")
def user_dashboard(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    try:
        users_sheet = spreadsheet.worksheet("users")
        users_records = users_sheet.get_all_records()
    except Exception:
        return "خطأ في جلب المستخدمين", 500

    user_info = None
    for u in users_records:
        if str(u.get("User_ID") or u.get("id") or "").strip() == str(user_id).strip():
            user_info = {
                "User_ID": u.get("User_ID") or u.get("id"),
                "Name": str(u.get("Name") or u.get("اسم") or "").strip(),
                "Profile_Image": str(u.get("Profile_Image") or u.get("image") or "")
            }
            break

    if not user_info:
        return "المستخدم غير موجود", 404

    try:
        trans_sheet = spreadsheet.worksheet("transactions")
    except Exception:
        try:
            trans_sheet = spreadsheet.worksheet("Main_User")
        except Exception:
            trans_sheet = None

    user_transactions = []
    total_balance = 0.0
    target_name = user_info["Name"].lower()

    if trans_sheet:
        trans_rows = trans_sheet.get_all_values()
        trans_data = trans_rows[1:] if len(trans_rows) > 1 else []
        
        for row in trans_data:
            if len(row) < 4:
                continue
            t_main_user = str(row[0]).strip().lower()
            
            if target_name and (target_name == t_main_user or target_name in t_main_user or t_main_user in target_name):
                agent_val = str(row[1]).strip() if len(row) > 1 else ""
                t_type = str(row[2]).strip() if len(row) > 2 else ""
                amt_str = str(row[3]).strip() if len(row) > 3 else "0"
                date_val = str(row[4]).strip() if len(row) > 4 else ""

                try:
                    val = float(amt_str.replace(",", "").strip())
                except ValueError:
                    val = 0.0

                if "سحب" in t_type or "(-)" in t_type:
                    total_balance -= val
                else:
                    total_balance += val

                user_transactions.append({
                    "Agent": agent_val,
                    "Type": t_type,
                    "Amount": amt_str,
                    "Date": date_val
                })

    user_info["Balance"] = total_balance
    return render_template("user.html", user=user_info, transactions=user_transactions)

# 4. تسجيل العملية والبقاء في نفس الصفحة
@app.route("/add_transaction/<user_id>", methods=["POST"])
def add_transaction(user_id):
    try:
        agent_name = request.form.get("agent_name", "")
        trans_type = request.form.get("type", "")
        amount = request.form.get("amount", "0")

        users_sheet = spreadsheet.worksheet("users")
        users_records = users_sheet.get_all_records()
        user_name = ""

        for u in users_records:
            if str(u.get("User_ID") or u.get("id") or "").strip() == str(user_id).strip():
                user_name = str(u.get("Name") or u.get("اسم") or "").strip()
                break

        try:
            trans_sheet = spreadsheet.worksheet("transactions")
        except Exception:
            try:
                trans_sheet = spreadsheet.worksheet("Main_User")
            except Exception:
                trans_sheet = spreadsheet.add_worksheet(title="transactions", rows="100", cols="5")
                trans_sheet.append_row(["Main_User", "Agent", "Type", "Amount", "Date"])

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trans_sheet.insert_row([user_name, agent_name, trans_type, amount, current_time], 2)

        return redirect(request.referrer or url_for("admin"))
    except Exception as e:
        return f"حدث خطأ أثناء إضافة العملية: {str(e)}", 500

# 5. رفع صورة الملف الشخصي
@app.route("/upload_profile_image/<user_id>", methods=["POST"])
def upload_profile_image(user_id):
    try:
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file.filename != '':
                filename = secure_filename(file.filename)
                filename = f"user_{user_id}_{filename}"
                file.save(os.path.join(UPLOAD_FOLDER, filename))

                users_sheet = spreadsheet.worksheet("users")
                header = users_sheet.row_values(1)

                if "Profile_Image" not in header:
                    next_col = len(header) + 1
                    users_sheet.update_cell(1, next_col, "Profile_Image")
                    header = users_sheet.row_values(1)

                col_index = header.index("Profile_Image") + 1
                records = users_sheet.get_all_records()
                row_index = None

                for idx, u in enumerate(records, start=2):
                    if str(u.get("User_ID") or u.get("id") or "").strip() == str(user_id).strip():
                        row_index = idx
                        break

                if row_index:
                    users_sheet.update_cell(row_index, col_index, filename)

        return redirect(request.referrer or url_for("admin"))
    except Exception as e:
        print(f"Error saving image: {str(e)}")
        return redirect(request.referrer or url_for("admin"))

# 6. واجهة تسجيل دخول المستخدم العادي (بالـ ID فقط)
@app.route("/login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        users_sheet = spreadsheet.worksheet("users")
        users_records = users_sheet.get_all_records()
        
        found_user = None
        for u in users_records:
            if str(u.get("User_ID") or u.get("id") or "").strip() == user_id:
                found_user = u
                break
                
        if found_user:
            session["user_id"] = user_id
            session["user_name"] = str(found_user.get("Name") or found_user.get("اسم") or "")
            return redirect(url_for("my_account"))
        else:
            return render_template("login.html", error="رقم التعريف (ID) غير صحيح، يرجى التأكد.")
            
    return render_template("login.html")

# 7. حساب المستخدم العادي (عرض فقط)
@app.route("/my_account")
def my_account():
    if "user_id" not in session:
        return redirect(url_for("user_login"))
        
    user_id = session["user_id"]
    users_sheet = spreadsheet.worksheet("users")
    users_records = users_sheet.get_all_records()
    
    current_user = None
    for u in users_records:
        if str(u.get("User_ID") or u.get("id") or "").strip() == str(user_id).strip():
            current_user = {
                "User_ID": u.get("User_ID") or u.get("id"),
                "Name": str(u.get("Name") or u.get("اسم") or "").strip(),
                "Profile_Image": str(u.get("Profile_Image") or u.get("image") or "")
            }
            break

    if not current_user:
        session.pop("user_id", None)
        return redirect(url_for("user_login"))

    try:
        trans_sheet = spreadsheet.worksheet("transactions")
    except Exception:
        try:
            trans_sheet = spreadsheet.worksheet("Main_User")
        except Exception:
            trans_sheet = None

    user_transactions = []
    total_balance = 0.0
    target_name = current_user["Name"].lower()

    if trans_sheet:
        trans_rows = trans_sheet.get_all_values()
        trans_data = trans_rows[1:] if len(trans_rows) > 1 else []
        for row in trans_data:
            if len(row) < 4:
                continue
            t_main_user = str(row[0]).strip().lower()
            if target_name and (target_name == t_main_user or target_name in t_main_user or t_main_user in target_name):
                agent_val = str(row[1]).strip() if len(row) > 1 else ""
                t_type = str(row[2]).strip() if len(row) > 2 else ""
                amt_str = str(row[3]).strip() if len(row) > 3 else "0"
                date_val = str(row[4]).strip() if len(row) > 4 else ""

                try:
                    val = float(amt_str.replace(",", "").strip())
                except ValueError:
                    val = 0.0

                if "سحب" in t_type or "(-)" in t_type:
                    total_balance -= val
                else:
                    total_balance += val

                user_transactions.append({
                    "Agent": agent_val,
                    "Type": t_type,
                    "Amount": amt_str,
                    "Date": date_val
                })

    current_user["Balance"] = total_balance
    return render_template("user_view.html", user=current_user, transactions=user_transactions)

# 8. تسجيل خروج المستخدم العادي
@app.route("/user_logout")
def user_logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    return redirect(url_for("user_login"))

# 9. ملفات التثبيت (PWA)
@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")

@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js")

if __name__ == "__main__":
    app.run(debug=True)