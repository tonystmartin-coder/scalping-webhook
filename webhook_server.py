# ─────────────────────────────────────────────────────────────
#  Gold & Silver Scalping — Webhook TradingView → Telegram
#  Stack : Python 3.11+ · FastAPI · httpx · python-dotenv
# ─────────────────────────────────────────────────────────────
#  Installation :
#    pip install fastapi uvicorn httpx python-dotenv
#
#  Lancement :
#    uvicorn webhook_server:app --host 0.0.0.0 --port 8000
#
#  Variables d'environnement (fichier .env) :
#    TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIjklMnOpQrsTuVwXyZ
#    TELEGRAM_CHAT_ID=-100123456789
#    WEBHOOK_SECRET=mon_secret_fort_ici
# ─────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

# ── Config ────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID:   str = os.getenv("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET:     str = os.getenv("WEBHOOK_SECRET", "")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scalp-webhook")

# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="Gold & Silver Scalping Webhook",
    description="Reçoit les alertes TradingView et envoie des notifications Telegram",
    version="1.0.0",
)

# ── Schéma du payload TradingView ────────────────────────────
class AlertPayload(BaseModel):
    asset:  str            = Field(...,  example="XAUUSD")
    action: str            = Field(...,  example="buy")        # buy | sell
    price:  float          = Field(...,  example=3285.40)
    atr:    Optional[float]= Field(None, example=1.25)
    rsi:    Optional[float]= Field(None, example=52.3)
    tf:     Optional[str]  = Field(None, example="5")          # timeframe en minutes
    time:   Optional[str]  = Field(None, example="2025-05-30 14:32:00")
    alert:  Optional[str]  = Field(None, example="scalp_gold_buy")


# ── Helpers ───────────────────────────────────────────────────
ASSET_EMOJI = {
    "XAUUSD": "🥇", "GOLD": "🥇",
    "XAGUSD": "🥈", "SILVER": "🥈",
}
ACTION_EMOJI = {"buy": "🟢", "sell": "🔴"}
TF_LABEL = {
    "1": "M1", "5": "M5", "15": "M15",
    "30": "M30", "60": "H1", "240": "H4",
}

def build_telegram_message(p: AlertPayload) -> str:
    asset_emoji  = ASSET_EMOJI.get(p.asset.upper(), "📈")
    action_emoji = ACTION_EMOJI.get(p.action.lower(), "⚪")
    action_label = p.action.upper()
    tf_label     = TF_LABEL.get(str(p.tf), f"TF{p.tf}") if p.tf else "—"
    now_utc      = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    lines = [
        f"{asset_emoji} *{p.asset.upper()}* — {action_emoji} *{action_label}*",
        f"",
        f"💰 Prix      : `{p.price:.2f}`",
        f"⏱ Timeframe : `{tf_label}`",
    ]
    if p.atr is not None:
        tp = p.price + p.atr * 1.5 if p.action.lower() == "buy" else p.price - p.atr * 1.5
        sl = p.price - p.atr * 0.7 if p.action.lower() == "buy" else p.price + p.atr * 0.7
        lines += [
            f"📐 ATR       : `{p.atr:.2f}`",
            f"🎯 TP estimé : `{tp:.2f}`",
            f"🛑 SL estimé : `{sl:.2f}`",
        ]
    if p.rsi is not None:
        rsi_warn = " ⚠️ sur-achat"  if p.rsi > 70 else \
                   " ⚠️ sur-vente"  if p.rsi < 30 else ""
        lines.append(f"📊 RSI(7)    : `{p.rsi:.1f}`{rsi_warn}")
    lines += [
        f"",
        f"🕐 Alerte    : `{now_utc}`",
        f"",
        f"_Généré par Gold Scalping Webhook_",
    ]
    return "\n".join(lines)


async def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram non configuré — vérifiez TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID")
        return False
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "Markdown",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(TELEGRAM_API_URL, json=payload)
        if resp.status_code == 200:
            log.info("Notification Telegram envoyée avec succès")
            return True
        log.error(f"Erreur Telegram {resp.status_code}: {resp.text}")
        return False


# ── Routes ────────────────────────────────────────────────────
@app.get("/", tags=["health"])
async def health_check():
    """Vérifie que le serveur est en ligne."""
    return {
        "status":    "ok",
        "service":   "Gold & Silver Scalping Webhook",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "telegram":  bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
    }


@app.post("/webhook", status_code=status.HTTP_200_OK, tags=["webhook"])
async def receive_alert(
    payload: AlertPayload,
    request: Request,
    x_webhook_secret: Optional[str] = Header(None),
):
    """
    Point d'entrée principal.
    TradingView envoie le payload JSON ici à chaque alerte déclenchée.
    """
    # ── Vérification du secret (optionnel mais recommandé)
    if WEBHOOK_SECRET and x_webhook_secret != WEBHOOK_SECRET:
        log.warning(f"Tentative avec secret invalide depuis {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secret webhook invalide",
        )

    log.info(
        f"Alerte reçue | {payload.asset} {payload.action.upper()} "
        f"@ {payload.price:.2f} | TF: {payload.tf} | RSI: {payload.rsi}"
    )

    # ── Construction et envoi du message Telegram
    message = build_telegram_message(payload)
    sent    = await send_telegram(message)

    return JSONResponse({
        "status":           "received",
        "asset":            payload.asset,
        "action":           payload.action,
        "price":            payload.price,
        "telegram_sent":    sent,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
    })


@app.post("/webhook/test", tags=["webhook"])
async def test_alert():
    """Envoie une fausse alerte Gold BUY pour tester l'intégration Telegram."""
    fake = AlertPayload(
        asset="XAUUSD", action="buy", price=3285.40,
        atr=1.32, rsi=54.7, tf="5",
        time="2025-05-30 14:32:00", alert="test_signal",
    )
    message = build_telegram_message(fake)
    sent    = await send_telegram(message)
    return {
        "status":        "test_sent",
        "telegram_sent": sent,
        "message":       message,
    }
