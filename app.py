import os
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# إعداد اتصال Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
spreadsheet = client.open("Deposit App Database")

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/admin")
def admin():
    try:
        users_sheet = spreadsheet.worksheet("users")
        users = users_sheet.get_all_records()
        return render_template("admin_dashboard.html", users=users)
    except Exception as e:
        return f"خطأ في لوحة التحكم: {str(e)}", 500

@app.route("/user/<user_id>")
def user_dashboard(user_id):
    try:
        users_sheet = spreadsheet.worksheet("users")
        users = users_sheet.get_all_records()
        
        user_info = None
        for u in users:
            if str(u.get("User_ID")) == str(user_id):
                user_info = u
                break
                
        if not user_info:
            return "المستخدم غير موجود", 404

        try:
            trans_sheet = spreadsheet.worksheet("transactions")
        except:
            try:
                trans_sheet = spreadsheet.worksheet("Main_User")
            except:
                trans_sheet = spreadsheet.add_worksheet(title="transactions", rows="100", cols="5")
                trans_sheet.append_row(["Main_User", "Agent", "Type", "Amount", "Date"])

        all_transactions = trans_sheet.get_all_records()
        user_name = user_info.get("Name")
        
        user_transactions = []
        for t in all_transactions:
            if str(t.get("Main_User", "")) == str(user_name) or str(t.get("Name", "")) == str(user_name):
                user_transactions.append({
                    "Date": t.get("Date", "") or t.get("التاريخ", ""),
                    "Amount": t.get("Amount", "0") or t.get("المبلغ", "0"),
                    "Type": t.get("Type", "") or t.get("النوع", ""),
                    "Agent": t.get("perforr", "") or t.get("Agent", "") or t.get("اسم مسجل العملية", "")
                })

        return render_template("user.html", user=user_info, transactions=user_transactions)
    except Exception as e:
        return f"خطأ في حساب المستخدم: {str(e)}", 500

@app.route("/add_transaction/<user_id>", methods=["POST"])
def add_transaction(user_id):
    try:
        agent_name = request.form.get("agent_name", "المدير")
        trans_type = request.form.get("type", "إيداع")
        amount = request.form.get("amount", "0")
        
        users_sheet = spreadsheet.worksheet("users")
        users = users_sheet.get_all_records()
        user_name = ""
        for u in users:
            if str(u.get("User_ID")) == str(user_id):
                user_name = u.get("Name")
                break
                
        try:
            trans_sheet = spreadsheet.worksheet("transactions")
        except:
            try:
                trans_sheet = spreadsheet.worksheet("Main_User")
            except:
                trans_sheet = spreadsheet.add_worksheet(title="transactions", rows="100", cols="5")
                trans_sheet.append_row(["Main_User", "Agent", "Type", "Amount", "Date"])
                
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trans_sheet.append_row([user_name, agent_name, trans_type, amount, current_time])
        
        return redirect(url_for("user_dashboard", user_id=user_id))
    except Exception as e:
        return f"حدث خطأ أثناء حفظ العملية: {str(e)}", 500

@app.route("/upload_profile_image/<user_id>", methods=["POST"])
def upload_profile_image(user_id):
    try:
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file.filename != '':
                filename = secure_filename(file.filename)
                filename = f"user_{user_id}_{filename}"
                
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
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
                    if str(u.get("User_ID")) == str(user_id):
                        row_index = idx
                        break
                
                if row_index:
                    users_sheet.update_cell(row_index, col_index, filename)
    except Exception as e:
        print(f"Error saving image: {e}")
        
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(debug=True)