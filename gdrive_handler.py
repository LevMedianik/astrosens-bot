import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

# Запуск OAuth flow для конкретного пользователя
if not os.path.exists('credentials.json'):
    creds_json = os.getenv('CREDENTIALS_JSON')
    if creds_json:
        with open('credentials.json', 'w') as f:
            f.write(creds_json)

# Завершение OAuth flow
def finish_flow(flow, code):
    flow.fetch_token(code=code)
    creds = flow.credentials
    return build('drive', 'v3', credentials=creds)

# Получение списка файлов
def list_files(service):
    results = service.files().list(
        pageSize=10,
        fields="files(id, name, mimeType)"
    ).execute()
    items = results.get('files', [])
    return [(item['id'], item['name']) for item in items if item['mimeType'] in [
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain'
    ]]

# Загрузка выбранного файла
def download_file(service, file_id, dest_path):
    request = service.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
