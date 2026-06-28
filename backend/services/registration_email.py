import html
import os

import resend


def send_registration_request(user, approval_token: str) -> str:
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    sender = os.environ.get("EMAIL_FROM", "").strip()
    recipient = os.environ.get("ADMIN_NOTIFICATION_EMAIL", "").strip()
    base_url = os.environ.get("APP_BASE_URL", "https://nikkeari.cc").rstrip("/")
    if not api_key or not sender or not recipient:
        raise RuntimeError("Registration email settings are incomplete")

    resend.api_key = api_key
    approval_url = (
        f"{base_url}/approve-registration"
        f"?user={user.id}&token={approval_token}"
    )
    provider_name = html.escape(user.provider_name or "未入力")
    play_server = html.escape(user.play_server or "未入力")
    game_start_date = html.escape(
        str(user.game_start_date) if user.game_start_date else "未入力"
    )
    email = html.escape(user.email)
    response = resend.Emails.send({
        "from": sender,
        "to": [recipient],
        "subject": f"【にけあり！】スタッフ登録依頼: {provider_name}",
        "html": (
            "<h2>スタッフ登録依頼</h2>"
            f"<p><strong>メールアドレス:</strong> {email}</p>"
            f"<p><strong>指揮官名:</strong> {provider_name}</p>"
            f"<p><strong>ゲーム開始日:</strong> {game_start_date}</p>"
            f"<p><strong>プレイサーバー:</strong> {play_server}</p>"
            "<p>次のページを開き、内容を確認してから承認してください。</p>"
            f'<p><a href="{html.escape(approval_url)}">登録依頼を確認する</a></p>'
            "<p>このリンクの有効期限は72時間です。</p>"
        ),
        "text": (
            "スタッフ登録依頼\n"
            f"メールアドレス: {user.email}\n"
            f"指揮官名: {user.provider_name or '未入力'}\n"
            f"ゲーム開始日: {user.game_start_date or '未入力'}\n"
            f"プレイサーバー: {user.play_server or '未入力'}\n\n"
            f"登録依頼を確認する: {approval_url}\n"
            "このリンクの有効期限は72時間です。"
        ),
    })
    return response["id"]


def send_registration_approved(user) -> str | None:
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    sender = os.environ.get("EMAIL_FROM", "").strip()
    base_url = os.environ.get("APP_BASE_URL", "https://nikkeari.cc").rstrip("/")
    if not api_key or not sender:
        return None
    resend.api_key = api_key
    response = resend.Emails.send({
        "from": sender,
        "to": [user.email],
        "subject": "【にけあり！】スタッフ登録が承認されました",
        "html": (
            "<h2>スタッフ登録が承認されました</h2>"
            "<p>登録時のメールアドレスとパスワードでログインできます。</p>"
            f'<p><a href="{html.escape(base_url)}/secret-login">ログインする</a></p>'
        ),
        "text": (
            "スタッフ登録が承認されました。\n"
            "登録時のメールアドレスとパスワードでログインできます。\n"
            f"{base_url}/secret-login"
        ),
    })
    return response["id"]
