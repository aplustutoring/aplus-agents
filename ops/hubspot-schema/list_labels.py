import os, requests
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path.home() / "Documents/aplus-agents/.env")
tok = os.getenv("HUBSPOT_API_KEY","") or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN","")
r = requests.get("https://api.hubapi.com/crm/v4/associations/contacts/contacts/labels",
                 headers={"Authorization": f"Bearer {tok}"})
for l in r.json().get("results", []):
    print(f"typeId={l['typeId']}  label={l.get('label')!r}  category={l.get('category')}")
