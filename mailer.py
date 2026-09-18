"""
mailer.py
Sends the two emails the system needs: the invitation link and the QR gate pass.

Uses Brevo's transactional email HTTP API (https://api.brevo.com) instead of
raw SMTP. Cloud platforms like Render block outbound SMTP ports (25/465/587)
on their free tier to stop spam, but plain HTTPS (port 443) always works —
so an HTTP-based email API is the reliable choice for a deployed app.

Mail is sent on a background thread so the person clicking "Send invitation"
never has to wait for the request to finish.
"""

import base64
import threading

import requests

from config import Config

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def _deliver(payload):
    try:
        response = requests.post(
            BREVO_ENDPOINT,
            headers={
                "api-key": Config.BREVO_API_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            timeout=20,
        )
        if response.status_code >= 300:
            print(f"[mail] FAILED for {payload['to'][0]['email']}: "
                  f"{response.status_code} {response.text}")
        else:
            print(f"[mail] sent to {payload['to'][0]['email']} — {payload['subject']}")
    except Exception as error:                      # noqa: BLE001
        # A failed email must never crash the visitor workflow. The invite
        # link is always available on screen as a fallback.
        print(f"[mail] FAILED for {payload['to'][0]['email']}: {error}")


def _send_async(payload):
    threading.Thread(target=_deliver, args=(payload,), daemon=True).start()


def _shell(inner_html, footer_note):
    """
    A table-based email shell (dark header band, white card body, footer).
    Tables are used instead of <div>/flex because that is what renders
    consistently across Gmail, Outlook and mobile mail apps.
    """
    return f"""
    <body style="margin:0;padding:0;background:#eef1f5;
                 font-family:'Segoe UI',Arial,sans-serif;color:#1f2933">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="background:#eef1f5;padding:32px 16px">
        <tr>
          <td align="center">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="max-width:520px;background:#ffffff;border-radius:8px;
                          overflow:hidden;box-shadow:0 1px 3px rgba(15,43,69,.12)">

              <!-- header band -->
              <tr>
                <td style="background:#0f2b45;border-bottom:3px solid #a97c2f;
                           padding:22px 28px">
                  <span style="color:#ffffff;font-size:17px;font-weight:600">
                    {Config.ORG_NAME}
                  </span><br>
                  <span style="color:#9fb3c8;font-size:12.5px">{Config.ORG_TAGLINE}</span>
                </td>
              </tr>

              <!-- body -->
              <tr>
                <td style="padding:30px 28px 8px;font-size:15px;line-height:1.65">
                  {inner_html}
                </td>
              </tr>

              <!-- footer -->
              <tr>
                <td style="padding:20px 28px 26px">
                  <hr style="border:none;border-top:1px solid #e3e8ee;margin:0 0 16px">
                  <span style="font-size:12px;color:#8a97a6">{footer_note}</span>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </body>
    """


def _button(url, label):
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:26px 0">
      <tr>
        <td style="background:#0f2b45;border-radius:6px">
          <a href="{url}" target="_blank"
             style="display:inline-block;padding:13px 28px;font-size:14.5px;
                    font-weight:600;color:#ffffff;text-decoration:none">{label}</a>
        </td>
      </tr>
    </table>
    """


def _base_payload(subject, to_address, html_body):
    return {
        "sender": {"name": Config.MAIL_SENDER_NAME, "email": Config.MAIL_USERNAME},
        "to": [{"email": to_address}],
        "subject": subject,
        "htmlContent": html_body,
    }


def send_invitation(to_address, host_name, visit_datetime, register_url):
    """Email 1 — asks the visitor to complete their details."""
    if not Config.MAIL_ENABLED:
        print(f"[mail] disabled. Invitation link for {to_address}: {register_url}")
        return False

    body = f"""
      <p style="margin:0 0 16px">Hello,</p>
      <p style="margin:0 0 16px">
        <strong>{host_name}</strong> has invited you to visit on
        <strong>{visit_datetime}</strong>.
      </p>
      <p style="margin:0 0 4px">
        Please complete your visitor details before you arrive — it takes about
        a minute, and your gate pass is issued as soon as you finish.
      </p>
      {_button(register_url, "Complete visitor details")}
      <p style="margin:0 0 6px;font-size:12.5px;color:#8a97a6">
        If the button does not open, copy this link into your browser:
      </p>
      <p style="margin:0;font-size:12.5px;color:#0f2b45;word-break:break-all">
        {register_url}
      </p>
    """
    html = _shell(body, "This link is personal to you. Please do not forward it.")
    payload = _base_payload(f"Visit invitation from {Config.ORG_NAME}", to_address, html)
    _send_async(payload)
    return True


def send_gate_pass(to_address, visitor_name, visit_datetime, host_name,
                   pass_url, qr_bytes):
    """Email 2 — delivers the QR gate pass as an attachment."""
    if not Config.MAIL_ENABLED:
        print(f"[mail] disabled. Gate pass link for {to_address}: {pass_url}")
        return False

    body = f"""
      <p style="margin:0 0 4px;font-size:12.5px;font-weight:600;letter-spacing:.02em;
                color:#a97c2f">VISIT CONFIRMED</p>
      <p style="margin:0 0 16px;font-size:19px;font-weight:600;color:#0f2b45">
        Your gate pass is ready
      </p>
      <p style="margin:0 0 16px">Hello {visitor_name},</p>
      <p style="margin:0 0 16px">
        Your visit to meet <strong>{host_name}</strong> on
        <strong>{visit_datetime}</strong> is confirmed. The QR code attached to
        this email is your gate pass — show it to the security officer at the
        gate. It is valid for this single visit only.
      </p>
      {_button(pass_url, "Open gate pass")}
      <p style="margin:0;font-size:13px;color:#5c6b7a">
        Please carry a photo ID along with this pass.
      </p>
    """
    html = _shell(body, "Generated automatically — please do not reply to this email.")
    payload = _base_payload(f"Gate pass — {Config.ORG_NAME}", to_address, html)
    payload["attachment"] = [{
        "content": base64.b64encode(qr_bytes).decode("ascii"),
        "name": "gate-pass.png",
    }]
    _send_async(payload)
    return True