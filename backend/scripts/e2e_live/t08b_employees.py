"""Employee checks on the live API with ZZTEST data only (a formula-looking name is used to test spreadsheet exports)."""
import json
import os
import secrets

from zz_lib import SC, IDS, Api, rec

created = json.load(open(os.path.join(SC, "zz_created.json")))


def chk(name, ok, detail="", sev="high"):
    rec("directories", name, "PASS" if ok else "FAIL", detail, None if ok else sev)


admin = Api("admin")
admin.login()
operator = Api("operator")
operator.login()
A = IDS["sections"]["A"]
r = admin.patch(f"/sections/{A}", json={"is_archived": False})
print("unarchive ZZTEST-Section-A ->", r.status_code)
tag = secrets.token_hex(3)
r = admin.post("/employees", json={"tab_number": f"ZZTEST-E{tag}", "full_name": "=1+1 ZZTEST", "section_id": A})
chk("create an employee whose name looks like a spreadsheet formula", r.status_code == 201, r.text[:100])
emp = r.json().get("id")
created.setdefault("employees", []).append(emp)
r = admin.post("/employees", json={"tab_number": f"ZZTEST-E{tag}", "full_name": "dup"})
chk("a duplicate tab number is refused (409)", r.status_code == 409, f"status {r.status_code}", "medium")
r = operator.patch(f"/employees/{emp}", json={"position": "ZZTEST position"})
chk("operator edits an employee", r.status_code == 200, f"status {r.status_code} {r.text[:80]}", "medium")
r = operator.delete(f"/employees/{emp}")
chk("operator deletes an employee (organization.delete is granted to operator)", r.status_code in (204, 409), f"status {r.status_code}", "low")
if r.status_code == 204:
    created["employees"].remove(emp)
json.dump(created, open(os.path.join(SC, "zz_created.json"), "w"))
