# CareBeds — AI Hospital Bed Management System

A runnable educational web application built with Python, Flask, SQLite, SQLAlchemy, Bootstrap, Chart.js, Pandas, NumPy and scikit-learn.

## Included features
- Login/logout with hashed passwords and server-side sessions
- Admin-only user management: create and delete staff, doctor, and administrator accounts
- Dashboard with total, available, occupied and maintenance bed counts
- Bed inventory: add, search, and update eligible bed status
- Patient registration and search
- Admission and discharge workflow with active-bed checks
- Seven-day Random Forest demonstration forecast
- Ward-wise occupancy snapshot and interactive doughnut chart
- CSV export for bed inventory
- JSON dashboard endpoint
- Automatic SQLite database creation and demo ward/bed seed data

## Run on Windows
1. Extract this ZIP.
2. Open the extracted `AI_Hospital_Bed_Management` folder in VS Code.
3. Open **Terminal → New Terminal**.
4. Run these commands one at a time:

   ```powershell
   python -m venv venv
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   .\venv\Scripts\python.exe app.py
   ```

5. Open `http://127.0.0.1:5000` in your browser.

If `python` is not recognized, install Python 3.10+ and select **Add Python to PATH** during installation. An internet connection is needed for the first dependency installation and online CDN assets.

## Demo login
- Username: `admin`
- Password: `Admin@123`

This is a demo credential. Change it and set a strong `SECRET_KEY` before any deployment. Do not expose this development server to the internet.

## User management
Sign in with the demo admin account, then choose **User management** in the sidebar. Create a username (3–80 characters), a password of at least 8 characters, and a role. The page is restricted to administrator accounts. The current account and the last administrator cannot be deleted. This educational version stores the selected role but does not yet enforce different operational permissions for doctors and staff.

## Database
The app automatically creates `instance/hospital.db` and demo wards/beds on first launch. Keep the database file if you want to preserve your demo records. Back it up before making schema changes.

## AI / ML disclaimer
The forecasting page trains a Random Forest regression model using generated synthetic daily data so the feature can be demonstrated without private hospital records. The results are illustrative only and are not validated predictions. For credible forecasting, use authorized, de-identified historical occupancy data, evaluate on a later time period, and compare against a baseline.

## Safety and privacy
This project is for learning and academic demonstration, not a certified clinical product. Use fictional data only. It does not make clinical decisions. Staff must verify any real-world bed placement using approved hospital procedures. Before production use, add CSRF protection to every state-changing form, rate limiting, audit logging, stronger role permissions, secure secret management, backups, and security testing.
