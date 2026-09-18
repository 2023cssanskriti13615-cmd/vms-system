# Setup guide

Two parts: **A** gets it running on your laptop, **B** puts it on a public URL with
Render so the QR codes work from any phone, anywhere.

---

# Part A — Run it on your laptop

### A1. Install Python

You need Python 3.10 or newer. Check with:

```bash
python --version
```

If that fails, try `python3 --version`. Download from python.org if needed, and
tick **"Add Python to PATH"** during the Windows installer.

### A2. Open the project folder

Unzip the folder, then open a terminal inside it:

```bash
cd smart-visitor-management
```

### A3. Create a virtual environment

Keeps this project's packages separate from everything else on your machine.

**Windows**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
```

Your prompt should now start with `(venv)`.

### A4. Install the packages

```bash
pip install -r requirements.txt
```

### A5. Create your settings file

Copy `.env.example` to a new file called `.env`:

**Windows:** `copy .env.example .env`
**macOS / Linux:** `cp .env.example .env`

Open `.env` in any text editor. For a first run you can leave the mail settings
blank — the app will print the invitation link on screen instead of emailing it.
Set a real `SECRET_KEY` though:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output as the value of `SECRET_KEY`.

### A6. Start the app

```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

Sign in as `employee` / `employee123`, send an invitation, and the link appears in
a yellow bar on screen. Open it in another tab as the visitor. Then sign in as
`guard` / `guard123` in a private/incognito window to verify the pass.

> One browser can only hold one session at a time. Use a normal window for the
> employee and an incognito window for the guard, and both roles work side by side.

### A7. Check everything works

```bash
python test_workflow.py
```

This walks the whole journey — invite, register, QR, scan, entry, duplicate
blocked — and prints ten OK lines. Useful to run in front of your examiner.

---

# Part B — Turn on Gmail

Gmail will not accept your normal password from a script. You need a 16-character
**App Password**.

### B1. Turn on 2-Step Verification

Go to **myaccount.google.com → Security → 2-Step Verification** and switch it on.
App Passwords do not appear until this is done.

### B2. Create the App Password

Go to **myaccount.google.com/apppasswords**. Type a name like `Visitor System`
and click **Create**. Google shows a 16-character password such as
`abcd efgh ijkl mnop`.

Copy it and **remove the spaces**.

### B3. Put it in `.env`

```
MAIL_USERNAME=youraddress@gmail.com
MAIL_PASSWORD=abcdefghijklmnop
MAIL_SENDER_NAME=Visitor Desk
```

Restart the app (`Ctrl+C`, then `python app.py` again) and send an invitation.
The terminal prints `[mail] sent to …` when it goes out.

If it says `[mail] FAILED`, the usual causes are: spaces left in the password,
2-Step Verification not enabled, or a college Wi-Fi network blocking port 465.

---

# Part C — Deploy to Render (the public URL)

This is what makes the QR code scannable from any phone. Render's free tier is
enough.

### C1. Put the code on GitHub

Create a free account at github.com, then a **new repository** named
`smart-visitor-management`. Keep it private if you prefer.

In your project folder:

```bash
git init
git add .
git commit -m "Smart Visitor Management System"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/smart-visitor-management.git
git push -u origin main
```

`.gitignore` already stops your `.env` and database file from being uploaded, so
your Gmail password never goes to GitHub.

### C2. Create the Render service

1. Sign up at **render.com** with your GitHub account.
2. Click **New → Web Service**.
3. Choose your `smart-visitor-management` repository.
4. Fill in:
   - **Name:** `smart-visitor-management` (this becomes your URL)
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** Free

### C3. Add the environment variables

Before clicking Create, open **Advanced → Add Environment Variable** and add:

| Key | Value |
|-----|-------|
| `SECRET_KEY` | a long random string (generate as in step A5) |
| `MAIL_USERNAME` | your Gmail address |
| `MAIL_PASSWORD` | your 16-character App Password |
| `MAIL_SENDER_NAME` | Visitor Desk |
| `ORG_NAME` | the title shown at the top of every page |
| `EMPLOYEE_USERNAME` / `EMPLOYEE_PASSWORD` | your employee login |
| `GUARD_USERNAME` / `GUARD_PASSWORD` | your guard login |
| `PYTHON_VERSION` | `3.11.9` |

You do **not** need to set `APP_BASE_URL`. Render supplies `RENDER_EXTERNAL_URL`
automatically and the app reads it, so the QR codes point at the right host from
the first deploy.

### C4. Deploy

Click **Create Web Service**. The first build takes two or three minutes. When it
finishes you get a URL like:

```
https://smart-visitor-management.onrender.com
```

That address works from any phone on any network. Open it, sign in, invite a
visitor, and scan the QR with a real phone camera — this is the demo to show in
college.

### C5. Keep the visitor records between deploys (optional)

Render's free tier wipes the disk on every redeploy, so the SQLite file resets.
To keep records:

1. Go to your service → **Disks → Add Disk**
2. Name: `data`, Mount Path: `/var/data`, Size: 1 GB
3. Add one more environment variable: `DB_PATH` = `/var/data/visitors.db`

Note that disks are a paid feature on Render. For a college demo the free tier is
fine — just re-create a visitor or two before you present.

---

# Things to know before your demo

**The free service sleeps.** After 15 minutes with no traffic Render puts the app
to sleep, and the first request afterwards takes 30–50 seconds. Open your URL a
minute before you present so it is already awake.

**Camera scanning needs HTTPS.** Browsers only allow camera access on a secure
address. Your Render URL is HTTPS, so scanning works there. On `127.0.0.1` it
works too. It will *not* work on a plain `http://192.168.x.x` address — use the
Render URL on the phone.

**Two roles, two windows.** Employee in one browser, guard in an incognito window.

**If the camera still refuses,** the scan page has a box where the guard can paste
the pass link instead, and today's expected visitors each have a "Verify" link on
the guard dashboard. Either path reaches the same verification screen.

---

# Quick command reference

| What | Command |
|------|---------|
| Activate the environment | `venv\Scripts\activate` (Win) / `source venv/bin/activate` |
| Install packages | `pip install -r requirements.txt` |
| Run locally | `python app.py` |
| Run the workflow test | `python test_workflow.py` |
| Start fresh database | delete `visitors.db`, then run the app again |
| Push an update to Render | `git add . && git commit -m "update" && git push` |
