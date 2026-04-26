# Demo Login Credentials

## Hospital Accounts

| Portal | Username | Password | Notes |
|---|---|---|---|
| Hospital | `mgh` | `mgh123` | Massachusetts General Hospital |
| Hospital | `cleveland` | `clinic123` | Cleveland Clinic |
| Hospital | `jhopkins` | `johns123` | Johns Hopkins Hospital |

## Demo Patient Accounts

| Portal | Username | Password | Notes |
|---|---|---|---|
| Patient | `john_doe` | `pass123` | Demo patient |
| Patient | `jane_smith` | `pass123` | Demo patient |
| Patient | `bob_jones` | `pass123` | Demo patient |
| Patient | `alice_brown` | `pass123` | Demo patient |
| Patient | `david_chen` | `pass123` | Demo patient |

## Dataset-Backed Patient Accounts

- The app also auto-seeds a small set of Synthea patients into the portal.
- Username format: `synthea_<first 8 chars of Patient_ID>`
- Default password: `pass123`
- Example: patient ID `660bec03-...` becomes username `synthea_660bec03`

To list all current patient usernames in the local DB:

```powershell
@'
import sqlite3
con = sqlite3.connect("secondlife.db")
cur = con.cursor()
for row in cur.execute("select username, first_name, last_name, synthea_id from patient_accounts order by username"):
    print(row)
'@ | python -
```
