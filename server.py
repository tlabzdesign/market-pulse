"""
Market Pulse — Cloud Server
Deploy to Render.com / Railway / any VPS
No Telegram, no dependencies beyond pip packages
"""
import os, time, hashlib, logging, threading
from datetime import datetime
from typing import List, Dict, Optional

import numpy as np
import pandas as pd
import yfinance as yf
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

try:
    import feedparser
except:
    feedparser = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mp")

PORT = int(os.getenv("PORT", 8000))

# ── Watchlist ──
STOCKS = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","SBIN",
    "BHARTIARTL","ITC","KOTAKBANK","LT","AXISBANK","BAJFINANCE","ASIANPAINT",
    "MARUTI","HCLTECH","SUNPHARMA","TITAN","WIPRO","ULTRACEMCO",
    "TATAMOTORS","TATASTEEL","ADANIENT","NTPC","POWERGRID","JSWSTEEL",
    "TECHM","HINDALCO","M&M","BAJAJFINSV","VEDL","TRENT","DLF","GAIL",
    "ONGC","COALINDIA","BPCL","IOC","INDIGO","SBILIFE","GODREJPROP",
    "TATAPOWER","ADANIPORTS","DIVISLAB","CIPLA","DRREDDY","APOLLOHOSP",
    "PNB","BANKBARODA","IRCTC","ZOMATO","BIRLASOFT","MPHASIS","LTIM",
    "COFORGE","PERSISTENT","NHPC","SJVN","RECLTD","SAIL","NMDC",
]

FEEDS = [
    ("Moneycontrol", "https://www.moneycontrol.com/rss/marketedge.xml"),
    ("ET Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("LiveMint", "https://www.livemint.com/rss/markets"),
    ("Business Std", "https://www.business-standard.com/rss/markets-106.rss"),
]

# ── State ──
state = {
    "breakouts": [], "news": [], "outlook": {},
    "last_scan": None, "last_news": None, "scan_count": 0, "status": "starting"
}

# ══════ Technical Indicators ══════
def sma(s,p): return s.rolling(p).mean()
def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def rsi(s,p=14):
    d=s.diff(); g=d.where(d>0,0).rolling(p).mean(); l=(-d.where(d<0,0)).rolling(p).mean()
    return 100-(100/(1+g/l.replace(0,np.nan)))
def atr(h,l,c,p=14):
    tr=pd.concat([h-l,abs(h-c.shift(1)),abs(l-c.shift(1))],axis=1).max(axis=1)
    return tr.rolling(p).mean()
def bbands(s,p=20,sd=2):
    m=s.rolling(p).mean();st=s.rolling(p).std()
    return m+st*sd, m, m-st*sd

# ══════ Scanner ══════
def make_alert(sym,nm,pat,bl,bh,t1,t2,sl,dur,conf,reason):
    risk=bh-sl; reward=t1-bh; rr=f"1:{reward/risk:.1f}" if risk>0 else "N/A"
    return {"symbol":sym,"name":nm,"pattern":pat,"side":"LONG",
        "buy_low":round(bl,2),"buy_high":round(bh,2),
        "target_1":round(t1,2),"target_2":round(t2,2),
        "stop_loss":round(sl,2),"duration":dur,
        "risk_reward":rr,"confidence":min(90,max(30,conf)),
        "reason":reason,"time":datetime.now().strftime("%H:%M")}

def scan_stock(sym):
    try:
        df=yf.Ticker(f"{sym}.NS").history(period="200d")
        if df is None or len(df)<50: return []
    except: return []

    alerts=[]; C,H,L,V=df["Close"],df["High"],df["Low"],df["Volume"]
    last,prev=C.iloc[-1],C.iloc[-2]
    if last<50 or last>50000: return []

    s20,s50,s200=sma(C,20),sma(C,50),sma(C,200)
    _r=rsi(C); _a=atr(H,L,C); va=V.rolling(20).mean()
    bbu,bbm,bbl=bbands(C)
    lr,la,lv,av=_r.iloc[-1],_a.iloc[-1],V.iloc[-1],va.iloc[-1]
    vr=lv/av if av>0 else 0
    h52=H.tail(252).max() if len(H)>=252 else H.max()
    try: nm=yf.Ticker(f"{sym}.NS").info.get("shortName",sym)
    except: nm=sym

    # 1. SMA Golden Cross
    if s20.iloc[-1]>s50.iloc[-1] and s20.iloc[-2]<=s50.iloc[-2] and vr>=1.5:
        alerts.append(make_alert(sym,nm,"SMA 20/50 Golden Cross",
            last-.5*la,last+.3*la,last+2*la,last+3.5*la,last-2*la,
            "1-2 weeks",55+int(vr*8)+(5 if last>s200.iloc[-1] else 0),
            f"SMA20 crossed SMA50. Vol {vr:.1f}x. RSI {lr:.0f}."))

    # 2. 200 DMA Breakout
    if last>s200.iloc[-1] and prev<=s200.iloc[-2] and vr>=1.3:
        alerts.append(make_alert(sym,nm,"200 DMA Breakout",
            s200.iloc[-1],last+.3*la,last+2.5*la,last+4*la,s200.iloc[-1]-la,
            "2-4 weeks",60+int(vr*6),
            f"Broke 200DMA ₹{s200.iloc[-1]:,.0f}. Vol {vr:.1f}x."))

    # 3. Volume Spike
    rh=H.tail(20).max()
    if last>rh*.98 and vr>=2 and lr>55:
        alerts.append(make_alert(sym,nm,"Volume Spike Breakout",
            last-.3*la,last+.2*la,last+2*la,last+3*la,last-1.5*la,
            "3-7 days",50+int(vr*5)+(10 if lr>60 else 0),
            f"Near 20D high. Vol {vr:.1f}x. RSI {lr:.0f}."))

    # 4. RSI Oversold
    if lr<35 and C.iloc[-1]>C.iloc[-2] and vr>=1.2:
        alerts.append(make_alert(sym,nm,"RSI Oversold Bounce",
            last-.5*la,last,last+2*la,last+3.5*la,L.tail(5).min()-la,
            "1-2 weeks",45+int(vr*5),
            f"RSI {lr:.0f} oversold + green candle + {vr:.1f}x vol."))

    # 5. 52W High
    if last>=h52*.98 and vr>=1.5 and lr>60:
        alerts.append(make_alert(sym,nm,"52-Week High Breakout",
            last-.3*la,last+.5*la,last*1.05,last*1.10,last-2*la,
            "1-3 weeks",55+int(vr*5),
            f"At 52W high ₹{h52:,.0f}. Vol {vr:.1f}x. RSI {lr:.0f}."))

    # 6. BB Squeeze
    bw=(bbu.iloc[-1]-bbl.iloc[-1])/bbm.iloc[-1] if bbm.iloc[-1] else 1
    if bw<.04 and last>bbu.iloc[-1] and vr>=1.3:
        alerts.append(make_alert(sym,nm,"Bollinger Squeeze Breakout",
            bbu.iloc[-1],last+.3*la,last+2*la,last+3*la,bbm.iloc[-1]-.5*la,
            "3-7 days",50+int(vr*6),
            f"BB squeeze {bw:.3f} + broke upper band. Vol {vr:.1f}x."))

    return alerts

def full_scan():
    log.info(f"Scanning {len(STOCKS)} stocks...")
    all_a=[]
    for i,s in enumerate(STOCKS):
        all_a.extend(scan_stock(s))
        if (i+1)%10==0:
            log.info(f"  {i+1}/{len(STOCKS)} ({len(all_a)} alerts)")
            time.sleep(1.5)
    all_a.sort(key=lambda x:x["confidence"],reverse=True)
    log.info(f"Done: {len(all_a)} breakouts")
    return all_a

# ══════ News ══════
seen_news=set()
def scan_news():
    global seen_news
    if not feedparser: return []
    POS=["surge","rally","gain","rise","bull","buy","ceasefire","rate cut","positive","upgrade","boom"]
    NEG=["crash","fall","plunge","war","sell","crisis","ban","loss","downgrade","panic","default"]
    IMP=["nifty","sensex","bank nifty","rbi","fii","dii","crude","gold","breakout","record","war","ceasefire"]
    SEC={"nifty":"Index","sensex":"Index","bank":"Banking","rbi":"Banking","oil":"Oil & Gas","crude":"Oil & Gas","auto":"Auto","pharma":"Pharma","gold":"Gold","metal":"Metals","it ":"IT","tech":"IT","real":"Realty","power":"Power","airline":"Airlines"}

    results=[]
    for name,url in FEEDS:
        try:
            for e in feedparser.parse(url).entries[:12]:
                t=e.get("title","").strip()
                if not t: continue
                h=hashlib.md5(t.encode()).hexdigest()[:10]
                if h in seen_news: continue
                seen_news.add(h)
                txt=t.lower(); sm=(e.get("summary") or "")[:200].replace("<","&lt;")
                isc=sum(1 for w in IMP if w in txt)
                impact="HIGH" if isc>=3 else "MEDIUM" if isc>=1 else "LOW"
                ps=sum(1 for w in POS if w in txt); ns=sum(1 for w in NEG if w in txt)
                direction="POSITIVE" if ps>ns else "NEGATIVE" if ns>ps else "NEUTRAL"
                sectors=list({v for k,v in SEC.items() if k in txt})[:4]
                results.append({"headline":t,"source":name,"impact":impact,"direction":direction,
                    "sectors":sectors,"analysis":sm,"time":datetime.now().strftime("%H:%M"),
                    "is_major":impact=="HIGH" and abs(ps-ns)>=2})
        except: pass
    if len(seen_news)>2000: seen_news=set(list(seen_news)[-1000:])
    return sorted(results,key=lambda x:{"HIGH":3,"MEDIUM":2,"LOW":1}.get(x["impact"],0),reverse=True)

# ══════ Outlook ══════
def gen_outlook():
    try:
        n=yf.Ticker("^NSEI").history(period="5d"); v=yf.Ticker("^INDIAVIX").history(period="5d")
        if n.empty: return
        last,prev=n["Close"].iloc[-1],n["Close"].iloc[-2] if len(n)>1 else n["Close"].iloc[-1]
        chg=((last-prev)/prev)*100; lv=v["Close"].iloc[-1] if not v.empty else 20
        s="BULLISH" if chg>1 else "BEARISH" if chg<-1 else "NEUTRAL"
        c=min(85,50+int(abs(chg)*8))
        dr=[f"Nifty {chg:+.1f}%",f"Nifty {last:,.0f}"]
        if lv>20: dr.append(f"VIX high {lv:.1f}")
        state["outlook"]={"sentiment":s,"confidence":c,
            "summary":f"Nifty at {last:,.0f} ({chg:+.1f}%). VIX {lv:.1f}. {'Positive momentum.' if chg>0 else 'Watch support.'}",
            "drivers":dr,"nifty_levels":f"{last:,.0f}","bnifty_levels":"Live"}
    except Exception as e:
        log.error(f"Outlook: {e}")

# ══════ Background Loop ══════
def bg_loop():
    time.sleep(3)
    gen_outlook()
    while True:
        try:
            state["status"]="scanning"
            state["breakouts"]=full_scan()[:15]
            state["last_scan"]=datetime.now().isoformat()
            state["scan_count"]+=1
            state["news"]=scan_news()[:20]
            state["last_news"]=datetime.now().isoformat()
            gen_outlook()
            state["status"]="idle"
            log.info(f"Cycle #{state['scan_count']}: {len(state['breakouts'])} breakouts, {len(state['news'])} news")
        except Exception as e:
            log.error(f"Loop: {e}"); state["status"]="error"
        time.sleep(1800) # 30 min

# ══════ FastAPI ══════
@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=bg_loop,daemon=True).start()
    log.info(f"Market Pulse on http://0.0.0.0:{PORT}")
    yield

app=FastAPI(title="Market Pulse",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])
app.mount("/static",StaticFiles(directory="static"),name="static")

@app.get("/")
async def root(): return FileResponse("static/index.html")
@app.get("/api/scan")
async def api_scan(): return {"breakouts":state["breakouts"],"last_scan":state["last_scan"],"count":state["scan_count"]}
@app.get("/api/news")
async def api_news(): return {"news":state["news"],"last_scan":state["last_news"]}
@app.get("/api/outlook")
async def api_outlook(): return state["outlook"]
@app.get("/api/status")
async def api_status():
    return {"status":state["status"],"last_scan":state["last_scan"],"scan_count":state["scan_count"],
        "watchlist_size":len(STOCKS),"breakouts_found":len(state["breakouts"]),"news_items":len(state["news"]),
        "server_time":datetime.now().isoformat()}
@app.post("/api/force-scan")
async def api_force():
    def _s():
        state["breakouts"]=full_scan()[:15]; state["last_scan"]=datetime.now().isoformat()
        state["scan_count"]+=1; state["news"]=scan_news()[:20]; state["last_news"]=datetime.now().isoformat()
    threading.Thread(target=_s,daemon=True).start()
    return {"msg":"started"}
@app.get("/manifest.json")
async def mf(): return FileResponse("static/manifest.json")
@app.get("/sw.js")
async def sw(): return FileResponse("static/sw.js")

if __name__=="__main__":
    uvicorn.run("server:app",host="0.0.0.0",port=PORT)
