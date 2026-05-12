from arcgis.gis import GIS
import requests
import pandas as pd
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
gis = GIS("home")

patch_table_item = gis.content.get('hosted_layer_id_here')
patch_table = patch_table_item.tables[0]
api_url ="https://content.esri.com/patch_notification/patches.json"
patch_list = []
target_version = "11.5"
new_vals = []

try:
    api = requests.get(api_url)
    data = api.json()
    for product in data.get("Product", []):
        version = product.get("version")

        if version == target_version:
            for patch in product.get("patches", []):
                op_sys = patch.get("Platform")
                if "windows" in op_sys.lower():
                    patch_name = patch.get("Name")
                    sys_dirty = patch.get("Products")
                    reg_pat = r"\s*,\s*\[?ArcGIS Enterprise\]?|\[?ArcGIS Enterprise\]?\s*,\s*|\[?ArcGIS Enterprise\]?"
                    system = re.sub(reg_pat, "", sys_dirty).strip()
                    if patch.get("Critical") == "security":
                        sec_up = "yes"
                    else:
                        sec_up = "no"
                    qfe_id = patch.get("QFE_ID")
                    rel_date = patch.get("ReleaseDate")
                    installed = "no"
                    patch_list.append([version, patch_name, system, op_sys, sec_up, rel_date, qfe_id, installed])
except requests.exceptions.RequestException as e:
    print(f"error: {e}")

df = pd.DataFrame(patch_list, columns=['age_version', 'patchname', 'component', 'op_sys', 'critical', 'rel_date', 'qfe_id', 'installed'])

ht_df = patch_table.query().df
exist_ids = ht_df['qfe_id'].tolist() if not ht_df.empty else []
miss_df= df[~df['qfe_id'].isin(exist_ids)].copy()
miss_df = miss_df.where(pd.notnull(miss_df), None)

for index, row in miss_df.iterrows():
    clean_row = {k: v for k, v in row.items()}
    new_vals.append({"attributes": clean_row})

if new_vals:
    result = patch_table.edit_features(adds=new_vals)

email_patches = patch_table.query(where="installed = 'no'")
email_df = email_patches.df
email_patch_name = email_df['patchname'].tolist()

portal_admin_url = f"{gis._url.replace('/sharing/rest', '')}/portaladmin/system/emailSettings"
params = {
    'f':'json',
    'token': gis._con.token
}

response = requests.get(portal_admin_url, params)
if response.status_code == 200:
    email_config = response.json()

msg = MIMEMultipart("html")
msg["Subject"] = "Enterprise Patches to Install"
msg["From"] = email_config["mailFrom"]
msg["To"] = "your_email@example.net"

bullet_list = "".join([f"<li>{val}</li>" for val in email_patch_name])
body = f"""
<html>
    <body>
        <p>Here are the available patches to install:</p>
        <ul>
            {bullet_list}
        </ul>
    </body>
</html>
"""
msg.attach(MIMEText(body, "html"))
with smtplib.SMTP(email_config["smtpHost"], email_config["smtpPort"]) as server:
        server.send_message(msg)