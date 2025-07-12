import os
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def start_flow(user_id: int):
    flow = Flow.from_client_secrets_file(
        'credentials.json',
        scopes=SCOPES,
        redirect_uri='urn:ietf:wg:oauth:2.0:oob'
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    return flow, auth_url

def finish_flow(flow: Flow, code: str):
    flow.fetch_token(code=code)
    creds = flow.credentials
    service = build('drive', 'v3', credentials=creds)
    return service

def list_files(service):
    results = service.files().list(
        pageSize=10,
        fields="files(id, name)",
        q="mimeType='application/pdf' or mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document' or mimeType='text/plain'"
    ).execute()
    items = results.get('files', [])
    return [(item['id'], item['name']) for item in items]

def download_file(service, file_id, dest_path):
    request = service.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as f:
        downloader = build('media', 'v1', credentials=service._http.credentials).media_request(
            request, f
        )
        downloader.execute()
