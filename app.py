"""
app.py
Smart Visitor Management & Secure QR Verification System.

The whole visitor journey in one file:
    employee invites  ->  visitor registers  ->  QR pass issued
                      ->  guard scans        ->  entry recorded

Run locally with:  python app.py
"""

import io
import secrets
from datetime import datetime
from functools import wraps

import qrcode
from flask import (
    Flask, abort, flash, redirect, render_template, request,
    send_file, session, url_for,
)
from werkzeug.security import check_password_hash

import database as db
import mailer
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.teardown_appcontext(db.close_db)


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------

def base_url():
    """
    The public address of this application.

    A QR code is useless if it points at 127.0.0.1, so on Render we read the
    real host name from the environment, and locally we fall back to whatever
    host the browser used (which also covers an ngrok tunnel).
    """
    if Config.APP_BASE_URL:
        return Config.APP_BASE_URL.rstrip("/")
    return request.url_root.rstrip("/")


def login_required(role):
    """Blocks a page unless someone with the right role is signed in."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if session.get("role") != role:
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapper
    return decorator


def make_qr_png(data):
    """Return a QR code for `data` as PNG bytes."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#12324f", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def pretty_datetime(value):
    """'2026-03-14 15:30' -> '14 Mar 2026, 03:30 PM'"""
    if not value:
        return "—"
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value, pattern).strftime("%d %b %Y, %I:%M %p")
        except ValueError:
            continue
    return value


app.jinja_env.filters["pretty"] = pretty_datetime


@app.context_processor
def inject_globals():
    return {
        "org_name": Config.ORG_NAME,
        "org_tagline": Config.ORG_TAGLINE,
        "current_user": session.get("full_name"),
        "current_role": session.get("role"),
        "mail_enabled": Config.MAIL_ENABLED,
        "year": datetime.now().year,
    }


# ----------------------------------------------------------------------
# Public pages and authentication
# ----------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.find_user(username)

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            destination = request.form.get("next") or (
                url_for("employee_dashboard") if user["role"] == "employee"
                else url_for("guard_dashboard")
            )
            return redirect(destination)

        flash("That username and password do not match an account.", "error")

    return render_template("login.html", next=request.args.get("next", ""))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))


# ----------------------------------------------------------------------
# Employee side
# ----------------------------------------------------------------------

@app.route("/employee")
@login_required("employee")
def employee_dashboard():
    return render_template(
        "employee_dashboard.html",
        counts=db.status_counts(),
        visitors=db.list_visitors(limit=15),
    )


@app.route("/employee/invite", methods=["GET", "POST"])
@login_required("employee")
def invite_visitor():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        person_to_meet = request.form.get("person_to_meet", "").strip()
        visit_datetime = request.form.get("visit_datetime", "").strip().replace("T", " ")
        purpose = request.form.get("purpose", "").strip()
        unit = request.form.get("unit", "").strip()

        if not email or "@" not in email:
            flash("Enter a valid email address for the visitor.", "error")
        elif not person_to_meet or not visit_datetime:
            flash("Person to meet and visit date/time are both required.", "error")
        else:
            # The security core of the project: an unguessable invitation token.
            token = secrets.token_urlsafe(32)
            connection = db.get_db()
            connection.execute(
                "INSERT INTO visitors (token, email, person_to_meet, unit, purpose, "
                "visit_datetime, status, invited_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (token, email, person_to_meet, unit, purpose, visit_datetime,
                 db.STATUS_INVITED, session["user_id"], db.now()),
            )
            connection.commit()

            register_url = f"{base_url()}/visitor/register/{token}"
            sent = mailer.send_invitation(
                email, session["full_name"], pretty_datetime(visit_datetime), register_url
            )
            if sent:
                flash(f"Invitation sent to {email}.", "success")
            else:
                flash("Email is not configured, so share this link with the visitor "
                      f"yourself: {register_url}", "warning")

            visitor = db.find_visitor_by_token(token)
            return redirect(url_for("visitor_detail", visitor_id=visitor["id"]))

    return render_template("invite_visitor.html", form=request.form)


@app.route("/employee/visitor/<int:visitor_id>")
@login_required("employee")
def visitor_detail(visitor_id):
    visitor = db.find_visitor_by_id(visitor_id)
    if visitor is None:
        abort(404)
    return render_template(
        "visitor_detail.html",
        visitor=visitor,
        register_url=f"{base_url()}/visitor/register/{visitor['token']}",
        pass_url=f"{base_url()}/visitor/pass/{visitor['token']}",
    )


@app.route("/employee/visitor/<int:visitor_id>/resend", methods=["POST"])
@login_required("employee")
def resend_invitation(visitor_id):
    visitor = db.find_visitor_by_id(visitor_id)
    if visitor is None:
        abort(404)
    if visitor["status"] != db.STATUS_INVITED:
        flash("This visitor has already registered, so there is nothing to resend.", "warning")
    else:
        register_url = f"{base_url()}/visitor/register/{visitor['token']}"
        if mailer.send_invitation(visitor["email"], session["full_name"],
                                  pretty_datetime(visitor["visit_datetime"]), register_url):
            flash(f"Invitation sent again to {visitor['email']}.", "success")
        else:
            flash("Email is not configured. Share the link below with the visitor.", "warning")
    return redirect(url_for("visitor_detail", visitor_id=visitor_id))


@app.route("/employee/records")
@login_required("employee")
def records():
    status = request.args.get("status") or None
    search = request.args.get("q", "").strip() or None
    return render_template(
        "records.html",
        visitors=db.list_visitors(status=status, search=search),
        status=status or "",
        search=search or "",
    )


# ----------------------------------------------------------------------
# Visitor side — no login, the secure token is the credential
# ----------------------------------------------------------------------

@app.route("/visitor/register/<token>", methods=["GET", "POST"])
def visitor_register(token):
    visitor = db.find_visitor_by_token(token)
    if visitor is None:
        return render_template("invalid_link.html"), 404

    # Already filled in? Send them straight to their pass.
    if visitor["status"] != db.STATUS_INVITED:
        return redirect(url_for("visitor_pass", token=token))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()

        if not name or not phone:
            flash("Your name and phone number are required.", "error")
        else:
            connection = db.get_db()
            connection.execute(
                "UPDATE visitors SET name = ?, phone = ?, company = ?, purpose = ?, "
                "unit = ?, status = ?, registered_at = ? WHERE token = ?",
                (
                    name, phone,
                    request.form.get("company", "").strip(),
                    request.form.get("purpose", "").strip() or visitor["purpose"],
                    request.form.get("unit", "").strip() or visitor["unit"],
                    db.STATUS_REGISTERED, db.now(), token,
                ),
            )
            connection.commit()

            updated = db.find_visitor_by_token(token)
            host = db.get_db().execute(
                "SELECT full_name FROM users WHERE id = ?", (updated["invited_by"],)
            ).fetchone()
            pass_url = f"{base_url()}/visitor/pass/{token}"
            mailer.send_gate_pass(
                updated["email"], name, pretty_datetime(updated["visit_datetime"]),
                host["full_name"] if host else "your host",
                pass_url, make_qr_png(f"{base_url()}/verify/{token}"),
            )
            return redirect(url_for("visitor_pass", token=token))

    return render_template("visitor_register.html", visitor=visitor, form=request.form)


@app.route("/visitor/pass/<token>")
def visitor_pass(token):
    visitor = db.find_visitor_by_token(token)
    if visitor is None or visitor["status"] == db.STATUS_INVITED:
        return render_template("invalid_link.html"), 404
    host = db.get_db().execute(
        "SELECT full_name FROM users WHERE id = ?", (visitor["invited_by"],)
    ).fetchone()
    return render_template("visitor_pass.html", visitor=visitor,
                           host=host["full_name"] if host else "—")


@app.route("/qr/<token>.png")
def qr_image(token):
    """The QR image itself. It encodes the guard's verification URL."""
    visitor = db.find_visitor_by_token(token)
    if visitor is None or visitor["status"] == db.STATUS_INVITED:
        abort(404)
    png = make_qr_png(f"{base_url()}/verify/{token}")
    return send_file(io.BytesIO(png), mimetype="image/png",
                     download_name=f"gate-pass-{visitor['id']}.png")


# ----------------------------------------------------------------------
# Guard side
# ----------------------------------------------------------------------

@app.route("/guard")
@login_required("guard")
def guard_dashboard():
    return render_template("guard_dashboard.html",
                           visitors=db.expected_today(),
                           counts=db.status_counts())


@app.route("/guard/scan")
@login_required("guard")
def guard_scan():
    return render_template("guard_scan.html")


@app.route("/verify/<token>")
@login_required("guard")
def verify(token):
    """
    Where the QR code lands. Three checks decide what the guard sees:
      1. does the token exist at all?
      2. has the visitor completed registration?
      3. has this pass already been used?
    """
    visitor = db.find_visitor_by_token(token)
    if visitor is None:
        return render_template("verify_result.html", state="unknown", visitor=None), 404

    host = db.get_db().execute(
        "SELECT full_name FROM users WHERE id = ?", (visitor["invited_by"],)
    ).fetchone()
    host_name = host["full_name"] if host else "—"

    if visitor["status"] == db.STATUS_INVITED:
        state = "incomplete"
    elif visitor["status"] == db.STATUS_ENTERED:
        state = "used"
    elif visitor["status"] == db.STATUS_REJECTED:
        state = "rejected"
    else:
        state = "valid"

    return render_template("verify_result.html", state=state,
                           visitor=visitor, host=host_name)


@app.route("/verify/<token>/decision", methods=["POST"])
@login_required("guard")
def verify_decision(token):
    visitor = db.find_visitor_by_token(token)
    if visitor is None:
        abort(404)

    decision = request.form.get("decision")
    connection = db.get_db()

    if decision == "allow":
        # Re-check inside the same request: a pass can only be used once.
        if visitor["status"] != db.STATUS_REGISTERED:
            flash("This pass is no longer valid for entry.", "error")
            return redirect(url_for("verify", token=token))
        connection.execute(
            "UPDATE visitors SET status = ?, entry_time = ?, verified_by = ? WHERE token = ?",
            (db.STATUS_ENTERED, db.now(), session["full_name"], token),
        )
        connection.commit()
        flash(f"Entry recorded for {visitor['name']}.", "success")

    elif decision == "reject":
        connection.execute(
            "UPDATE visitors SET status = ?, verified_by = ?, remarks = ? WHERE token = ?",
            (db.STATUS_REJECTED, session["full_name"],
             request.form.get("remarks", "").strip(), token),
        )
        connection.commit()
        flash(f"Entry refused for {visitor['email']}.", "warning")

    return redirect(url_for("verify", token=token))


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    return render_template("invalid_link.html"), 404


db.init_db(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
