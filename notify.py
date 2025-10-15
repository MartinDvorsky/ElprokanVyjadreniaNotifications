from datetime import date
from supabase import create_client, Client
#from dotenv import load_dotenv
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Optional

#load_dotenv()

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_API_KEY"]
email = os.environ["EMAIL"]
email_pass = os.environ["EMAIL_PASSWORD"]

today = date.today()
now_iso = datetime.now(timezone.utc).isoformat()

class EmailSender:
    def __init__(self):
        self.outlook_email = email
        self.outlook_password = email_pass
        self.smtp_server = "smtp.office365.com"
        self.smtp_port = 587
        self.error_message = ""

    def sendEmail(self, subject, body):
        try:
            msg = MIMEMultipart()
            msg["From"] = self.outlook_email
            #msg["To"] = "elprokan@elprokan.sk"
            msg["To"] = self.outlook_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "html"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.outlook_email, self.outlook_password)
                server.send_message(msg)
            return True
        except Exception as e:
            print(f"[MAIL ERROR] {e}")
            self.error_message = f"[SMTP MAIL ERROR] {e}"
            return False


class NotificationService:
    def __init__(self):
        self.supabase: Client = create_client(url, key)
        self.emailSender = EmailSender()
        # Ping na heartbeat tabuľku
        self.supabase.table("heartbeat").insert({
            "executed_at": now_iso,
            "note": "Daily GitHub Actions ping"
        }).execute()

        self.errorMessage = None

    def logAction(self, notification_id: int, action_type: str,
                  # 'firstNotification' | 'secondNotification' | 'setDone'
                  status: str = "SUCCESS",  # 'SUCCESS' | 'ERROR'
                  error_message: Optional[str] = None,
                  ):
        payload = {
            "idnotification": notification_id,
            "action_type": action_type,
            "status": status,
            "error_message": error_message,
        }
        self.supabase.table("notification_logs").insert(payload).execute()

    def buildNotifiactionBody(self, znacka: str, nazov_stavby: str, link: str | None, days: int = 20) -> str:
        safe_title = f"{znacka} – {nazov_stavby}"

        # časť s tlačidlom + linkom
        button_html = ""
        if link:
            button_html = f"""
            <p style="margin:0 0 16px;">Dokument otvoríš kliknutím na tlačidlo:</p>
            <table role="presentation" cellspacing="0" cellpadding="0">
                <tr>
                  <td bgcolor="#2563eb" style="border-radius:10px;">
                    <a href="{link}" target="_blank" rel="noopener noreferrer"
                       style="display:inline-block; padding:12px 18px; font-weight:600;
                              font-family:Segoe UI, Roboto, Arial, sans-serif;
                              color:#ffffff; text-decoration:none; font-size:14px;">
                      📄 Otvoriť dokument
                    </a>
                  </td>
                </tr>
            </table>
            <div style="font-size:12px; color:#6b7280; word-break:break-all; margin-top:12px;">
                Ak tlačidlo nefunguje, skopíruj tento odkaz do prehliadača:<br>
                <span>{link}</span>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html lang="sk">
        <head>
        <meta charset="UTF-8">
        <meta name="color-scheme" content="light only">
        </head>
        <body style="margin:0; padding:0; background:#ffffff; font-family:Segoe UI, Roboto, Arial, sans-serif;">
          <div style="padding:24px;">
            <div style="max-width:640px; margin:0 auto; background:#ffffff; border-radius:12px;
                        box-shadow:0 2px 8px rgba(0,0,0,.06); padding:24px; color:#1f2937;">
              <h1 style="font-size:20px; font-weight:700; margin:0 0 16px;">{safe_title}</h1>

              <div style="background:#f3f4f6; border-radius:8px; padding:12px 14px; font-size:14px; margin:12px 0 20px;">
                Od odoslania vyjadrení prešlo <strong>{days} dní</strong>.
              </div>

              {button_html}

              <p style="color:#9ca3af; font-size:12px; margin-top:24px;">
                Toto je automatická správa, neodpovedaj prosím na ňu.
              </p>
            </div>
          </div>
        </body>
        </html>
        """

    def selectUnfinished(self):
        response = self.supabase.table("notification").select("*").eq("done", False).execute()
        return response.data

    def setDone(self, id):
        try:
            response = self.supabase.table("notification").update({"done": True}).eq("idnotification", id).execute()
            return bool(response.data)
        except Exception as e:
            self.errorMessage = f"[setDone ERROR] {e}"
            return False

    def checkAndNotify(self):
        unfinished = self.selectUnfinished()
        for item in unfinished:
            id_ = item["idnotification"]
            test = item.get("test", False)
            #test interface
            """if test:
                self.emailSender.sendEmail(
                    f"{item['znacka']} - {item['nazovstavby']}",
                   self.buildNotifiactionBody(item['znacka'], item['nazovstavby'], item['sharedDocumentLink'], days=30))
                continue"""

            first_date = date.fromisoformat(item["firstnotification"])
            second_date = date.fromisoformat(item["secondnotification"])

            if today == first_date:
                firstNotificationCheck = self.emailSender.sendEmail(
                    f"{item['znacka']} - {item['nazovstavby']}",
                    self.buildNotifiactionBody(item['znacka'], item['nazovstavby'], item['sharedDocumentLink'], days=20)
                )

                if firstNotificationCheck:
                    self.logAction(id_, "firstNotification")
                else:
                    self.logAction(id_, "firstNotification", "ERROR", self.emailSender.error_message)

            elif today == second_date:
                secondNotification = self.emailSender.sendEmail(
                    f"{item['znacka']} - {item['nazovstavby']}",
                    self.buildNotifiactionBody(item['znacka'], item['nazovstavby'], item['sharedDocumentLink'], days=40)
                )

                if secondNotification:
                    self.logAction(id_, "secondNotification")
                    setDone = self.setDone(id_)
                    if setDone:
                        self.logAction(id_, "setDone")
                    else:
                        self.logAction(id_, "setDone", "ERROR", self.errorMessage)
                else:
                    self.logAction(id_, "secondNotification", "ERROR", self.emailSender.error_message)




n = NotificationService()
n.checkAndNotify()
