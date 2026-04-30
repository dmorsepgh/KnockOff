#!/usr/bin/env python3.12
"""Upload a video to YouTube using OAuth credentials."""

import argparse
import json
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

KEYS_DIR = Path.home() / ".keys"
CLIENT_SECRET = KEYS_DIR / "youtube-client-secret.json"
TOKEN_FILE = KEYS_DIR / "youtube-token.json"


def get_credentials():
    """Load and refresh OAuth credentials, or run fresh auth flow."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]

    creds = None

    if TOKEN_FILE.exists():
        try:
            token_data = json.loads(TOKEN_FILE.read_text())
            client_data = json.loads(CLIENT_SECRET.read_text())
            installed = client_data.get("installed", {})

            creds = Credentials(
                token=token_data.get("access_token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=installed.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=installed.get("client_id"),
                client_secret=installed.get("client_secret"),
                scopes=SCOPES,
            )

            if creds.expired:
                creds.refresh(Request())
        except Exception as e:
            print(f"  Existing token failed ({e}), re-authenticating...")
            creds = None

    if not creds or not creds.valid:
        print("  Opening browser for YouTube authentication...")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=8090)

    # Save token for next time
    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
    }
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))

    return creds


def upload(video_path, title, description, tags, privacy="unlisted", category="22"):
    """Upload video to YouTube."""
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category,
        },
        "status": {
            "privacyStatus": privacy,
        },
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    print(f"Uploading: {video_path}")
    print(f"Title: {title}")
    print(f"Privacy: {privacy}")

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    url = f"https://youtu.be/{video_id}"
    print(f"\nDone! {url}")
    return url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="Path to video file")
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--tags", default="", help="Comma-separated tags")
    ap.add_argument("--privacy", default="unlisted", choices=["public", "unlisted", "private"])
    args = ap.parse_args()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    upload(args.video, args.title, args.description, tags, args.privacy)


if __name__ == "__main__":
    main()
