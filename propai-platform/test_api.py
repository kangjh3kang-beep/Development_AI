import requests
import json
import os

key = os.environ.get("MOLIT_API_KEY", "") 
# It might be in the .env file.
from dotenv import load_dotenv
load_dotenv(".env")
key = os.environ.get("APPLYHOME_API_KEY", "") or os.environ.get("MOLIT_API_KEY", "")

url = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getUrbtyOfctlLttotPblancDetail"
params = {"page": 1, "perPage": 300, "serviceKey": key}
resp = requests.get(url, params=params)
data = resp.json().get("data", [])

target_id = None
for r in data:
    if "더하이브" in r.get("HOUSE_NM", ""):
        print("Found:", r.get("HOUSE_NM"), "ID:", r.get("HOUSE_MANAGE_NO"))
        target_id = r.get("HOUSE_MANAGE_NO")
        break

if target_id:
    url_mdl = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getUrbtyOfctlLttotPblancMdl"
    resp_mdl = requests.get(url_mdl, params={"page": 1, "perPage": 50, "serviceKey": key, "cond[HOUSE_MANAGE_NO::EQ]": target_id})
    print(json.dumps(resp_mdl.json().get("data", []), ensure_ascii=False, indent=2))
