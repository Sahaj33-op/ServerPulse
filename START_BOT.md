# 🚀 ServerPulse - Quick Start Guide

## Simple Commands to Control Your Bot

### ✅ Start the Bot (First Time or After Code Changes)

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose up -d --build
```

This builds the image and starts all containers in the background.

### ✅ Start the Bot (Quick Start - No Rebuild)

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose up -d
```

Use this when you just want to start without rebuilding.

### 🛑 Stop the Bot

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose down
```

Stops and removes all containers.

### 🔄 Restart the Bot

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose restart
```

Restarts containers without rebuilding.

### 📊 Check if Bot is Running

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose ps
```

Shows status of all containers.

### 📝 View Bot Logs

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose logs serverpulse
```

### 📝 View Bot Logs (Live/Follow)

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose logs -f serverpulse
```

Press `Ctrl+C` to exit.

---

## 🎯 Most Common Scenarios

### Scenario 1: IDE Crashed, Need to Start Bot

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose up -d
```

### Scenario 2: Bot is Acting Strange, Need to Restart

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose restart serverpulse
```

### Scenario 3: Made Code Changes, Need to Apply Them

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose up -d --build
```

### Scenario 4: Check if Bot is Actually Running

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose ps
```

Look for "Up" status next to `serverpulse-bot`.

### Scenario 5: Bot Not Working, Need to See What's Wrong

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose logs --tail=50 serverpulse
```

---

## 🔧 Troubleshooting

### Bot Says "Already Exists" Error

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose down
docker compose up -d
```

### Want to Start Fresh

```powershell
cd f:\Sahaj\Projects\ServerPulse
docker compose down -v
docker compose up -d --build
```

⚠️ This deletes all data including database!

### Check All Container Statuses

```powershell
docker ps -a
```

---

## 📌 Important Notes

1. **Always navigate to project folder first**:

   ```powershell
   cd f:\Sahaj\Projects\ServerPulse
   ```

2. **Bot runs in background** with `-d` flag
   - It will keep running even if you close PowerShell
   - It will auto-start on system reboot (unless you stop it)

3. **To completely stop everything**:

   ```powershell
   docker compose down
   ```

4. **Bot token and settings** are in `.env` file
   - Edit that file if you need to change API keys
   - After editing, restart: `docker compose restart serverpulse`

---

## 🎮 Easy Copy-Paste Commands

**Just Start the Bot:**

```powershell
cd f:\Sahaj\Projects\ServerPulse ; docker compose up -d
```

**Stop the Bot:**

```powershell
cd f:\Sahaj\Projects\ServerPulse ; docker compose down
```

**Restart the Bot:**

```powershell
cd f:\Sahaj\Projects\ServerPulse ; docker compose restart
```

**Check Status:**

```powershell
cd f:\Sahaj\Projects\ServerPulse ; docker compose ps
```

**View Logs:**

```powershell
cd f:\Sahaj\Projects\ServerPulse ; docker compose logs --tail=30 serverpulse
```
