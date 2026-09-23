# Firefighter Dashboard

A Flask dashboard for live ER:LC server telemetry and Roblox-authenticated fire/medical incident records.

## Setup

1. Create and activate a Python virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Create a Roblox OAuth application and set its callback URL to the value of `ROBLOX_REDIRECT_URI`.
4. Add the following values to `.env`:

```env
ERLC_SERVER_KEY=your_er_lc_server_key
FLASK_SECRET_KEY=use-a-long-random-value
ROBLOX_CLIENT_ID=your_roblox_oauth_client_id
ROBLOX_CLIENT_SECRET=your_roblox_oauth_client_secret
ROBLOX_REDIRECT_URI=http://localhost:5000/auth/roblox/callback
PORT=5000
DATABASE_PATH=firefighter_dashboard.db
```

Start the app with:

```bash
python app.py
```

Open `http://localhost:5000`; unauthenticated visitors are sent to the required Roblox login page. After signing in, the account headshot opens a menu showing the signed-in username and a **Sign out** action that returns to the login page. The app stores the Roblox subject/user id in the Flask session. That identity is used as the publisher of every record and is checked again on deletion.

## Records and deletion rules

Records are stored in the SQLite database at `DATABASE_PATH`, not in browser `localStorage`.

- `POST /api/records` requires a Roblox sign-in and stamps the record with `publishedById` and `publishedByName`.
- Every fire and medical record automatically includes the signed-in Roblox username in `units`. Additional units can be selected from the checkbox dropdown, which is populated from currently active Fire, EMS, and Police players returned by ER:LC.
- `DELETE /api/records/<id>` only succeeds when the signed-in Roblox user owns that record. Other users see a lock icon and the server returns `403` even if a request is sent manually.
- The ER:LC server API identifies the configured game server through `ERLC_SERVER_KEY`. Roblox OAuth identifies the dashboard operator; the ER:LC API does not receive the OAuth token.

## ER:LC live data

`app.py` proxies `https://api.erlc.gg/v2/server` with `Players=true`, `Vehicles=true`, and `EmergencyCalls=true`.

The template automatically fetches the endpoint when the page loads and every 5 seconds afterward. It filters the returned `Players` list to Fire, EMS, and Police teams, joins each player to the matching `Vehicles` owner, and displays the player's callsign and current vehicle in the live units table. The **Active Units on Duty** KPI is set to that fetched filtered-player count. It shows `--` when the API is unavailable and is never initialized to a made-up number.

## Customization guide

All current place-specific text and assets are in `templates/index.html` unless noted otherwise.

### Header branding

- Browser title: the `<title>` near the top of `templates/index.html` (`Station 7 | Fire & Medical Command Portal`).
- Large top-left header text: the `STATION 7 COMMAND` `<h1>` in the `Top Navbar` section.
- Text beside it: the `Liberty County Fire & Rescue` paragraph directly below that heading.
- The image/icon beside the text is currently not an image file. It is the Font Awesome `fa-fire-extinguisher` icon in the red square immediately before the heading. Replace that `<i>` element with an `<img src="...">` if a real logo is preferred.

### Dispatcher label

The fixed, non-editable dispatcher text is the `currentUserName` `<span>` in the top navbar:

```html
<span id="currentUserName">Springfield 911 Command Center</span>
```

Incident records also use this command-center label when building the responding-units display. Roblox user identity remains the publisher/audit identity.

### Tactical map

The map is rendered by the `<img>` in the `TAB 5: TACTICAL MAP` section:

```html
<img src="{{ url_for('static', filename='Firefighter Map Asset_2.jpg') }}" ...>
```

Put the replacement image at `static/Firefighter Map Asset_2.jpg`, or change the `filename` value in that line. The current checkout does not contain a `static` directory or that JPG, so the `onerror` handler displays a remote fallback image until the asset is added. The map alt text and the nearby `Liberty County Sector 7` label are in the same section.

### Other Liberty County references

Search for `Liberty County` in `templates/index.html` to update all of these current labels:

- Header department subtitle: `Liberty County Fire & Rescue`.
- Tactical map description: `Liberty County district grid layout...`.
- Tactical map asset badge: `Map Asset Loaded: Liberty County Sector 7`.
- ER:LC server placeholder: `Liberty County RP #1`.

### Other editable application text

- `Station 7` also appears in the page title, the Flask page docstring, and the startup message in `app.py`.
- Case number prefixes are `F` and `MED` in `updateCaseNumberFields`, `submitFireReport`, and `submitMedicalReport`.
- ER:LC team filtering is in `syncERLCData()` in `templates/index.html`. Adjust the team names there if the server uses different team labels.
- OAuth endpoints, scopes, and callback handling are in the `/auth/roblox/*` routes in `app.py`.

## Security notes

Keep `.env` and the generated SQLite database out of source control. Use a stable, private `FLASK_SECRET_KEY` in production. Configure Roblox OAuth with the exact public callback URL used by the deployment.