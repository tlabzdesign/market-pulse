# 📊 Market Pulse — Deploy & Install as Android App

## Architecture
```
Render.com (free cloud)          Your Phone
┌──────────────────────┐        ┌──────────────────┐
│  server.py           │        │  Market Pulse APK │
│  ├── Scans 60+ NSE   │◄──────►│  (WebView shell)  │
│  │   stocks / 30 min  │  API  │  ├── Live news     │
│  ├── 4 RSS feeds      │       │  ├── Breakouts     │
│  ├── 6 breakout scans │       │  ├── Buy/Sell/SL   │
│  └── Auto outlook     │       │  └── Auto-refresh  │
└──────────────────────┘        └──────────────────┘
                                Share APK with friends!
```

## Step 1: Deploy Backend (5 min)

### Option A: Render.com (Recommended, Free)
1. Go to https://github.com — create a new repo "market-pulse"
2. Upload all files from this folder to the repo
3. Go to https://render.com — sign up free
4. Click "New" → "Web Service"
5. Connect your GitHub repo
6. Render auto-detects `render.yaml` — click Deploy
7. Wait 2-3 min — you get a URL like `https://market-pulse-xxxx.onrender.com`

### Option B: Railway.app (Free)
1. Go to https://railway.app — sign up
2. Click "New Project" → "Deploy from GitHub"
3. Select your repo
4. Add environment variable: `PORT=8000`
5. Deploy — get URL like `https://market-pulse.up.railway.app`

### Option C: Your MacBook (for testing)
```bash
pip install -r requirements.txt
python server.py
# Open http://localhost:8000
```

## Step 2: Make Android APK (5 min)

### Option A: PWABuilder (Easiest)
1. Go to https://www.pwabuilder.com
2. Enter your Render URL: `https://market-pulse-xxxx.onrender.com`
3. Click "Package for stores" → Android
4. Download the APK
5. Install on your phone (enable "Unknown sources")
6. Share APK file with friends via WhatsApp/email

### Option B: Bubblewrap CLI (More control)
```bash
npm install -g @aspect/aspect-cli
npm install -g @nicegoodthings/nicepwa-builder

# Or use Google's Bubblewrap:
npm install -g @nicegoodthings/nicepwa-builder

# Simpler: use https://nicepwa.com
# Enter your URL → download APK
```

### Option C: Android Studio (Full control)
1. Create new project → "Empty Activity"
2. Replace MainActivity with WebView pointing to your URL
3. Build → Generate Signed APK
4. Share APK

## Step 3: Share with Friends
- Send the APK file via WhatsApp/email
- OR just share the URL — they open in Chrome → "Add to Home Screen"
- Everyone sees the same live data

## What Runs Live
✅ Stock prices — Yahoo Finance (every 30 min scan)
✅ 6 breakout patterns — SMA cross, 200DMA, volume spike, RSI, 52W high, BB squeeze
✅ Buy/Sell/SL levels — ATR-calculated, changes every scan
✅ News — 4 RSS feeds scanned every 10 min
✅ Outlook — auto-generated from Nifty + VIX

## Free Tier Limits
- Render free: sleeps after 15 min inactivity, wakes on request (30s cold start)
- To keep alive: use https://uptimerobot.com (free) to ping your URL every 14 min
- Railway free: 500 hours/month (enough for market hours)

## Folder Structure
```
market-pulse-deploy/
├── server.py          ← Everything in one file (backend + scanner + news)
├── requirements.txt   ← Python packages
├── render.yaml        ← Render.com auto-config
├── static/
│   ├── index.html     ← PWA frontend (the app UI)
│   ├── manifest.json  ← PWA install config
│   └── sw.js          ← Offline support
└── README.md          ← This file
```
