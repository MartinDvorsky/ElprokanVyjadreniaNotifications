import msal
import requests
import os
from typing import Optional


class GraphEmailSender:
    """
    Email sender používajúci Microsoft Graph API namiesto SMTP.
    Funguje s 2FA a je odporúčaný Microsoftom.
    Použije rovnaké credentials ako SharePoint manager.
    """

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, from_email: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.from_email = from_email
        self.error_message = ""

        if not all([tenant_id, client_id, client_secret, from_email]):
            raise ValueError("Chýbajú potrebné premenné pre Graph API")

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


# Príklad použitia (pre testovanie):
if __name__ == "__main__":
    # Test s environment premennými

    #from dotenv import load_dotenv
    #load_dotenv()

    sender = GraphEmailSender(
        tenant_id=os.environ.get('TENANT_ID'),
        client_id=os.environ.get('CLIENT_ID'),
        client_secret=os.environ.get('CLIENT_SECRET'),
        from_email=os.environ.get('EMAIL')
    )

    test_html = """
    <html>
    <body>
        <h1>Test email</h1>
        <p>Toto je testovací email z Graph API.</p>
    </body>
    </html>
    """

    success = sender.sendEmail(
        subject="🧪 Test Graph API",
        body=test_html,
        to_email="dvorsky@elprokan.sk"
    )

    if success:
        print("✓ Email úspešne odoslaný")
    else:
        print(f"✗ Chyba: {sender.error_message}")