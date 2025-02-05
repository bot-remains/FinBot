from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = "token.json"


def authenticate():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return creds


def upload(file_path, folder_id=None):
    creds = authenticate()
    drive_service = build("drive", "v3", credentials=creds)

    file_metadata = {
        "name": file_path.split("/")[-1],
        "parents": [folder_id] if folder_id else [],
    }

    media = MediaFileUpload(file_path, resumable=True)

    file = drive_service.files().create(body=file_metadata, media_body=media).execute()
    file_id = file.get("id")
    print(f"File ID: {file_id}")

    # Set file permissions to make it public
    set_permissions(drive_service, file_id)

    # Generate and print file link
    file_link = f"https://drive.google.com/file/d/{file_id}/view"
    print(f"File Link: {file_link}")


def set_permissions(drive_service, file_id):
    permission = {
        "type": "anyone",  # Anyone can access
        "role": "reader",  # Read-only access
    }
    drive_service.permissions().create(fileId=file_id, body=permission).execute()
    print("Permissions updated: Anyone can view the file.")


upload("./KH_1677_26-Jul-1995_806.pdf", "1h47wvxxcB2vxy-fdBfgd91VPTuu-sx9w")
