# ─────────────────────────────────────────────────────────────
#  Gold & Silver Scalping v2 — Webhook TradingView → Telegram
#  Inclut PE (Point d'Entrée), TP et SL dans les alertes
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import logging, os
from datetime import datetime, timezone
from typing import Optional
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET     = os.getenv("WEBHOOK_SECRET", "")
TELEGRAM_API_URL   = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("scalp-webhook")

app = FastAPI(title="Gold & Silver Scalping Webhook v2", version="2.0.0")

class AlertPayload(BaseModel):
    asset:  str            = Field(..., example="XAUUSD")
    action: str            = Field(..., example="buy")
    price:  float          = Field(..., example=3285.40)
    pe:     Optional[float]= Field(None, example=3284.50)
    tp:     Optional[float]= Field(None, example=3287.38)
    sl:     Optional[float]= Field(None, example=3284.48)
    atr:    Optional[float]= Field(None, example=1.25)
    rsi:    Optional[float]= Field(None, example=52.3)
    tf:     Optional[str]  = Field(None, example="5")
    time:   Optional[str]  = Field(None)
    alert:  Optional[str]  = Field(None)

ASSET_EMOJI  = {"XAUUSD": "🥇", "GOLD": "🥇", "XAGUSD": "🥈", "SILVER": "🥈"}
ACTION_EMOJI = {"buy": "🟢", "sell": "🔴"}
TF_LABEL     = {"1":"M1","5":"M5","15":"M15","30":"M30","60":"H1","240":"H4"}

def build_message(p: AlertPayload) -> str:
    ae  = ASSET_EMOJI.get(p.asset.upper(), "📈")
    ace = ACTION_EMOJI.get(p.action.lower(), "⚪")
    tf  = TF_LABEL.get(str(p.tf), f"TF{p.tf}") if p.tf else "—"
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    rr  = round(abs((p.tp - p.price) / (p.price - p.sl)), 2) if p.tp and p.sl and p.sl != p.price else None

    lines = [
        f"{ae} *{p.asset.upper()}* — {ace} *{p.action.upper()}*",
        f"",
        f"💰 Prix actuel : `{p.price:.2f}`",
        f"⏱ Timeframe   : `{tf}`",
    ]
    if p.pe:
        lines.append(f"🎯 Point Entrée : `{p.pe:.2f}`")
    if p.tp:
        lines.append(f"✅ Take Profit  : `{p.tp:.2f}`")
    if p.sl:
        lines.append(f"🛑 Stop Loss    : `{p.sl:.2f}`")
    if rr:
        lines.append(f"⚖️ R/R ratio    : `1:{rr}`")
    if p.atr:
        lines.append(f"📐 ATR          : `{p.atr:.2f}`")
    if p.rsi:
        rsi_warn = " ⚠️ sur-achat" if p.rsi > 70 else " ⚠️ sur-vente" if p.rsi < 30 else ""
        lines.append(f"📊 RSI(7)       : `{p.rsi:.1f}`{rsi_warn}")
    lines += ["", f"🕐 Alerte : `{now}`", "", "_Gold Scalping Webhook v2_"]
    return "\n".join(lines)

async def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram non configuré")
        return False
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(TELEGRAM_API_URL, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        })
        if resp.status_code == 200:
            log.info("Telegram envoyé ✅")
            return True
        log.error(f"Erreur Telegram {resp.status_code}: {resp.text}")
        return False

@app.get("/")
async def health():
    return {"status":"ok","service":"Gold & Silver Scalping Webhook v2","telegram":bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)}

@app.post("/webhook")
async def receive_alert(payload: AlertPayload, request: Request, x_webhook_secret: Optional[str] = Header(None)):
    if WEBHOOK_SECRET and x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Secret invalide")
    log.info(f"Alerte | {payload.asset} {payload.action.upper()} @ {payload.price:.2f} | PE:{payload.pe} TP:{payload.tp} SL:{payload.sl}")
    sent = await send_telegram(build_message(payload))
    return JSONResponse({"status":"received","asset":payload.asset,"action":payload.action,"price":payload.price,"pe":payload.pe,"tp":payload.tp,"sl":payload.sl,"telegram_sent":sent})

@app.post("/webhook/test")
async def test_alert():
    fake = AlertPayload(
        asset="XAUUSD", action="buy", price=3285.40,
        pe=3284.50, tp=3287.38, sl=3284.48,
        atr=1.32, rsi=54.7, tf="5", time="2026-09-22 11:20:00"
    )
    sent = await send_telegram(build_message(fake))
    return {"status":"test_sent","telegram_sent":sent}
