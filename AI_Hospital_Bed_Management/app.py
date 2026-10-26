import os
import csv
import io
import math
import random
from datetime import datetime, date, timedelta
from functools import wraps

import numpy as np
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "development-only-change-before-deployment")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "instance", "hospital.db").replace("\\", "/")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff")


class Ward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)


class Bed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bed_number = db.Column(db.String(20), unique=True, nullable=False)
    ward_id = db.Column(db.Integer, db.ForeignKey("ward.id"), nullable=False)
    bed_type = db.Column(db.String(30), nullable=False, default="Standard")
    status = db.Column(db.String(20), nullable=False, default="Available")
    ward = db.relationship("Ward", backref="beds")


class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_code = db.Column(db.String(30), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    sex = db.Column(db.String(20), nullable=False, default="Not specified")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Admission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    bed_id = db.Column(db.Integer, db.ForeignKey("bed.id"), nullable=False)
    admitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    discharged_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Active")
    patient = db.relationship("Patient", backref="admissions")
    bed = db.relationship("Bed", backref="admissions")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    """Restrict user administration to signed-in admin accounts."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Only administrators can manage user accounts.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {"now_date": date.today().strftime("%a, %d %b %Y")}


def get_active_admission(bed_id):
    return Admission.query.filter_by(bed_id=bed_id, status="Active").first()


def build_forecast():
    """Train a demo Random Forest on synthetic history; not for real clinical use."""
    total = Bed.query.count()
    if total <= 0:
        return [], {"mae": None, "source": "No beds configured"}
    rng = np.random.default_rng(42)
    days = 365
    start = date.today() - timedelta(days=days)
    records = []
    baseline_capacity = max(1, total)
    for i in range(days):
        d = start + timedelta(days=i)
        weekly = 0.06 * math.sin(2 * math.pi * d.weekday() / 7)
        yearly = 0.07 * math.sin(2 * math.pi * i / 365)
        trend = 0.00015 * i
        noise = float(rng.normal(0, 0.035))
        occupancy_ratio = float(np.clip(0.62 + weekly + yearly + trend + noise, 0.25, 0.97))
        records.append({
            "day_index": i,
            "weekday": d.weekday(),
            "month": d.month,
            "day_of_year": d.timetuple().tm_yday,
            "occupied": round(occupancy_ratio * baseline_capacity)
        })
    frame = pd.DataFrame(records)
    features = ["day_index", "weekday", "month", "day_of_year"]
    X = frame[features]
    y = frame["occupied"]
    model = RandomForestRegressor(n_estimators=100, random_state=42, min_samples_leaf=3)
    model.fit(X, y)
    train_pred = model.predict(X)
    mae = round(float(mean_absolute_error(y, train_pred)), 2)
    future = []
    current_index = days
    for step in range(1, 8):
        d = date.today() + timedelta(days=step)
        row = pd.DataFrame([{
            "day_index": current_index + step - 1,
            "weekday": d.weekday(),
            "month": d.month,
            "day_of_year": d.timetuple().tm_yday
        }])
        prediction = int(round(float(model.predict(row[features])[0])))
        prediction = min(total, max(0, prediction))
        future.append({
            "day": d.strftime("%a, %d %b"),
            "beds": prediction,
            "rate": round(prediction * 100 / total, 1)
        })
    return future, {"mae": mae, "source": "Synthetic demonstration data", "training_days": days}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    """Admin-only account creation and user directory."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "staff").strip().lower()
        allowed_roles = {"admin", "doctor", "staff"}

        if len(username) < 3 or len(username) > 80:
            flash("Username must be between 3 and 80 characters.", "danger")
        elif any(ch.isspace() for ch in username):
            flash("Username cannot contain spaces.", "danger")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
        elif role not in allowed_roles:
            flash("Choose a valid role.", "danger")
        elif User.query.filter_by(username=username).first():
            flash("That username already exists. Choose another one.", "danger")
        else:
            db.session.add(User(
                username=username,
                password_hash=generate_password_hash(password),
                role=role
            ))
            db.session.commit()
            flash(f"Account for {username} created successfully.", "success")
            return redirect(url_for("users"))

    all_users = User.query.order_by(User.role, User.username).all()
    return render_template("users.html", users=all_users)


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    target = db.get_or_404(User, user_id)
    if target.id == session.get("user_id"):
        flash("You cannot delete the account you are currently using.", "warning")
    elif target.role == "admin" and User.query.filter_by(role="admin").count() <= 1:
        flash("The last administrator account cannot be deleted.", "warning")
    else:
        db.session.delete(target)
        db.session.commit()
        flash(f"Account {target.username} deleted.", "success")
    return redirect(url_for("users"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    total = Bed.query.count()
    available = Bed.query.filter_by(status="Available").count()
    occupied = Bed.query.filter_by(status="Occupied").count()
    maintenance = Bed.query.filter_by(status="Maintenance").count()
    patients_count = Patient.query.count()
    active_count = Admission.query.filter_by(status="Active").count()
    occupancy = round(occupied * 100 / total, 1) if total else 0
    recent = Admission.query.order_by(Admission.admitted_at.desc()).limit(6).all()
    ward_stats = []
    for ward in Ward.query.order_by(Ward.name).all():
        count = len(ward.beds)
        used = sum(1 for bed in ward.beds if bed.status == "Occupied")
        ward_stats.append({"name": ward.name, "total": count, "occupied": used,
                           "rate": round(used * 100 / count, 1) if count else 0})
    return render_template("dashboard.html", total=total, available=available, occupied=occupied,
                           maintenance=maintenance, patients=patients_count,
                           active_admissions=active_count, occupancy=occupancy,
                           recent=recent, ward_stats=ward_stats)


@app.route("/beds", methods=["GET", "POST"])
@login_required
def beds():
    if request.method == "POST":
        number = request.form.get("bed_number", "").strip().upper()
        ward_id = request.form.get("ward_id", type=int)
        bed_type = request.form.get("bed_type", "Standard")
        if not number or not ward_id:
            flash("Please enter a bed number and select a ward.", "danger")
        elif Bed.query.filter_by(bed_number=number).first():
            flash("That bed number already exists.", "danger")
        else:
            db.session.add(Bed(bed_number=number, ward_id=ward_id, bed_type=bed_type))
            db.session.commit()
            flash("Bed added successfully.", "success")
        return redirect(url_for("beds"))
    search = request.args.get("q", "").strip()
    query = Bed.query.join(Ward)
    if search:
        query = query.filter(db.or_(Bed.bed_number.ilike(f"%{search}%"), Ward.name.ilike(f"%{search}%")))
    return render_template("beds.html", beds=query.order_by(Ward.name, Bed.bed_number).all(),
                           wards=Ward.query.order_by(Ward.name).all())


@app.route("/beds/<int:bed_id>/status", methods=["POST"])
@login_required
def bed_status(bed_id):
    bed = db.get_or_404(Bed, bed_id)
    new_status = request.form.get("status")
    if new_status not in {"Available", "Maintenance"}:
        flash("Invalid status change.", "danger")
    elif get_active_admission(bed.id):
        flash("This bed has an active admission. Discharge the patient first.", "warning")
    else:
        bed.status = new_status
        db.session.commit()
        flash(f"Bed {bed.bed_number} updated.", "success")
    return redirect(url_for("beds"))


@app.route("/patients", methods=["GET", "POST"])
@login_required
def patients():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        age = request.form.get("age", type=int)
        sex = request.form.get("sex", "Not specified")
        if not name or age is None or age < 0 or age > 120:
            flash("Enter a valid patient name and age (0–120).", "danger")
        else:
            patient = Patient(
                patient_code=f"P{datetime.utcnow().strftime('%y%m%d%H%M%S%f')}",
                full_name=name, age=age, sex=sex
            )
            db.session.add(patient)
            db.session.commit()
            flash(f"Patient registered. Patient ID: {patient.patient_code}", "success")
        return redirect(url_for("patients"))
    search = request.args.get("q", "").strip()
    query = Patient.query
    if search:
        query = query.filter(db.or_(Patient.full_name.ilike(f"%{search}%"), Patient.patient_code.ilike(f"%{search}%")))
    return render_template("patients.html", patients=query.order_by(Patient.created_at.desc()).all())


@app.route("/admissions", methods=["GET", "POST"])
@login_required
def admissions():
    if request.method == "POST":
        patient_id = request.form.get("patient_id", type=int)
        bed_id = request.form.get("bed_id", type=int)
        patient = db.session.get(Patient, patient_id) if patient_id else None
        bed = db.session.get(Bed, bed_id) if bed_id else None
        if not patient or not bed:
            flash("Choose a valid patient and bed.", "danger")
        elif bed.status != "Available" or get_active_admission(bed.id):
            flash("That bed is not available. Please choose another bed.", "danger")
        elif Admission.query.filter_by(patient_id=patient.id, status="Active").first():
            flash("This patient already has an active admission.", "warning")
        else:
            db.session.add(Admission(patient_id=patient.id, bed_id=bed.id))
            bed.status = "Occupied"
            db.session.commit()
            flash(f"{patient.full_name} admitted to bed {bed.bed_number}.", "success")
        return redirect(url_for("admissions"))
    active = Admission.query.filter_by(status="Active").order_by(Admission.admitted_at.desc()).all()
    history = Admission.query.filter_by(status="Discharged").order_by(Admission.discharged_at.desc()).limit(50).all()
    return render_template("admissions.html", active=active, history=history,
                           patients=Patient.query.order_by(Patient.full_name).all(),
                           beds=Bed.query.filter_by(status="Available").order_by(Bed.bed_number).all())


@app.route("/admissions/<int:admission_id>/discharge", methods=["POST"])
@login_required
def discharge(admission_id):
    admission = db.get_or_404(Admission, admission_id)
    if admission.status != "Active":
        flash("This admission is already discharged.", "warning")
    else:
        admission.status = "Discharged"
        admission.discharged_at = datetime.utcnow()
        admission.bed.status = "Available"
        db.session.commit()
        flash(f"{admission.patient.full_name} discharged; bed is available.", "success")
    return redirect(url_for("admissions"))


@app.route("/predictions")
@login_required
def predictions():
    total = Bed.query.count()
    occupied = Bed.query.filter_by(status="Occupied").count()
    forecast, metrics = build_forecast()
    return render_template("predictions.html", total=total, occupied=occupied,
                           occupancy=round(occupied * 100 / total, 1) if total else 0,
                           forecast=forecast, metrics=metrics)


@app.route("/reports/export.csv")
@login_required
def export_report():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Bed Number", "Ward", "Bed Type", "Current Status"])
    for bed in Bed.query.join(Ward).order_by(Ward.name, Bed.bed_number).all():
        writer.writerow([bed.bed_number, bed.ward.name, bed.bed_type, bed.status])
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=bed_inventory_report.csv"})


@app.route("/api/dashboard")
@login_required
def dashboard_api():
    total = Bed.query.count()
    occupied = Bed.query.filter_by(status="Occupied").count()
    available = Bed.query.filter_by(status="Available").count()
    maintenance = Bed.query.filter_by(status="Maintenance").count()
    return jsonify({"total_beds": total, "occupied_beds": occupied,
                    "available_beds": available, "maintenance_beds": maintenance,
                    "occupancy_rate": round(occupied * 100 / total, 1) if total else 0})


def seed_demo_data():
    if not User.query.filter_by(username="admin").first():
        db.session.add(User(username="admin", password_hash=generate_password_hash("Admin@123"), role="admin"))
    if Ward.query.count() == 0:
        wards = [Ward(name="General Ward"), Ward(name="ICU"), Ward(name="Maternity"), Ward(name="Paediatrics")]
        db.session.add_all(wards)
        db.session.flush()
        bed_rows = [
            (wards[0], 12, "GW", "Standard"),
            (wards[1], 5, "ICU", "Critical Care"),
            (wards[2], 4, "MAT", "Standard"),
            (wards[3], 4, "PED", "Paediatric"),
        ]
        for ward, count, prefix, bed_type in bed_rows:
            for i in range(1, count + 1):
                db.session.add(Bed(bed_number=f"{prefix}-{i:02d}", ward_id=ward.id,
                                   bed_type=bed_type, status="Available"))
    db.session.commit()


with app.app_context():
    db.create_all()
    seed_demo_data()


if __name__ == "__main__":
    app.run(debug=True)
