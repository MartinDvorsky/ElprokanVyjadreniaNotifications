from datetime import date, timedelta
from supabase import create_client, Client
import os
import msal
import requests
from datetime import datetime, timezone
from typing import Optional

#from dotenv import load_dotenv
#load_dotenv()


# Import SharePoint managera z existujúceho súboru
from SharepointKartaStavbyFinder import SharePointManager

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_API_KEY"]
email = os.environ["EMAIL"]

# SharePoint credentials (použijeme aj pre email)
TENANT_ID = os.environ['TENANT_ID']
CLIENT_ID = os.environ['CLIENT_ID']
CLIENT_SECRET = os.environ['CLIENT_SECRET']
SHAREPOINT_SITE_URL = os.environ['SHAREPOINT_SITE_URL']
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

today = date.today()
now_iso = datetime.now(timezone.utc).isoformat()


class GraphEmailSender:
    """
    Email sender používajúci Microsoft Graph API namiesto SMTP.
    Funguje s 2FA a je bezpečnejší.
    """

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, from_email: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.from_email = from_email
        self.error_message = ""

    def get_access_token(self) -> Optional[str]:
        """Získa access token pre Graph API"""
        try:
            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=authority,
                client_credential=self.client_secret,
            )

            result = app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )

            if "access_token" in result:
                return result["access_token"]
            else:
                error = result.get("error_description", result.get("error"))
                self.error_message = f"Token error: {error}"
                print(f"[AUTH ERROR] {self.error_message}")
                return None

        except Exception as e:
            self.error_message = f"Auth exception: {str(e)}"
            print(f"[AUTH ERROR] {self.error_message}")
            return None

    def sendEmail(self, subject: str, body: str, to_email: str = "elprokan@elprokan.sk") -> bool:
        """
        Pošle email cez Microsoft Graph API

        Args:
            subject: Predmet emailu
            body: HTML obsah emailu
            to_email: Príjemca

        Returns:
            bool: True ak sa podarilo odoslať
        """
        try:
            token = self.get_access_token()
            if not token:
                return False

            # Priprav správu
            message = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "HTML",
                        "content": body
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "address": to_email
                            }
                        }
                    ]
                },
                "saveToSentItems": "true"
            }

            # Pošli cez Graph API
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            response = requests.post(
                f"https://graph.microsoft.com/v1.0/users/{self.from_email}/sendMail",
                headers=headers,
                json=message,
                timeout=30
            )

            if response.status_code == 202:
                print(f"[MAIL] ✓ Email odoslaný na {to_email}")
                return True
            else:
                self.error_message = f"Graph API error {response.status_code}: {response.text}"
                print(f"[MAIL ERROR] {self.error_message}")
                return False

        except requests.exceptions.RequestException as e:
            self.error_message = f"Request error: {str(e)}"
            print(f"[MAIL ERROR] {self.error_message}")
            return False
        except Exception as e:
            self.error_message = f"Unexpected error: {str(e)}"
            print(f"[MAIL ERROR] {self.error_message}")
            return False


class NotificationService:
    def __init__(self):
        self.supabase: Client = create_client(url, key)

        # Použije Graph API namiesto SMTP
        self.emailSender = GraphEmailSender(TENANT_ID, CLIENT_ID, CLIENT_SECRET, email)

        # Inicializácia SharePoint managera
        self.sharepoint = SharePointManager(TENANT_ID, CLIENT_ID, CLIENT_SECRET, OPENAI_API_KEY)
        if self.sharepoint.get_access_token():
            self.sharepoint.get_site_id(SHAREPOINT_SITE_URL)
            print("[SharePoint] ✓ Úspešne pripojený")
        else:
            print("[SharePoint] ✗ Zlyhalo pripojenie")

        # Ping na heartbeat tabuľku
        self.supabase.table("heartbeat").insert({
            "executed_at": now_iso,
            "note": "Daily GitHub Actions ping"
        }).execute()

        self.errorMessage = None

    def logAction(self, notification_id: int, action_type: str,
                  status: str = "SUCCESS",
                  error_message: Optional[str] = None):
        payload = {
            "idnotification": notification_id,
            "action_type": action_type,
            "status": status,
            "error_message": error_message,
        }
        self.supabase.table("notification_logs").insert(payload).execute()

    def getSharePointLink(self, znacka: str, nazov_stavby: str) -> Optional[str]:
        """
        Nájde Kartu stavby na SharePointe a vráti webUrl

        Returns:
            str: SharePoint webUrl alebo None ak sa nenašiel
        """
        try:
            print(f"[SharePoint] Hľadám súbor pre {znacka}...")

            # Použije existujúcu metódu na vyhľadanie xlsx súborov
            files = self.sharepoint.get_xlsx_files_from_folder(
                znacka,
                nazov_stavby,
                search_subfolders=False,
                auto_select=True
            )

            if files and len(files) > 0:
                selected_file = files[0]
                web_url = selected_file.get('webUrl')

                if web_url:
                    print(f"[SharePoint] ✓ Nájdený: {selected_file['name']}")
                    return web_url
                else:
                    print(f"[SharePoint] ✗ webUrl nebola nájdená v odpovedi")
                    return None
            else:
                print(f"[SharePoint] ✗ Súbor nenájdený")
                return None

        except Exception as e:
            print(f"[SharePoint] ✗ Chyba pri hľadaní: {e}")
            return None

    def buildTestEmailBody(self, znacka: str, nazov_stavby: str, link: str | None,
                           days: int, error: str | None = None) -> str:
        """Email pre testovanie deň pred odoslaním"""
        safe_title = f"🧪 TEST: {znacka} — {nazov_stavby}"

        if error:
            status_html = f"""
            <div style="background:#fee2e2; border-left:4px solid #dc2626; padding:16px; border-radius:8px; margin:16px 0;">
                <p style="margin:0; color:#991b1b; font-weight:600;">❌ CHYBA PRI HĽADANÍ NA SHAREPOINTE</p>
                <p style="margin:8px 0 0; color:#7f1d1d; font-size:13px;">{error}</p>
            </div>
            """
        elif link:
            status_html = f"""
            <div style="background:#dcfce7; border-left:4px solid #16a34a; padding:16px; border-radius:8px; margin:16px 0;">
                <p style="margin:0; color:#166534; font-weight:600;">✅ DOKUMENT ÚSPEŠNE NÁJDENÝ</p>
                <p style="margin:8px 0 0; color:#14532d; font-size:13px; word-break:break-all;">Link: {link}</p>
            </div>
            """
        else:
            status_html = """
            <div style="background:#fef3c7; border-left:4px solid #f59e0b; padding:16px; border-radius:8px; margin:16px 0;">
                <p style="margin:0; color:#92400e; font-weight:600;">⚠️ DOKUMENT NENÁJDENÝ</p>
                <p style="margin:8px 0 0; color:#78350f; font-size:13px;">Skontroluj SharePoint pred odoslaním notifikácie.</p>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html lang="sk">
        <head>
        <meta charset="UTF-8">
        </head>
        <body style="margin:0; padding:0; background:#ffffff; font-family:Segoe UI, Roboto, Arial, sans-serif;">
          <div style="padding:24px;">
            <div style="max-width:640px; margin:0 auto; background:#ffffff; border-radius:12px;
                        box-shadow:0 2px 8px rgba(0,0,0,.06); padding:24px; color:#1f2937;">
              <h1 style="font-size:20px; font-weight:700; margin:0 0 8px;">{safe_title}</h1>
              <p style="color:#6b7280; margin:0 0 16px; font-size:14px;">
                Testovací email - notifikácia bude odoslaná zajtra ({days} dní)
              </p>

              {status_html}

              <div style="background:#f9fafb; border-radius:8px; padding:16px; margin:16px 0;">
                <p style="margin:0 0 8px; font-weight:600; font-size:14px;">📋 Informácie:</p>
                <p style="margin:4px 0; font-size:13px; color:#4b5563;">
                  <strong>Značka:</strong> {znacka}<br>
                  <strong>Názov:</strong> {nazov_stavby}<br>
                  <strong>Odoslanie:</strong> Zajtra
                </p>
              </div>

              <p style="color:#9ca3af; font-size:12px; margin-top:24px;">
                Toto je automatický testovací email pre kontrolu pred odoslaním.
              </p>
            </div>
          </div>
        </body>
        </html>
        """

    def buildNotifiactionBody(self, znacka: str, nazov_stavby: str, link: str | None, days: int = 20) -> str:
        safe_title = f"{znacka} — {nazov_stavby}"

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
        else:
            button_html = """
            <p style="margin:0 0 16px; color:#dc2626; background:#fee2e2; padding:12px; border-radius:8px;">
                Dokument sa nepodarilo nájsť na SharePointe.
            </p>
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
                Od odoslania vyjadrenia prešlo <strong>{days} dní</strong>.
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
            znacka = item["znacka"]
            nazov_stavby = item["nazovstavby"]

            first_date = date.fromisoformat(item["firstnotification"])
            second_date = date.fromisoformat(item["secondnotification"])

            # Testovanie deň pred notifikáciami
            test_first_date = first_date - timedelta(days=1)
            test_second_date = second_date - timedelta(days=1)

            # TEST pred prvou notifikáciou
            if today == test_first_date:
                print(f"[TEST] Testujem pre {znacka} (prvá notifikácia zajtra)")
                try:
                    sharepoint_link = self.getSharePointLink(znacka, nazov_stavby)
                    test_email_sent = self.emailSender.sendEmail(
                        f"🧪 TEST: {znacka} - {nazov_stavby}",
                        self.buildTestEmailBody(znacka, nazov_stavby, sharepoint_link, 20),
                        to_email="dvorsky@elprokan.sk"
                    )

                except Exception as e:
                    error_msg = f"Chyba pri teste: {str(e)}"
                    print(f"[TEST ERROR] {error_msg}")
                    self.emailSender.sendEmail(
                        f"❌ TEST ERROR: {znacka}",
                        self.buildTestEmailBody(znacka, nazov_stavby, None, 20, error=error_msg),
                        to_email="dvorsky@elprokan.sk"
                    )
                    self.logAction(id_, "testFirstNotification", "ERROR", error_msg)

            # TEST pred druhou notifikáciou
            elif today == test_second_date:
                print(f"[TEST] Testujem pre {znacka} (druhá notifikácia zajtra)")
                try:
                    sharepoint_link = self.getSharePointLink(znacka, nazov_stavby)
                    test_email_sent = self.emailSender.sendEmail(
                        f"🧪 TEST: {znacka} - {nazov_stavby}",
                        self.buildTestEmailBody(znacka, nazov_stavby, sharepoint_link, 40),
                        to_email="dvorsky@elprokan.sk"
                    )
                except Exception as e:
                    error_msg = f"Chyba pri teste: {str(e)}"
                    print(f"[TEST ERROR] {error_msg}")
                    self.emailSender.sendEmail(
                        f"❌ TEST ERROR: {znacka}",
                        self.buildTestEmailBody(znacka, nazov_stavby, None, 40, error=error_msg),
                        to_email="dvorsky@elprokan.sk"
                    )
                    self.logAction(id_, "testSecondNotification", "ERROR", error_msg)

            # SKUTOČNÁ prvá notifikácia
            elif today == first_date:
                sharepoint_link = self.getSharePointLink(znacka, nazov_stavby)
                firstNotificationCheck = self.emailSender.sendEmail(
                    f"{znacka} - {nazov_stavby}",
                    self.buildNotifiactionBody(znacka, nazov_stavby, sharepoint_link, days=20)
                )

                if firstNotificationCheck:
                    self.logAction(id_, "firstNotification")
                else:
                    self.logAction(id_, "firstNotification", "ERROR", self.emailSender.error_message)

            # SKUTOČNÁ druhá notifikácia (jedine tu sa nastaví done=True)
            elif today == second_date:
                sharepoint_link = self.getSharePointLink(znacka, nazov_stavby)
                secondNotification = self.emailSender.sendEmail(
                    f"{znacka} - {nazov_stavby}",
                    self.buildNotifiactionBody(znacka, nazov_stavby, sharepoint_link, days=40)
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


if __name__ == "__main__":
    n = NotificationService()
    n.checkAndNotify()