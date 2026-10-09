import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_google_client():
    # قراءة الاعتمادات من الملف المحلي بأمان دون وضع أي مفاتيح سرية في الكود
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return gspread.authorize(creds)

client = get_google_client()
spreadsheet = client.open("Deposit App Database")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        user_id = request.form.get("user_id")
        users_sheet = spreadsheet.worksheet("users")
        users = users_sheet.get_all_records()
        
        user_found = None
        for u in users:
            if str(u.get("User_ID")) == str(user_id):
                user_found = u
                break
                
        if user_found:
            return redirect(url_for("user_dashboard", user_id=user_id))
        else:
            flash("رقم التعرف غير موجود، يرجى التأكد والمحاولة مجدداً")
            
    return render_template("login.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if username == "admin" and password == "admin123":
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        else:
            flash("اسم المستخدم أو كلمة المرور غير صحيحة")
            
    return render_template("admin_login.html")

@app.route("/admin", methods=["GET"])
def admin():
    if "admin_logged_in" not in session:
        return redirect(url_for("admin_login"))
        
    users_sheet = spreadsheet.worksheet("users")
    transactions_sheet = spreadsheet.worksheet("transactions")
    
    users = users_sheet.get_all_records()
    transactions = transactions_sheet.get_all_records()
    
    return render_template("admin_dashboard.html", users=users, transactions=transactions)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("تم تسجيل الخروج بنجاح")
    return redirect(url_for("admin_login"))

@app.route("/update_avatar/<user_id>", methods=["POST"])
def update_avatar(user_id):
    if "avatar" in request.files:
        file = request.files["avatar"]
        if file.filename != "":
            filename = f"user_{user_id}.jpg"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
    return redirect(url_for("admin"))

@app.route("/user/<user_id>")
def user_dashboard(user_id):
    users_sheet = spreadsheet.worksheet("users")
    transactions_sheet = spreadsheet.worksheet("transactions")
    
    users = users_sheet.get_all_records()
    user_info = next((u for u in users if str(u.get("User_ID")) == str(user_id)), None)
    
    if not user_info:
        flash("المستخدم غير موجود")
        return redirect(url_for("index"))
        
    all_transactions = transactions_sheet.get_all_records()
    user_name = user_info.get("Name")
    
    user_transactions = [
        t for t in all_transactions 
        if str(t.get("Main_User")) == str(user_name) or str(t.get("Main_User")) == str(user_id)
    ]
    
    return render_template("user.html", user=user_info, transactions=user_transactions)

if __name__ == "__main__":
    app.run(debug=True, port=5000)