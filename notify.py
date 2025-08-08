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
now = datetime.now(timezone.utc).isoformat()

class EmailSender:
    def __init__(self):
        self.outlook_email = email
        self.outlook_password = email_pass
        self.smtp_server = "smtp.office365.com"
        self.smtp_port = 587

    def getFirstNotificationBody(self, znacka, nazovStavby):
        return f"{nazovStavby}: {znacka} - uplynulo 30 dni"

    def getSecondNotificationBody(self, znacka, nazovStavby):
        return f"{nazovStavby}: {znacka} - uplynulo 60 dni"

    def sendEmail(self, subject, body):
        message = MIMEMultipart()
        message["From"] = self.outlook_email
        message["To"] = self.outlook_email
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))
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
            "executed_at": now,
            "note": "Daily GitHub Actions ping"
        }).execute()

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
            if test:
                """self.emailSender.sendEmail(
                    f"{item['znacka']} - {item['nazovstavby']}",
                    self.emailSender.getFirstNotificationBody(item['znacka'], item["nazovstavby"])
                )
                """
                #continue

            # dátumy z databázy (ako string) prevedieme na objekt typu date
            first_date = date.fromisoformat(item["firstnotification"])
            second_date = date.fromisoformat(item["secondnotification"])


            if today == first_date:
                self.emailSender.sendEmail(
                    f"{item['znacka']} - {item['nazovstavby']}",
                    self.emailSender.getFirstNotificationBody(item['znacka'], item["nazovstavby"])
                )

            elif today == second_date:
                self.emailSender.sendEmail(
                    f"{item['znacka']} - {item['nazovstavby']}",
                    self.emailSender.getSecondNotificationBody(item['znacka'], item["nazovstavby"])
                )

                print(f"[{id_}] - Označujeme ako hotové (done=True).")
                self.set_done(id_)


n = NotificationService()
n.check_and_notify()
