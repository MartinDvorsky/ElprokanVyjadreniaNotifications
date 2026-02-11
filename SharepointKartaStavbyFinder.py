import msal
import requests
import os

from typing import Optional, List, Dict

#from dotenv import load_dotenv
#load_dotenv()


TENANT_ID = os.environ['TENANT_ID']
CLIENT_ID = os.environ['CLIENT_ID']
CLIENT_SECRET = os.environ['CLIENT_SECRET']
SHAREPOINT_SITE_URL = os.environ['SHAREPOINT_SITE_URL']
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')


class SharePointManager:
    """Manažér pre prácu so SharePoint súbormi cez Microsoft Graph API"""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, openai_api_key: Optional[str] = None):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.openai_api_key = openai_api_key
        self.access_token: Optional[str] = None
        self.site_id: Optional[str] = None
        self.base_graph_url = "https://graph.microsoft.com/v1.0"

    def get_access_token(self) -> bool:
        """
        Získa access token pre Microsoft Graph API

        Returns:
            bool: True ak je token úspešne získaný, inak False
        """
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=authority,
            client_credential=self.client_secret
        )

        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" in result:
            self.access_token = result["access_token"]
            print("✓ Access token úspešne získaný")
            return True
        else:
            print(f"✗ Chyba pri získavaní tokenu: {result.get('error_description')}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Vráti HTTP headers s autorizáciou"""
        return {"Authorization": f"Bearer {self.access_token}"}

    def test_connection(self) -> bool:
        """
        Otestuje pripojenie k Microsoft Graph API

        Returns:
            bool: True ak je pripojenie úspešné
        """
        print("\n=== Test pripojenia ===")
        endpoint = f"{self.base_graph_url}/sites"
        response = requests.get(endpoint, headers=self._get_headers())

        success = response.status_code == 200
        print(f"Test prístupu k sites: {response.status_code} {'✓' if success else '✗'}")

        if not success:
            print(f"Odpoveď: {response.text}")

        return success

    def get_site_id(self, site_url: str) -> Optional[str]:
        """
        Získa ID SharePoint situ

        Args:
            site_url: URL SharePoint situ (napr. https://firma.sharepoint.com/sites/mysite)

        Returns:
            str: Site ID alebo None pri chybe
        """
        parts = site_url.replace("https://", "").split("/", 1)
        hostname = parts[0]
        site_path = "/" + parts[1] if len(parts) > 1 else ""

        endpoint = f"{self.base_graph_url}/sites/{hostname}:{site_path}"

        print(f"\nZískavam Site ID z: {endpoint}")
        response = requests.get(endpoint, headers=self._get_headers())

        if response.status_code == 200:
            self.site_id = response.json()["id"]
            print(f"✓ Site ID získané: {self.site_id}")
            return self.site_id
        else:
            print(f"✗ Chyba pri získavaní Site ID: {response.status_code}")
            print(f"Odpoveď: {response.text}")
            return None

    def _select_folder_with_ai_v2(self, folders: List[Dict], znacka: str, nazov_stavby: str) -> Optional[Dict]:
        """
        Použije OpenAI API na výber správneho priečinka
        Berie do úvahy aj xlsx súbory v každom priečinku

        Args:
            folders: Zoznam nájdených priečinkov (s info o xlsx súboroch)
            znacka: Značka stavby (napr. "EP25005/2025")
            nazov_stavby: Názov stavby

        Returns:
            Dict: Vybraný priečinok alebo None
        """
        if not self.openai_api_key:
            print("⚠ OpenAI API kľúč nie je nastavený, vraciam prvý priečinok")
            return folders[0]

        # Vytvor detailný zoznam priečinkov s xlsx súbormi
        folders_list = []
        for i, f in enumerate(folders):
            folder_info = f"{i + 1}. {f['name']}"
            if f['xlsx_count'] > 0:
                folder_info += f"\n   XLSX súbory ({f['xlsx_count']}):"
                for xf in f['xlsx_files']:
                    folder_info += f"\n     - {xf}"
            else:
                folder_info += "\n   (žiadne XLSX súbory)"
            folders_list.append(folder_info)

        folders_text = "\n".join(folders_list)

        prompt = f"""Máš zoznam priečinkov zo SharePointa a potrebuješ vybrať ten správny na základe značky a názvu stavby.

Značka stavby: {znacka}
Názov stavby: {nazov_stavby}

Nájdené priečinky:
{folders_text}

Úloha: Vyber priečinok, ktorý:
1. PRIORITNE obsahuje súbor "karta stavby" s touto značkou (napr. "karta stavby - {znacka.split('/')[0]}.xlsx")
2. Najlepšie zodpovedá danej značke a názvu stavby
3. Názov stavby sa môže mierne líšiť (skratky, preklepy, atď.)

DÔLEŽITÉ: Ak značka obsahuje rok (napr. "ZP12715/2024"), uprednostni priečinok ktorý obsahuje tento rok v názve alebo v štruktúre cesty.

Odpoveď MUSÍ byť len jedno číslo (1-{len(folders)}) bez akéhokoľvek iného textu alebo vysvetlenia."""

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system",
                         "content": "Si pomocník pre výber správneho priečinka. Odpovedaj len číslom."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0,
                    "max_tokens": 10
                }
            )

            if response.status_code == 200:
                result = response.json()
                choice_text = result["choices"][0]["message"]["content"].strip()
                choice_num = int(''.join(filter(str.isdigit, choice_text)))

                if 1 <= choice_num <= len(folders):
                    selected = folders[choice_num - 1]
                    print(f"🤖 AI vybralo: {selected['name']}")
                    return selected
                else:
                    print(f"⚠ AI vrátilo neplatné číslo ({choice_num}), vraciam prvý priečinok")
                    return folders[0]
            else:
                print(f"⚠ Chyba OpenAI API: {response.status_code}, vraciam prvý priečinok")
                return folders[0]

        except Exception as e:
            print(f"⚠ Chyba pri volaní AI: {e}, vraciam prvý priečinok")
            return folders[0]

    def _select_xlsx_with_ai(self, xlsx_files: List[Dict], znacka: str, nazov_stavby: str) -> Optional[Dict]:
        """
        Použije OpenAI API na výber správneho XLSX súboru (prioritne Karta stavby)

        Args:
            xlsx_files: Zoznam nájdených XLSX súborov
            znacka: Značka stavby
            nazov_stavby: Názov stavby

        Returns:
            Dict: Vybraný súbor alebo None
        """
        if not self.openai_api_key:
            print("⚠ OpenAI API kľúč nie je nastavený, vraciam prvý súbor")
            return xlsx_files[0]

        # OPRAVA: Použij cestu namiesto len názvu súboru
        files_list = "\n".join([
            f"{i + 1}. {f.get('path', f['name'])}"
            for i, f in enumerate(xlsx_files)
        ])

        # Odstrániť rok zo značky pre lepšie porovnanie
        znacka_clean = znacka.split('/')[0]

        prompt = f"""Máš zoznam Excel súborov (.xlsx) zo SharePointa a potrebuješ vybrať správny súbor "Karta stavby" alebo hlavný súbor pre správu stavby.

    Značka stavby: {znacka_clean}
    Názov stavby: {nazov_stavby}

    Nájdené súbory (s cestou):
    {files_list}

    Úloha: Vyber súbor, ktorý je hlavným súborom pre správu tejto stavby.

    PRIORITA (od najvyššej po najnižšiu):
    1. Súbor s názvom obsahujúcim "karta stavby" + značka stavby
    2. Súbor s názvom obsahujúcim "karta stavby"
    3. Súbor s názvom obsahujúcim "tabulka" + značka stavby v akejkoľvek ceste
    4. Akýkoľvek súbor v adresári "ZIADOSTI" so značkou stavby

    VYLÚČ:
    - Súbory s názvom obsahujúcim "ORS tabulka", "navratky", "vypis materialu", "bodove supisy", "ZOM", "Technicke_udaje", "kalkulacka", "Merne", "Poplatky"
    - Súbory v adresároch: "Oznamenia", "F - Bodove supisy", "PL", "Prepočet"

    Odpoveď MUSÍ byť len jedno číslo (1-{len(xlsx_files)}) bez akéhokoľvek iného textu alebo vysvetlenia."""

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system",
                         "content": "Si pomocník pre výber správneho Excel súboru. Odpovedaj len číslom."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0,
                    "max_tokens": 1000
                }
            )

            if response.status_code == 200:
                result = response.json()
                choice_text = result["choices"][0]["message"]["content"].strip()
                choice_num = int(''.join(filter(str.isdigit, choice_text)))

                if 1 <= choice_num <= len(xlsx_files):
                    selected = xlsx_files[choice_num - 1]
                    selected_path = selected.get('path', selected['name'])
                    print(f"🤖 AI vybralo súbor: {selected_path}")
                    return selected
                else:
                    print(f"⚠ AI vrátilo neplatné číslo ({choice_num}), vraciam prvý súbor")
                    return xlsx_files[0]
            else:
                print(f"⚠ Chyba OpenAI API: {response.status_code}, vraciam prvý súbor")
                return xlsx_files[0]

        except Exception as e:
            print(f"⚠ Chyba pri volaní AI: {e}, vraciam prvý súbor")
            return xlsx_files[0]

    def find_folder_by_name(self, znacka: str, nazov_stavby: str = "") -> Optional[Dict]:
        """
        Nájde priečinok, ktorý obsahuje zadanú značku v názve
        Pri viacerých výsledkoch použije AI na výber správneho

        Args:
            znacka: Značka stavby (napr. "EP25005/2025" alebo "EP25005")
            nazov_stavby: Názov stavby pre lepšiu identifikáciu

        Returns:
            Dict: Informácie o priečinku alebo None ak sa nenašiel
        """
        if not self.site_id:
            print("✗ Najprv musíš získať Site ID")
            return None

        # Rozdeľ značku na samotnú značku a rok (ak existuje)
        znacka_parts = znacka.split('/')
        znacka_clean = znacka_parts[0]  # Napr. "EP25005"
        rok = znacka_parts[1] if len(znacka_parts) > 1 else None  # Napr. "2025"

        print(f"\nHľadám priečinok obsahujúci '{znacka_clean}'" + (f" (rok: {rok})" if rok else "") + "...")
        endpoint = f"{self.base_graph_url}/sites/{self.site_id}/drive/root/search(q='{znacka_clean}')"
        response = requests.get(endpoint, headers=self._get_headers())

        if response.status_code == 200:
            results = response.json().get("value", [])

            folders = [
                item for item in results
                if "folder" in item and znacka_clean.lower() in item["name"].lower()
            ]

            if not folders:
                print(f"✗ Priečinok obsahujúci '{znacka_clean}' sa nenašiel")
                return None

            # Odstránenie duplicít podľa názvu (case-insensitive) - ale ulož si všetky ID
            seen_names = {}
            unique_folders = []
            all_folder_ids = []  # Všetky priečinky s rovnakým názvom

            for folder in folders:
                folder_name_lower = folder['name'].lower()
                if folder_name_lower not in seen_names:
                    seen_names[folder_name_lower] = []
                    unique_folders.append(folder)
                seen_names[folder_name_lower].append(folder)

            # Pre každý unikátny názov ulož všetky jeho varianty
            for folder in unique_folders:
                folder_name_lower = folder['name'].lower()
                all_variants = seen_names[folder_name_lower]
                if len(all_variants) > 1:
                    print(f"  ℹ️ Našiel som {len(all_variants)} variantov priečinka '{folder['name']}'")
                    for variant in all_variants[1:]:
                        print(f"    - Duplicitný variant (ID: {variant['id']})")

            folders = unique_folders

            if len(folders) == 1:
                folder = folders[0]
                print(f"✓ Našiel som 1 priečinok: {folder['name']}")
                # Pridaj všetky varianty ako kandidátov
                folder['_all_candidates'] = seen_names[folder['name'].lower()]
            else:
                print(f"✓ Našiel som {len(folders)} unikátnych priečinkov")

                # NOVÉ: Získaj xlsx súbory pre každý priečinok
                folders_with_files = []
                for folder in folders:
                    folder_id = folder['id']
                    endpoint = f"{self.base_graph_url}/sites/{self.site_id}/drive/items/{folder_id}/children"
                    resp = requests.get(endpoint, headers=self._get_headers())

                    xlsx_files = []
                    if resp.status_code == 200:
                        items = resp.json().get("value", [])
                        xlsx_files = [
                            item['name'] for item in items
                            if "file" in item and item["name"].lower().endswith(".xlsx")
                        ]

                    folder['xlsx_files'] = xlsx_files
                    folder['xlsx_count'] = len(xlsx_files)
                    folder['_all_candidates'] = seen_names[folder['name'].lower()]
                    folders_with_files.append(folder)

                    print(f"  {len(folders_with_files)}. {folder['name']}")
                    print(f"     XLSX súborov: {len(xlsx_files)}")
                    if xlsx_files:
                        for xf in xlsx_files:
                            print(f"       - {xf}")

                # Použij AI na výber správneho priečinka (s informáciou o xlsx súboroch)
                folder = self._select_folder_with_ai_v2(folders_with_files, znacka, nazov_stavby)

            print(f"  ID: {folder['id']}")
            return folder
        else:
            print(f"✗ Chyba pri vyhľadávaní: {response.status_code}")
            print(response.text)
            return None

    def get_xlsx_files_from_folder(self, znacka: str, nazov_stavby: str = "",
                                   search_subfolders: bool = False,
                                   auto_select: bool = True) -> List[Dict]:
        """
        Nájde všetky .xlsx súbory v priečinku, ktorý obsahuje zadanú značku

        Args:
            znacka: Značka stavby (napr. "EP25005/2025")
            nazov_stavby: Názov stavby pre lepšiu identifikáciu priečinka
            search_subfolders: Či prehľadávať aj podpriečinky (default: False)
            auto_select: Či automaticky vybrať "Karta stavby" pomocou AI (default: True)

        Returns:
            List[Dict]: Zoznam .xlsx súborov (alebo len vybraný súbor ak auto_select=True)
        """
        folder = self.find_folder_by_name(znacka, nazov_stavby)
        if not folder:
            return []

        # Ulož si všetky nájdené priečinky (nie len vybraný)
        all_folders = folder.get('_all_candidates', [folder])

        def get_files_recursive(folder_id: str, path: str = "") -> List[Dict]:
            """Rekurzívne získa všetky xlsx súbory z priečinka a podpriečinkov"""
            endpoint = f"{self.base_graph_url}/sites/{self.site_id}/drive/items/{folder_id}/children"
            response = requests.get(endpoint, headers=self._get_headers())

            xlsx_files = []

            if response.status_code == 200:
                items = response.json().get("value", [])

                for item in items:
                    current_path = f"{path}/{item['name']}" if path else item['name']

                    # Ak je to xlsx súbor, pridaj ho
                    if "file" in item and item["name"].lower().endswith(".xlsx"):
                        item['path'] = current_path
                        xlsx_files.append(item)

                    # Ak je to priečinok a chceme prehľadávať podpriečinky, rekurzívne prehľadaj
                    elif "folder" in item and search_subfolders:
                        print(f"  📁 Prehľadávam podpriečinok: {current_path}")
                        xlsx_files.extend(get_files_recursive(item['id'], current_path))
            else:
                print(f"✗ Chyba pri získavaní súborov z {path or 'root'}: {response.status_code}")

            return xlsx_files

        # Skús všetky nájdené priečinky, až kým nenájdeš xlsx súbory
        xlsx_files = []
        for idx, folder_candidate in enumerate(all_folders):
            folder_id = folder_candidate["id"]
            folder_name = folder_candidate["name"]

            if idx == 0:
                print(f"Získavam súbory z priečinka{' (vrátane podpriečinkov)' if search_subfolders else ''}...")
            else:
                print(
                    f"\n⚠ V prvom priečinku sa nenašli xlsx súbory, skúšam ďalší kandidát ({idx + 1}/{len(all_folders)})...")
                print(f"  Priečinok: {folder_name}")

            xlsx_files = get_files_recursive(folder_id)

            if xlsx_files:
                print(f"✓ Našiel som {len(xlsx_files)} .xlsx súbor(ov) v: {folder_name}")
                break  # Našli sme súbory, netreba ďalej hľadať
            else:
                print(f"✓ Našiel som 0 .xlsx súbor(ov) v: {folder_name}")

        if xlsx_files:
            for i, file in enumerate(xlsx_files, 1):
                size_mb = file.get("size", 0) / (1024 * 1024)
                path = file.get('path', file.get('name'))
                print(f"  {i}. {path} ({size_mb:.2f} MB)")

            # Ak je viac súborov a auto_select je zapnutý, vyber správny pomocou AI
            if len(xlsx_files) > 1 and auto_select:
                print("\n🔍 Viacero súborov nájdených, používam AI na výber...")
                selected_file = self._select_xlsx_with_ai(xlsx_files, znacka, nazov_stavby)
                return [selected_file] if selected_file else xlsx_files

        return xlsx_files


if __name__ == "__main__":
    shp = SharePointManager(TENANT_ID, CLIENT_ID, CLIENT_SECRET, OPENAI_API_KEY)
    shp.get_access_token()
    shp.get_site_id(SHAREPOINT_SITE_URL)

    znacky_stavby = [
        ["EP25005/2025", "Raslavice – VN, TS, NN"],
        ["EP25042/2025", "Humenné, ul. Chemlonská - NN"],
        ["EP25030/2025", "Valaliky, 8 RD - NN"],
        ["EP25046/2025", "Zemplínske Hámre, 3RD - NN"],
        ["IP12455/2024", "PREŠOV-Sídl.Sekčov - úprava VN kábla V708 V707"],
        ["ZP12752/2024", "Košice, Nad jazerom, Napájadlá - VNR"],
        ["EP25034/2025", "7 HOUSES RESORT"],
        ["EP24002/2024", "HE | obytný súbor \"Suchý jarok\""],
        ["IP12663/2025", "V565/596 - Úprava VN z ES Košice IV"],
        ["EP25059/2025", "APARTMÁNOVÝ DOM STARÁ LESNÁ"],
        ["EP25001/2025", "Drienovská Nová Ves - VN, TS, NN"],
        ["EP25053/2025", "Snina, ul. kpt. Nálepku - NN"],
        ["EP25043/2025", "Jasenov, LHV Lúky, 76 RD - VN, TS, NN"],
        ["EP25040/2025", "Košice - OC Grunt, 37 OM - NN"],
        ["ZP12715/2024", "Kračúnovce - VN, TS, NN"],
        ["EP25028/2025", "Hanušovce nad Topľou, záhradné chatky - NN"],
        ["IP13028/2025", "Úprava V-425 a V-264 v obci Gemerská Hôrka"],
        ["E06/2024", "Essity Slovakia – zriadenie VN prípojky z ES Gemerská Hôrka"],
        ["ZP12476/2023", "Košice, Trieda SNP, UPJŠ - VNR(5K)"],
        ["EP25054/2025", "Drienov, ul. Šífnava, II. Etapa – TS, NN"]
    ]

    znacky_stavby2 = [
        ["IP12360/2024", "Čerhov - úprava NN a DP z TS4"]
    ]

    for znacka in znacky_stavby2:
        print(f"\n\n{'=' * 70}")
        print(f"=== Hľadám pre značku: {znacka[0]} | {znacka[1]} ===")
        print(f"{'=' * 70}")

        # Získaj súbory (auto-select vyberie správny súbor pomocou AI)
        files = shp.get_xlsx_files_from_folder(
            znacka[0],
            znacka[1],
            search_subfolders=True,
            auto_select=True
        )

        if files:
            selected_file = files[0]
            print(f"\n📄 Vybraný súbor: {selected_file['name']}")

            # webUrl je už v odpovedi z Graph API
            web_url = selected_file.get('webUrl')
            if web_url:
                print(f"🔗 SharePoint URL: {web_url}")
            else:
                print("⚠ webUrl nebola nájdená v odpovedi")