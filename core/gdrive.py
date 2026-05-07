import os
import socket
from pathlib import Path
from datetime import datetime

# 抑制 Google API 日誌
import logging
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

def get_drive_service():
    """取得 Google Drive API 授權物件 (OAuth 2.0)"""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("[WARN] 缺少 Google API 套件，跳過上傳 (下次啟動會自動安裝)")
        return None

    SCOPES = ['https://www.googleapis.com/auth/drive']
    root_dir = Path(__file__).parent.parent
    creds_file = root_dir / "credentials.json"
    token_file = root_dir / "token.json"
    creds = None

    # 如果有之前的授權檔 (token.json)，直接讀取
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except Exception:
            pass

    # 若沒有授權檔或已過期，則重新要求授權
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"[WARN] 憑證刷新失敗，需重新登入：{e}")
                creds = None

        if not creds:
            if not creds_file.exists():
                print("[INFO] 未找到 credentials.json，跳過雲端備份。")
                return None
            
            print("\n[SETUP] 首次設定 Google Drive，將開啟瀏覽器進行授權...")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
                # 使用固定 port 避免防火牆問題，或設為 0 自動尋找
                creds = flow.run_local_server(port=0)
            except Exception as e:
                print(f"[ERR] 瀏覽器授權失敗：{e}")
                return None

        # 將成功的授權存下來，以後就不必再登入了
        try:
            token_file.write_text(creds.to_json())
        except Exception as e:
            print(f"[WARN] 無法儲存 token.json：{e}")

    try:
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"[ERR] Google Drive 建立服務失敗：{e}")
        return None

def find_or_create_folder(service, folder_name, parent_id):
    """在指定的 parent_id 下尋找同名資料夾，若無則建立"""
    try:
        # 尋找是否已存在
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
        response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = response.get('files', [])
        
        if files:
            return files[0].get('id')
            
        # 若不存在則建立
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')
    except Exception as e:
        print(f"[ERR] 建立資料夾 {folder_name} 失敗：{e}")
        return None

def upload_or_update_file(service, file_path, parent_id):
    """上傳檔案至指定資料夾，若同名檔案已存在則覆蓋更新"""
    try:
        from googleapiclient.http import MediaFileUpload
        import mimetypes
        
        file_path = Path(file_path)
        if not file_path.exists():
            return False
            
        file_name = file_path.name
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = 'application/octet-stream'

        # 檢查是否已存在同名檔案
        query = f"name='{file_name}' and '{parent_id}' in parents and trashed=false"
        response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = response.get('files', [])
        
        media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
        
        if files:
            # 覆蓋更新
            file_id = files[0].get('id')
            service.files().update(fileId=file_id, media_body=media).execute()
            print(f"    [OK] 已更新：{file_name}")
        else:
            # 全新上傳
            file_metadata = {'name': file_name, 'parents': [parent_id]}
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f"    [OK] 已上傳：{file_name}")
            
        return True
    except Exception as e:
        print(f"    [ERR] 上傳 {file_path.name} 失敗：{e}")
        return False

def backup_to_drive(audio_path, pdf_path, html_path, txt_path, meeting_title=None):
    """
    執行完整的 Google Drive 備份流程
    資料夾架構：[指定總資料夾] -> [上傳日期_電腦名稱] -> [AI摘要會議名稱]
    """
    service = get_drive_service()
    if not service:
        return
        
    print("\n==================================================")
    print("  ☁️ 正在備份至 Google Drive...")
    print("==================================================")
    
    # 根資料夾 ID（由使用者提供）
    ROOT_FOLDER_ID = "1tA3U4W2R9jO2UpViCR1cSXwFpPNRnEUQ"
    
    # 1. 建立 [上傳日期_使用者名稱] 資料夾
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        user_name = os.getlogin()
    except:
        user_name = "User"
        
    level1_name = f"{today_str}_{user_name}"
    level1_id = find_or_create_folder(service, level1_name, ROOT_FOLDER_ID)
    if not level1_id:
        return
        
    # 2. 建立 [AI摘要會議名稱] 資料夾
    # 優先順序：AI 產出的標題 -> 原始音檔名稱 -> "未命名會議"
    # 確保名稱不包含非法字元
    if meeting_title and meeting_title.strip():
        level2_name = meeting_title.strip().replace("/", "_").replace("\\", "_")
    else:
        level2_name = Path(audio_path).stem if audio_path else "未命名會議"

    level2_id = find_or_create_folder(service, level2_name, level1_id)
    if not level2_id:
        return
        
    print(f"[INFO] 雲端備份路徑：{level1_name} / {level2_name}")
    
    # 3. 上傳檔案
    files_to_upload = [pdf_path, html_path, txt_path, audio_path]
    success_count = 0
    for f in files_to_upload:
        if f and Path(f).exists():
            if upload_or_update_file(service, f, level2_id):
                success_count += 1
                
    print(f"\n[OK] 雲端備份完成，共上傳/更新 {success_count} 個檔案！")
