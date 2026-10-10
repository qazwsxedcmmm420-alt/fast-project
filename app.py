import os
import json
from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# إعداد الاتصال بـ Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

creds_json_str = os.environ.get("GOOGLE_CREDENTIALS_JSON")
if creds_json_str:
    creds_dict = json.loads(creds_json_str)
    print("CURRENT SERVICE ACCOUNT EMAIL:", creds_dict.get("client_email"))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
else:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

client = gspread.authorize(creds)
spreadsheet = client.open("Deposit App Database")

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/")
def home():
    return redirect(url_for("admin"))


@app.route("/admin")
def admin():
    try:
        users_sheet = spreadsheet.worksheet("users")
        users_records = users_sheet.get_all_records()

        try:
            trans_sheet = spreadsheet.worksheet("transactions")
        except Exception:
            try:
                trans_sheet = spreadsheet.worksheet("Main_User")
            except Exception:
                trans_sheet = spreadsheet.add_worksheet(title="transactions", rows="100", cols="5")
                trans_sheet.append_row(["Main_User", "Agent", "Type", "Amount", "Date"])

        all_transactions = trans_sheet.get_all_records()
        users_list = []

        for u in users_records:
            user_id = str(u.get("User_ID") or u.get("id") or "")
            user_name = str(u.get("Name") or u.get("اسم") or "").strip()
            profile_img = str(u.get("Profile_Image") or u.get("image") or "")

            balance = 0.0
            target_name = user_name.lower()

            for t in all_transactions:
                t_main_user = str(t.get("Main_User") or t.get("Name") or t.get("اسم المستخدم") or "").strip().lower()

                if t_main_user == target_name or target_name in t_main_user or t_main_user in target_name:
                    amt_str = str(t.get("Amount", "0") or t.get("المبلغ", "0"))
                    try:
                        val = float(amt_str.replace(',', '').strip())
                    except ValueError:
                        val = 0.0

                    t_type = str(t.get("Type", "") or t.get("النوع", ""))
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

    except Exception as e:
        return f"خطأ في لوحة التحكم: {str(e)}", 500


@app.route("/admin_logout")
def admin_logout():
    return redirect(url_for("admin"))


@app.route("/user/<user_id>")
def user_dashboard(user_id):
    try:
        users_sheet = spreadsheet.worksheet("users")
        users_records = users_sheet.get_all_records()

        user_info = None
        for u in users_records:
            if str(u.get("User_ID") or u.get("id") or "") == str(user_id):
                user_info = {
                    "User_ID": str(u.get("User_ID") or u.get("id") or ""),
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
                trans_sheet = spreadsheet.add_worksheet(title="transactions", rows="100", cols="5")
                trans_sheet.append_row(["Main_User", "Agent", "Type", "Amount", "Date"])

        all_transactions = trans_sheet.get_all_records()
        user_transactions = []
        total_balance = 0.0

        target_name = user_info["Name"].lower()

        for t in all_transactions:
            t_main_user = str(t.get("Main_User") or t.get("Name") or t.get("اسم المستخدم") or "").strip().lower()

            if t_main_user == target_name or target_name in t_main_user or t_main_user in target_name:
                amt_str = str(t.get("Amount", "0") or t.get("المبلغ", "0"))
                try:
                    val = float(amt_str.replace(',', '').strip())
                except ValueError:
                    val = 0.0

                t_type = str(t.get("Type", "") or t.get("النوع", ""))
                if "سحب" in t_type or "(-)" in t_type:
                    total_balance -= val
                else:
                    total_balance += val

                user_transactions.append({
                    "Date": str(t.get("Date", "") or t.get("التاريخ", "")),
                    "Amount": amt_str,
                    "Type": t_type,
                    "Agent": str(t.get("Agent", "") or t.get("perforr", "") or t.get("اسم مسجل العملية", ""))
                })

        user_info["Balance"] = total_balance
        return render_template("user.html", user=user_info, transactions=user_transactions)

    except Exception as e:
        return f"خطأ في حساب المستخدم: {str(e)}", 500


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
            if str(u.get("User_ID") or u.get("id") or "") == str(user_id):
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
        trans_sheet.append_row([user_name, agent_name, trans_type, amount, current_time])

        return redirect(url_for("user_dashboard", user_id=user_id))
    except Exception as e:
        return f"حدث خطأ أثناء إضافة العملية: {str(e)}", 500


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
                    if str(u.get("User_ID") or u.get("id") or "") == str(user_id):
                        row_index = idx
                        break

                if row_index:
                    users_sheet.update_cell(row_index, col_index, filename)

        return redirect(url_for("user_dashboard", user_id=user_id))
    except Exception as e:
        print(f"Error saving image: {str(e)}")
        return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True)