from datetime import date
from supabase import create_client, Client
#from dotenv import load_dotenv
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

#load_dotenv()

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_API_KEY"]
email =os.environ["EMAIL"]
email_pass  = os.environ["EMAIL_PASSWORD"]

today = date.today()
now_iso = datetime.now(timezone.utc).isoformat()  # alebo .replace(microsecond=0).isoformat()

class EmailSender:
    def __init__(self):
        self.outlook_email = email
        self.outlook_password = email_pass
        self.smtp_server = "smtp.office365.com"
        self.smtp_port = 587

    def sendEmail(self, subject, body):
        message = MIMEMultipart()
        message["From"] = self.outlook_email
        message["To"] = self.outlook_email
        message["Subject"] = subject
        message.attach(MIMEText(body, "html"))
        server = smtplib.SMTP(self.smtp_server, self.smtp_port)
        server.starttls()
        server.login(self.outlook_email, self.outlook_password)
        server.send_message(message)

class NotificationService:
    def __init__(self):
        self.supabase: Client = create_client(url, key)
        self.emailSender = EmailSender()
        # Ping na heartbeat tabuľku
        self.supabase.table("heartbeat").insert({
            "executed_at": now_iso,
            "note": "Daily GitHub Actions ping"
        }).execute()

    def buildNotifiactionBody(self, znacka: str, nazov_stavby: str, link: str | None, days: int = 30) -> str:
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

    def select_unfinished(self):
        response = self.supabase.table("notification").select("*").eq("done", False).execute()
        return response.data

    def set_done(self, id):
        response = self.supabase.table("notification").update({"done": True}).eq("idnotification", id).execute()
        return bool(response.data)

    def check_and_notify(self):
        unfinished = self.select_unfinished()
        for item in unfinished:
            id_ = item["idnotification"]
            test = item.get("test", False)
            """if test:
                self.emailSender.sendEmail(
                    f"{item['znacka']} - {item['nazovstavby']}",
                   self.buildNotifiactionBody(item['znacka'], item['nazovstavby'], item['sharedDocumentLink'], days=30))
                continue"""

            # dátumy z databázy (ako string) prevedieme na objekt typu date
            first_date = date.fromisoformat(item["firstnotification"])
            second_date = date.fromisoformat(item["secondnotification"])


            if today == first_date:
                self.emailSender.sendEmail(
                    f"{item['znacka']} - {item['nazovstavby']}",
                    self.buildNotifiactionBody(item['znacka'], item['nazovstavby'], item['sharedDocumentLink'], days=30)
                )

            elif today == second_date:
                self.emailSender.sendEmail(
                    f"{item['znacka']} - {item['nazovstavby']}",
                    self.buildNotifiactionBody(item['znacka'], item['nazovstavby'], item['sharedDocumentLink'], days=60)
                )

                print(f"[{id_}] - Označujeme ako hotové (done=True).")
                self.set_done(id_)


n = NotificationService()
n.check_and_notify()
