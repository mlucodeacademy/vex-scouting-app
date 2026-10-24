# 🤖 VEX Robotics Tournament Schedule & Live Scouting App

A fast, mobile-first Progressive Web App (PWA) designed for VEX Robotics teams to track tournament match schedules, cumulative cascading match delays, match turnaround alerts, and live alliance scouting data across team members in real-time.

---

## ✨ Features

- **📱 Mobile-First PWA**: Fits iPhone & Android screens with zero horizontal overflow, installable to the home screen.
- **⏱️ Per-Game Cascading Delays**: Adjust any match start time or click **"Set to NOW"**; delays cascade automatically forward to all subsequent matches.
- **🍔 Dynamic Lunch Cutoff**: The fixed venue lunch window (e.g., 11:27 AM – 12:15 PM) dynamically determines which match is the last one played before the break based on current match delays.
- **🔭 Live Collaborative Scouting**: Instant 0–5 rating buttons (Auton, Loading, Scoring, Toggle, Driving + Notes), synchronized across all team phones via Firebase Realtime Database.
- **📋 Google Form & Sheet Integration**: Submits directly to your team's Google Form for central record keeping, and exports CSV pick-lists on demand.
- **🌓 Native Dark & Light Mode**: Clean, high-contrast theme toggle powered by native CSS `light-dark()`.
- **🔄 Tournament Reusability**: Load any tournament match schedule on the fly by pasting a public Google Sheet link.

---

## 🚀 How Another User or Team Can Deploy This

Because this app is a static single-page web app (vanilla HTML5, CSS3, JavaScript) with offline-first local storage, another user has several simple deployment options:

### Option 1: GitHub Pages (Easiest — Free, No Firebase Required)

If another user doesn't want or need a Firebase account, they can run this entirely on GitHub Pages. The app automatically stores all scouting, match delays, and custom schedules in the browser's `localStorage`.

1. **Fork or push** this repository to GitHub.
2. In the GitHub repository, go to **Settings** > **Pages**.
3. Under **Build and deployment**:
   - **Source**: `Deploy from a branch`
   - **Branch**: `main` (or your branch), folder: `/public` (or `/` if you move files to root).
4. Click **Save**. Within 1–2 minutes, your site is live at:
   ```
   https://<username>.github.io/<repo-name>/
   ```
5. *(Optional)* Pass custom parameters in the URL:
   ```
   https://<username>.github.io/<repo-name>/?team=1234A
   ```

---

### Option 2: Deploy to Their Own Firebase Project (For Multi-Phone Live Sync)

To enable real-time collaboration where multiple team members scout and update match delays simultaneously from different phones:

#### 1. Create a Free Firebase Project
1. Go to [Firebase Console](https://console.firebase.google.com/) and click **Add project** (e.g. `my-vex-scout`).
2. In the left sidebar, click **Build** > **Realtime Database** > **Create Database**.
3. Start in **Test mode** (or paste the rules from `database.rules.json`).

#### 2. Configure the Repository
1. In `public/index.html` (around line 1060), update `RTDB_URL` with their database URL:
   ```javascript
   const RTDB_URL = "https://<your-project-id>-default-rtdb.firebaseio.com/vex_<your-team>";
   ```
   *(Or pass it as a URL parameter: `https://your-site.web.app/?rtdb=https://<your-db>.firebaseio.com/myteam`)*

2. In `.firebaserc`, replace the project ID:
   ```json
   {
     "projects": {
       "default": "<your-firebase-project-id>"
     }
   }
   ```

3. In `firebase.json`, you can customize the hosting target or site name, or use the default:
   ```json
   {
     "database": {
       "rules": "database.rules.json"
     },
     "hosting": {
       "public": "public",
       "rewrites": [{ "source": "**", "destination": "/index.html" }]
     }
   }
   ```

#### 3. Deploy via Firebase CLI
```bash
# 1. Install Firebase CLI
npm install -g firebase-tools

# 2. Log in with your Google account
firebase login

# 3. Link to your project
firebase use --add <your-firebase-project-id>

# 4. Deploy Hosting & Database Rules
firebase deploy
```

---

### Option 3: 1-Click Deploy on Vercel, Netlify, or Cloudflare Pages

1. Connect your GitHub repository to [Vercel](https://vercel.com/) or [Netlify](https://www.netlify.com/).
2. Set the **Root Directory** to `public` (or set the publish directory to `public`).
3. Deploy!

---

## 🛠️ Customizing for Your Team & Tournament

### 1. Setting Your Focus Team
- Change the team dropdown at the top of the app, or pass `?team=YOUR_TEAM_NUMBER` in the URL (e.g. `?team=98250A`).
- The app remembers your selected team in `localStorage`.

### 2. Loading a New Tournament Schedule
1. In Google Sheets, make sure your match schedule spreadsheet is set to **"Anyone with the link can view"**.
2. Columns should follow standard VEX format:
   `Match | Time | Field | Red 1 | Red 2 | Blue 1 | Blue 2`
3. Click the **📱 QR / Share** button in the app header, paste the Google Sheet URL into **"Reuse for Future Tournaments"**, and tap **"Load Schedule from Sheet"**.
4. The schedule updates immediately and syncs across all connected team devices.

### 3. Connecting Your Own Google Form (Optional)
To submit scouting reports into your own Google Form:
1. Inspect your Google Form's `action` URL and input entry IDs (`entry.XXXXXXXXX`).
2. In `public/index.html`, update `GOOGLE_FORM_ACTION` and the field IDs inside `submitScoutReport()`.

---

## 🔒 Security & Privacy

- No sensitive API keys or secret credentials are stored in this repository.
- Firebase Realtime Database operates via open REST endpoints during tournament play.
- Works 100% offline with zero external network dependencies if the network is spotty inside venue arenas.
