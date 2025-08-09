import aiohttp
from .config import WA_BASE_URL, WA_TOKEN, WA_PHONE_ID


class WhatsAppService:
    def __init__(self, token: str | None = None, phone_id: str | None = None):
        self.token = token or WA_TOKEN
        self.phone_id = phone_id or WA_PHONE_ID

    async def send_text(self, to_msisdn: str, body: str) -> dict:
        url = f"{WA_BASE_URL}/{self.phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to_msisdn,
            "type": "text",
            "text": {"body": body},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                return {"status": resp.status, "data": data}


