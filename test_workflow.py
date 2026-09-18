"""
test_workflow.py
Runs the complete visitor journey against the app without opening a browser:
invite -> register -> QR -> scan -> entry -> duplicate blocked.

Run it with:  python test_workflow.py
"""
import os, re, tempfile

os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")
os.environ["APP_BASE_URL"] = "http://localhost:5000"

from app import app  # noqa: E402

app.config["TESTING"] = False
emp = app.test_client()
grd = app.test_client()

# 1. employee login
r = emp.post("/login", data={"username": "employee", "password": "employee123"}, follow_redirects=True)
assert "Visitor dashboard" in r.get_data(as_text=True), "employee login failed"
print("1. employee login OK")

# 2. send invitation
r = emp.post("/employee/invite", data={
    "email": "visitor@example.com", "person_to_meet": "Rahul Verma",
    "visit_datetime": "2026-09-18T11:30", "purpose": "Vendor meeting", "unit": "Purchase",
}, follow_redirects=True)
body = r.get_data(as_text=True)
token = re.search(r"/visitor/register/([A-Za-z0-9_-]+)", body).group(1)
print("2. invitation created, token =", token[:12] + "...")

# 3. visitor registers
r = emp.get(f"/visitor/register/{token}")
assert r.status_code == 200
r = emp.post(f"/visitor/register/{token}", data={
    "name": "Anita Sharma", "phone": "9876543210", "company": "Sharma Engineering",
    "purpose": "Vendor meeting", "unit": "Purchase",
}, follow_redirects=True)
assert "Visitor gate pass" in r.get_data(as_text=True), "pass not issued"
print("3. visitor registered, pass issued OK")

# 4. QR image renders
r = emp.get(f"/qr/{token}.png")
assert r.status_code == 200 and r.data[:4] == b"\x89PNG", "QR image failed"
print("4. QR image OK,", len(r.data), "bytes")

# 5. guard must log in to verify
r = grd.get(f"/verify/{token}", follow_redirects=True)
assert "Sign in" in r.get_data(as_text=True), "verify page was not protected"
grd.post("/login", data={"username": "guard", "password": "guard123"})
r = grd.get(f"/verify/{token}")
assert "Pass is valid" in r.get_data(as_text=True), "valid pass not recognised"
print("5. guard login + verification OK")

# 6. allow entry
r = grd.post(f"/verify/{token}/decision", data={"decision": "allow"}, follow_redirects=True)
assert "Pass already used" in r.get_data(as_text=True), "entry not recorded"
print("6. entry recorded OK")

# 7. duplicate use blocked
r = grd.post(f"/verify/{token}/decision", data={"decision": "allow"}, follow_redirects=True)
assert "no longer valid" in r.get_data(as_text=True), "duplicate use was not blocked!"
print("7. duplicate QR use blocked OK")

# 8. unknown token
r = grd.get("/verify/totally-made-up-token")
assert r.status_code == 404 and "not recognised" in r.get_data(as_text=True)
print("8. unknown token rejected OK")

# 9. register + guard dashboard
assert "Anita Sharma" in emp.get("/employee/records").get_data(as_text=True)
assert "Anita Sharma" in grd.get("/guard").get_data(as_text=True)
print("9. register and gate list OK")

# 10. role separation
assert grd.get("/employee", follow_redirects=True).get_data(as_text=True).count("Sign in") > 0
print("10. role separation OK")

print("\nAll checks passed.")
os.unlink(os.environ["DB_PATH"])
