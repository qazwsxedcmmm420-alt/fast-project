import os
from datetime import datetime
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

# ----------------- نماذج قاعدة البيانات (MySQL Models) -----------------

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False, default='') # كلمة المرور المشفرة
    role = db.Column(db.String(20), nullable=False, default='user')  # 'admin' (مدير), 'staff' (مسؤول), 'user' (مستخدم)
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

@app.route("/")
def home():
    # توجيه افتراضي لصفحة تسجيل الدخول الموحدة
    return redirect(url_for("login"))

# ----------------- 1. نظام تسجيل الدخول الموحد -----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        password = request.form.get("password", "").strip()
        
        # استعلام عن المستخدم أو المدير أو المسؤول
        u = User.query.filter_by(user_id=user_id).first()
        
        if u and check_password_hash(u.password, password):
            session["user_db_id"] = u.id
            session["user_id"] = u.user_id
            session["user_name"] = u.name
            session["role"] = u.role
            
            # التوجيه بناءً على الصلاحية (Role)
            if u.role == "admin":
                return redirect(url_for("admin"))
            elif u.role == "staff":
                return redirect(url_for("staff_dashboard"))
            else:
                return redirect(url_for("my_account"))
        else:
            return render_template("login.html", error="رقم التعريف أو كلمة المرور غير صحيحة")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# دالة مساعدة لجلب وعمل حسابات المستخدمين من MySQL
def get_processed_users():
    users = User.query.filter_by(role='user').all() # جلب المستخدمين العاديين فقط للحسابات
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

# ----------------- 2. لوحة تحكم المدير (Admin Dashboard) -----------------
@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    
    users_list = get_processed_users()
    all_users_count = User.query.count()
    
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

# 2.1 إضافة مستخدم جديد (متاح للمدير فقط)
@app.route("/admin/add_user", methods=["GET", "POST"])
def add_user():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
        
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "user") # user, staff, admin
        
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

# 2.2 حذف مستخدم (للمدير فقط)
@app.route("/admin/delete_user/<int:id>")
def delete_user(id):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
        
    u = User.query.get_or_404(id)
    if u.role != "admin": # منع حذف المدير الأساسي عن طريق الخطأ
        db.session.delete(u)
        db.session.commit()
        
    return redirect(url_for("admin"))

# ----------------- 3. لوحة تحكم المسؤول / الموظف (Staff Dashboard) -----------------
@app.route("/staff")
def staff_dashboard():
    if session.get("role") not in ["admin", "staff"]:
        return redirect(url_for("login"))
        
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

# ----------------- 4. إدارة العمليات (تسجيل، تعديل، حذف) -----------------
@app.route("/add_transaction/<user_id>", methods=["POST"])
def add_transaction(user_id):
    # متاح للمدير والمسؤول
    if session.get("role") not in ["admin", "staff"]:
        return redirect(url_for("login"))

    u = User.query.filter_by(user_id=str(user_id).strip()).first()
    if u:
        agent_name = session.get("user_name", "المسؤول")
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

# حذف عملية محددة (للمدير والمسؤول)
@app.route("/transaction/delete/<int:index>")
def delete_transaction(index):
    if session.get("role") not in ["admin", "staff"]:
        return redirect(url_for("login"))

    trans = Transaction.query.get(index)
    if trans:
        db.session.delete(trans)
        db.session.commit()

    return redirect(request.referrer or url_for("admin"))

# ----------------- 5. واجهة تفاصيل المستخدم الخاصة بالأدمن / المسؤول -----------------
@app.route("/user/<user_id>")
def user_dashboard(user_id):
    if session.get("role") not in ["admin", "staff"]:
        return redirect(url_for("login"))

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
            "Row_Index": t.id,
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

# ----------------- 6. حساب المستخدم العادي (User View) -----------------
@app.route("/my_account")
def my_account():
    if session.get("role") != "user":
        return redirect(url_for("login"))
        
    user_id = str(session["user_id"]).strip()
    u = User.query.filter_by(user_id=user_id).first()

    if not u:
        session.clear()
        return redirect(url_for("login"))

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

# ----------------- 7. رفع صورة الملف الشخصي -----------------
@app.route("/upload_profile_image/<user_id>", methods=["POST"])
def upload_profile_image(user_id):
    if session.get("role") not in ["admin", "staff"]:
        return redirect(url_for("login"))

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

# ----------------- 8. ملفات التثبيت (PWA) -----------------
@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")

@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js")

if __name__ == "__main__":
    app.run(debug=True)