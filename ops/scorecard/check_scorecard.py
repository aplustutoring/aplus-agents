import requests, os, json
from dotenv import load_dotenv
load_dotenv(".env")
key = os.getenv("MONDAY_API_KEY")
headers = {"Authorization": key, "Content-Type": "application/json"}
query = '{ boards(ids: [18402267902]) { items_page(limit: 50) { cursor items { id name group { title } column_values { id text } } } } }'
r = requests.post("https://api.monday.com/v2", json={"query": query}, headers=headers)
data = r.json()
items = data["data"]["boards"][0]["items_page"]["items"]
cursor = data["data"]["boards"][0]["items_page"].get("cursor")
if cursor:
    q2 = 'query ($c: String!) { next_items_page(cursor: $c, limit: 50) { items { id name group { title } column_values { id text } } } }'
    r2 = requests.post("https://api.monday.com/v2", json={"query": q2, "variables": {"c": cursor}}, headers=headers)
    items.extend(r2.json()["data"]["next_items_page"]["items"])

auto_map = {
    "11483245331": "hours_attended -> company attended hrs",
    "11483189029": "package_units_sold -> weekly pkg units from TW invoices",
    "11408675886": "cancellation_rate -> company cancel rate %",
    "11487301255": "new_students -> first lesson count",
    "11487307948": "package_hours_sold -> FY invoice pkg hrs (July 1 - Sat)",
    "11487311080": "charter_deals -> HubSpot Charter Mktg Proposal+Negotiating",
    "11521747780": "pilots_signed -> HubSpot Charter Mktg Closed Won",
    "11521873481": "post_lesson_72hr -> company 72hr missed %",
}

grp = ""
for item in items:
    g = item["group"]["title"]
    if g != grp:
        grp = g
        print(f"\n{g}")
        print("=" * 110)
    target = ""
    val = ""
    for cv in item["column_values"]:
        if cv["id"] == "text_mm13s9jw" and cv.get("text"):
            target = cv["text"]
        if cv["id"] == "numeric_mm1gbqpe" and cv.get("text"):
            val = cv["text"]
    iid = item["id"]
    if iid in auto_map:
        tag = "AUTO"
        mapping = auto_map[iid]
    else:
        tag = "MANUAL"
        mapping = "n/a"
    print(f"  [{tag:6}] ID {iid:15} | {item['name']:52} | Target: {target:25} | Val: {val}")
    if tag == "AUTO":
        print(f"           Script mapping: {mapping}")
