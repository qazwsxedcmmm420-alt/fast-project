import os
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key_123")

# رابط الاتصال بقاعدة بيانات MySQL
# يقرأ الرابط تلقائياً من متغيرة البيئة DATABASE_URL في Render
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "mysql+pymysql://root:password@localhost/deposit_app")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ----------------- نماذج قاعدة البيانات (MySQL Models) -----------------

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    profile_image = db.Column(db.String(255), default='')
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade="all, delete-orphan")

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_name = db.Column(db.String(100), nullable=False)
    trans_type = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)

# إنشاء الجداول تلقائياً في MySQL عند بدء التشغيل
with app.app_context():
    db.create_all()

# ----------------- المسارات والدوال -----------------

@app.route("/")
def home():
    return redirect(url_for("admin"))

# 1. تسجيل دخول وخروج المسؤول (Admin Login / Logout)
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "") or request.form.get("admin_password", "")
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

# دالة مساعدة لجلب وعمل حسابات المستخدمين من MySQL
def get_processed_users():
    users = User.query.all()
    users_list = []
    for u in users:
        balance = 0.0
        for t in u.transactions:
            if "سحب" in t.trans_type or "(-)" in t.trans_type:
                balance -= t.amount
            else:
                balance += t.amount

        users_list.append({
            "User_ID": u.user_id,
            "Name": u.name,
            "Profile_Image": u.profile_image,
            "Balance": balance
        })
    return users_list

# 2. لوحة تحكم المسؤول (عرض كل المستخدمين والإحصائيات)
@app.route("/admin")
def admin():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    
    users_list = get_processed_users()
    
    total_debts = sum(u['Balance'] for u in users_list if u['Balance'] < 0)
    total_positive_balances = sum(u['Balance'] for u in users_list if u['Balance'] > 0)
    net_balance = total_positive_balances + total_debts

    return render_template(
        "admin_dashboard.html", 
        users=users_list, 
        total_debts=total_debts,
        total_positive_balances=total_positive_balances,
        net_balance=net_balance
    )

# 2.1 مسار عرض الديون فقط (الأرصدة السالبة)
@app.route("/admin/debts")
def admin_debts():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    
    users_list = get_processed_users()
    total_debts = sum(u['Balance'] for u in users_list if u['Balance'] < 0)
    total_positive_balances = sum(u['Balance'] for u in users_list if u['Balance'] > 0)
    net_balance = total_positive_balances + total_debts

    debt_users = [u for u in users_list if u['Balance'] < 0]

    return render_template(
        "admin_dashboard.html", 
        users=debt_users, 
        total_debts=total_debts,
        total_positive_balances=total_positive_balances,
        net_balance=net_balance
    )

# 2.2 مسار عرض الأرصدة الموجبة فقط
@app.route("/admin/positive")
def admin_positive():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    
    users_list = get_processed_users()
    total_debts = sum(u['Balance'] for u in users_list if u['Balance'] < 0)
    total_positive_balances = sum(u['Balance'] for u in users_list if u['Balance'] > 0)
    net_balance = total_positive_balances + total_debts

    positive_users = [u for u in users_list if u['Balance'] > 0]

    return render_template(
        "admin_dashboard.html", 
        users=positive_users, 
        total_debts=total_debts,
        total_positive_balances=total_positive_balances,
        net_balance=net_balance
    )

# 3. واجهة تفاصيل المستخدم الخاصة بالأدمن
@app.route("/user/<user_id>")
def user_dashboard(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    u = User.query.filter_by(user_id=str(user_id).strip()).first()
    if not u:
        return "المستخدم غير موجود", 404

    total_balance = 0.0
    user_transactions = []

    for t in u.transactions:
        if "سحب" in t.trans_type or "(-)" in t.trans_type:
            total_balance -= t.amount
        else:
            total_balance += t.amount

        user_transactions.append({
            "Row_Index": t.id,  # الـ ID الفريد للعملية في MySQL
            "Agent": t.agent_name,
            "Type": t.trans_type,
            "Amount": f"{t.amount:,.0f}",
            "Date": t.date.strftime("%Y-%m-%d %H:%M:%S")
        })

    user_info = {
        "User_ID": u.user_id,
        "Name": u.name,
        "Profile_Image": u.profile_image,
        "Balance": total_balance
    }

    return render_template("user.html", user=user_info, transactions=user_transactions)

# 4. تسجيل عملية جديدة
@app.route("/add_transaction/<user_id>", methods=["POST"])
def add_transaction(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    u = User.query.filter_by(user_id=str(user_id).strip()).first()
    if u:
        agent_name = request.form.get("agent_name", "")
        trans_type = request.form.get("type", "")
        amt_str = request.form.get("amount", "0").replace(",", "").strip()
        
        try:
            amount = float(amt_str)
        except ValueError:
            amount = 0.0

        new_trans = Transaction(
            user_id=u.id, 
            agent_name=agent_name, 
            trans_type=trans_type, 
            amount=amount
        )
        db.session.add(new_trans)
        db.session.commit()

    return redirect(request.referrer or url_for("admin"))

# 4.1 حذف عملية محددة برقم الـ ID من MySQL
@app.route("/user/<user_id>/delete_transaction/<int:index>")
def delete_transaction(user_id, index):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    trans = Transaction.query.get(index)
    if trans:
        db.session.delete(trans)
        db.session.commit()

    return redirect(url_for("user_dashboard", user_id=user_id))

# 4.2 تعديل عملية محددة
@app.route("/user/<user_id>/edit_transaction/<int:index>")
def edit_transaction(user_id, index):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    return redirect(url_for("user_dashboard", user_id=user_id))

# 5. رفع صورة الملف الشخصي
@app.route("/upload_profile_image/<user_id>", methods=["POST"])
def upload_profile_image(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    u = User.query.filter_by(user_id=str(user_id).strip()).first()
    if u and 'profile_image' in request.files:
        file = request.files['profile_image']
        if file.filename != '':
            filename = secure_filename(file.filename)
            filename = f"user_{user_id}_{filename}"
            file.save(os.path.join(UPLOAD_FOLDER, filename))

            u.profile_image = filename
            db.session.commit()

    return redirect(request.referrer or url_for("admin"))

# 6. واجهة تسجيل دخول المستخدم العادي
@app.route("/login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        u = User.query.filter_by(user_id=user_id).first()
        
        if u:
            session["user_id"] = user_id
            session["user_name"] = u.name
            return redirect(url_for("my_account"))
        else:
            return render_template("login.html", error="رقم التعريف (ID) غير صحيح، يرجى التأكد.")
            
    return render_template("login.html")

# 7. حساب المستخدم العادي
@app.route("/my_account")
def my_account():
    if "user_id" not in session:
        return redirect(url_for("user_login"))
        
    user_id = str(session["user_id"]).strip()
    u = User.query.filter_by(user_id=user_id).first()

    if not u:
        session.clear()
        return redirect(url_for("user_login"))

    total_balance = 0.0
    user_transactions = []

    for t in u.transactions:
        if "سحب" in t.trans_type or "(-)" in t.trans_type:
            total_balance -= t.amount
        else:
            total_balance += t.amount

        user_transactions.append({
            "Agent": t.agent_name,
            "Type": t.trans_type,
            "Amount": f"{t.amount:,.0f}",
            "Date": t.date.strftime("%Y-%m-%d %H:%M:%S")
        })

    current_user = {
        "User_ID": u.user_id,
        "Name": u.name,
        "Profile_Image": u.profile_image,
        "Balance": total_balance
    }

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