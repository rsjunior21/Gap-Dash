# Sharing the Gap-Time Dashboard

You have **two ways** to share. Pick whichever matches your situation.

---

## Option A — Share on your office network (LAN)

Use this if everyone you want to share with is on the same Wi-Fi / corporate network as your PC.

1. Double-click **Start_Dashboard.bat**.
2. Leave the black console window open.
3. Send coworkers this URL (replace `YOUR-PC` with your computer name — the launcher prints it for you):

   ```
   http://YOUR-PC:8501
   ```

   Or share your IP version:

   ```powershell
   ipconfig | Select-String "IPv4"
   ```

   then send `http://<that-IP>:8501`.

**First-time only:** Windows Firewall will pop up and ask whether to allow Python on the network — click **Allow**. If you missed it, run this once in an **admin** PowerShell:

```powershell
New-NetFirewallRule -DisplayName "Streamlit Dashboard" -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow
```

Caveats: your PC must be powered on and the launcher must be running. Anyone off the network can't reach it.

---

## Option B — Public URL via Streamlit Community Cloud (free, always on)

This gives you a permanent URL like `https://gap-time.streamlit.app` that anyone can open from any device, even when your PC is off.

### One-time setup

1. Make a free GitHub account: https://github.com/signup
2. Create a new **public** repo (e.g. `gap-time-dashboard`).
3. Upload these three files into the repo (drag & drop on GitHub works):
   - `dashboard.py`
   - `requirements.txt`
   - this `SHARING.md` (optional)
4. Sign in to https://share.streamlit.io with the same GitHub account.
5. Click **New app** → pick your repo → main file = `dashboard.py` → **Deploy**.
6. After ~1 minute you'll get a public URL. Share it.

### Updating it

Edit `dashboard.py` on GitHub (or push from your PC). Streamlit Cloud redeploys automatically within a minute.

> If your Excel files are confidential and you don't want a public app, the cloud option also supports a private deployment via the same dashboard — toggle **"Only specific people can view this app"** under app settings.

---

## Option C — Quick public tunnel (advanced, your PC stays the host)

If you want a public URL but want files processed on YOUR machine (nothing uploaded to the cloud), install ngrok (https://ngrok.com), then while the launcher is running:

```powershell
ngrok http 8501
```

ngrok prints a `https://xxxx.ngrok-free.app` URL — that's the shareable link. Stops working when you close ngrok or the launcher.
