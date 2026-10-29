import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key_123")

# رابط الاتصال بقاعدة بيانات MySQL
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "mysql+pymysql://root:password@localhost/deposit_app")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# دالة لتحديد التوقيت المحلي (توقيت العراق UTC+3)
def get_local_time():
    return datetime.utcnow() + timedelta(hours=3)

# ----------------- نماذج قاعدة البيانات (MySQL Models) -----------------

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False, default='') # كلمة المرور المشفرة
    role = db.Column(db.String(20), nullable=False, default='user')  # 'admin' (مدير), 'staff' (مسؤول), 'user' (مستخدم)
    profile_image = db.Column(db.String(255), default='')
    # ترتيب العمليات تنازلياً (الأحدث أولاً) تلقائياً
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade="all, delete-orphan", order_by="Transaction.date.desc()")

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_name = db.Column(db.String(100), nullable=False)
    trans_type = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=get_local_time)

# نموذج رأس المال الجديد
class Capital(db.Model):
    __tablename__ = 'capital'
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(255), default='رأس المال الأساسي')
    date = db.Column(db.DateTime, default=get_local_time)

# إنشاء الجداول تلقائياً وإنشاء مدير افتراضي عند عدم وجوده
with app.app_context():
    db.create_all()
    
    # إضافة الأعمدة تلقائياً إذا كانت مفقودة في قاعدة البيانات القديمة
    try:
        db.session.execute(db.text("ALTER TABLE users ADD COLUMN password VARCHAR(200) NOT NULL DEFAULT '';"))
        db.session.commit()
    except Exception:
        db.session.rollback()
        
    try:
        db.session.execute(db.text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user';"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    # التحقق من وجود مدير أساسي، وإذا لم يوجد يتم إنشاؤه تلقائياً
    admin_exists = User.query.filter_by(role='admin').first()
    if not admin_exists:
        default_admin = User(
            user_id="admin",
            name="المدير العام",
            password=generate_password_hash("admin123"),
            role="admin"
        )
        db.session.add(default_admin)
        db.session.commit()

# ----------------- المسارات والدوال -----------------

# --- مسار الصفحة الرئيسية Redirect ---
@app.route("/")
def home():
    return redirect(url_for("user_login"))

# --- 1. دخول المستخدم العادي (ID فقط) ---
@app.route("/login", methods=["GET", "POST"], endpoint="user_login")
def user_login():
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        u = User.query.filter_by(user_id=user_id).first()
        
        if u and u.role == "user":
            session["user_db_id"] = u.id
            session["user_id"] = u.user_id
            session["user_name"] = u.name
            session["role"] = u.role
            return redirect(url_for("my_account"))
        else:
            return render_template("login.html", error="معرف الحساب غير موجود أو غير مخصص للمستخدمين")
            
    return render_template("login.html")

# --- 2. دخول المسؤول والموظف (ID + Password) ---
@app.route("/admin/login", methods=["GET", "POST"], endpoint="admin_login")
def admin_login():
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        password = request.form.get("password", "").strip()
        
        u = User.query.filter_by(user_id=user_id).first()
        
        if u and check_password_hash(u.password, password) and u.role in ["admin", "staff"]:
            session["user_db_id"] = u.id
            session["user_id"] = u.user_id
            session["user_name"] = u.name
            session["role"] = u.role
            
            if u.role == "admin":
                return redirect(url_for("admin"))
            else:
                return redirect(url_for("staff_dashboard"))
        else:
            return render_template("admin_login.html", error="معرف الحساب أو كلمة المرور غير صحيحة")
            
    return render_template("admin_login.html")

@app.route("/logout")
def logout():
    session.clear()
    role = session.get("role")
    if role in ["admin", "staff"]:
        return redirect(url_for("admin_login"))
    return redirect(url_for("user_login"))

# دالة مساعدة لجلب وعمل حسابات المستخدمين من MySQL
def get_processed_users():
    users = User.query.filter_by(role='user').all()
    users_list = []
    for u in users:
        balance = 0.0
        for t in u.transactions:
            if "سحب" in t.trans_type or "(-)" in t.trans_type:
                balance -= t.amount
            else:
                balance += t.amount

        users_list.append({
            "DB_ID": u.id,
            "User_ID": u.user_id,
            "Name": u.name,
            "Profile_Image": u.profile_image,
            "Balance": balance
        })
    return users_list

# ----------------- 3. لوحة تحكم المدير (Admin Dashboard) -----------------
@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))
    
    filter_type = request.args.get("filter", "all")
    all_users_list = get_processed_users()
    
    # تصفية المستخدمين بناءً على الفلتر المطلوب
    if filter_type == "debts":
        users_list = [u for u in all_users_list if u['Balance'] < 0]
    elif filter_type == "positive":
        users_list = [u for u in all_users_list if u['Balance'] > 0]
    else:
        users_list = all_users_list
    
    total_debts = sum(u['Balance'] for u in all_users_list if u['Balance'] < 0)
    total_positive_balances = sum(u['Balance'] for u in all_users_list if u['Balance'] > 0)
    
    # حساب الفرق الإجمالي بين الأرصدة الموجبة والسالبة فقط
    net_balance = total_positive_balances + total_debts
    
    # رأس المال الأساسي المضاف من القاعدة
    base_capital = db.session.query(db.func.sum(Capital.amount)).scalar() or 0.0
    
    # إجمالي رأس المال مضافاً إليه الفرق الإجمالي
    total_capital = base_capital + net_balance

    return render_template(
        "admin_dashboard.html", 
        users=users_list, 
        total_debts=total_debts,
        total_positive_balances=total_positive_balances,
        net_balance=net_balance,
        total_capital=total_capital,
        current_filter=filter_type
    )

@app.route("/admin/debts", endpoint="admin_debts")
def admin_debts():
    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))
    return redirect(url_for("admin", filter="debts"))

# مسار إضافة وتعديل رأس المال الجديد (للمدير فقط)
@app.route("/admin/add_capital", methods=["POST"])
def add_capital():
    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))
        
    amt_str = request.form.get("capital_amount", "0").replace(",", "").strip()
    note = request.form.get("capital_note", "رأس المال الأساسي").strip()
    
    try:
        amount = float(amt_str)
    except ValueError:
        amount = 0.0
        
    if amount != 0:
        new_capital = Capital(amount=amount, note=note)
        db.session.add(new_capital)
        db.session.commit()
        
    return redirect(url_for("admin"))

# 3.1 إضافة مستخدم جديد (متاح للمدير فقط)
@app.route("/admin/add_user", methods=["GET", "POST"])
def add_user():
    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))
        
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "user")
        
        if User.query.filter_by(user_id=user_id).first():
            return render_template("add_user.html", error="رقم التعريف مستخدم مسبقاً.")
        
        if user_id and name and password:
            hashed_password = generate_password_hash(password)
            new_user = User(
                user_id=user_id,
                name=name,
                password=hashed_password,
                role=role
            )
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for("admin"))
            
    return render_template("add_user.html")

# 3.2 حذف مستخدم (للمدير فقط)
@app.route("/admin/delete_user/<int:id>")
def delete_user(id):
    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))
        
    u = User.query.get_or_404(id)
    if u.role != "admin":
        db.session.delete(u)
        db.session.commit()
        
    return redirect(url_for("admin"))

# ----------------- 4. لوحة تحكم المسؤول / الموظف (Staff Dashboard) -----------------
@app.route("/staff")
def staff_dashboard():
    # السماح للمدير أو المسؤول بالدخول هنا
    if session.get("role") not in ["admin", "staff"]:
        return redirect(url_for("admin_login"))
        
    users_list = get_processed_users()
    transactions = Transaction.query.order_by(Transaction.date.desc()).all()
    
    formatted_transactions = []
    for t in transactions:
        user_obj = User.query.get(t.user_id)
        formatted_transactions.append({
            "ID": t.id,
            "User_Name": user_obj.name if user_obj else "حذف",
            "User_ID": user_obj.user_id if user_obj else "",
            "Agent": t.agent_name,
            "Type": t.trans_type,
            "Amount": f"{t.amount:,.0f}",
            "Date": t.date.strftime("%Y-%m-%d %H:%M:%S")
        })

    return render_template("staff_dashboard.html", users=users_list, transactions=formatted_transactions)

# ----------------- 5. إدارة العمليات (تسجيل، حذف) -----------------
@app.route("/add_transaction/<user_id>", methods=["POST"])
def add_transaction(user_id):
    if session.get("role") not in ["admin", "staff"]:
        return redirect(url_for("admin_login"))

    u = User.query.filter_by(user_id=str(user_id).strip()).first()
    if u:
        agent_name = request.form.get("agent_name", "").strip()
        if not agent_name:
            agent_name = session.get("user_name", "المسؤول")
            
        trans_type = request.form.get("type", "")
        
        amt_str = request.form.get("amount", "").strip()
        if not amt_str:
            amt_str = request.form.get("formatted_amount", "0")
        amt_str = amt_str.replace(",", "").strip()
        
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

    return redirect(request.referrer or url_for("staff_dashboard" if session.get("role") == "staff" else "admin"))

@app.route("/transaction/delete/<int:index>")
def delete_transaction(index):
    if session.get("role") not in ["admin", "staff"]:
        return redirect(url_for("admin_login"))

    trans = Transaction.query.get(index)
    if trans:
        db.session.delete(trans)
        db.session.commit()

    return redirect(request.referrer or url_for("staff_dashboard" if session.get("role") == "staff" else "admin"))

# ----------------- 6. واجهة تفاصيل المستخدم الخاصة بالأدمن / المسؤول -----------------
@app.route("/user/<user_id>", methods=["GET", "POST"])
def user_dashboard(user_id):
    if session.get("role") not in ["admin", "staff"]:
        return redirect(url_for("admin_login"))
        
    u = User.query.filter_by(user_id=str(user_id).strip()).first()
    if not u:
        return "المستخدم غير موجود", 404

    total_balance = 0.0
    user_transactions = []
    
    for t in u.transactions:
        if "سحب" in str(t.trans_type) or "(-)" in str(t.trans_type):
            total_balance -= float(t.amount or 0)
        else:
            total_balance += float(t.amount or 0)
            
        user_transactions.append({
            "Row_Index": t.id,
            "Agent": t.agent_name if t.agent_name else "المدير العام",
            "Type": t.trans_type,
            "Amount": float(t.amount or 0),
            "Date": t.date.strftime("%Y-%m-%d %H:%M:%S") if t.date else ""
        })

    user_info = {
        "User_ID": u.user_id,
        "Name": u.name,
        "Profile_Image": u.profile_image,
        "Balance": total_balance
    }

    return render_template("user.html", user=user_info, transactions=user_transactions)

# ----------------- 7. حساب المستخدم العادي (User View) -----------------
@app.route("/my_account")
def my_account():
    if session.get("role") != "user":
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

# ----------------- 8. رفع صورة الملف الشخصي -----------------
@app.route("/upload_profile_image/<user_id>", methods=["POST"])
def upload_profile_image(user_id):
    if session.get("role") not in ["admin", "staff"]:
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

# ----------------- 9. ملفات التثبيت (PWA) -----------------
@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")

@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js")

if __name__ == "__main__":
    app.run(debug=True)