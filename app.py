from flask import Flask, session, redirect, url_for, request, render_template
import secrets
import requests

app = Flask(__name__)
app.secret_key = "e05f71dcab14188c6c174f33339910870067423832c85387bbf565e3840e6c1e"

# ESI Developer Credentials
CLIENT_ID = "83344efb272d4e469c40bec7934b050f"
CLIENT_SECRET = "HdhcdDgExQj0jBZ88tif4JgBgiQcSkqSs1DRdvFP"

# ESI OAuth Endpoints
AUTH_URL = "https://login.eveonline.com/v2/oauth/authorize"
TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
CALLBACK_URL = "https://fleet-dest-cbbf9384726f.herokuapp.com/callback"

@app.route("/")
def index():
    """Render the app's home page."""
    logged_in = "access_token" in session
    character_name = session.get("character_name")
    return render_template("index.html", logged_in=logged_in, character_name=character_name)

@app.route("/login")
def login():
    """Redirect to EVE Online login page."""
    state = secrets.token_hex(16)
    session["state"] = state
    return redirect(
        f"{AUTH_URL}?response_type=code&redirect_uri={CALLBACK_URL}&client_id={CLIENT_ID}&state={state}"
    )

@app.route("/callback")
def callback():
    """Handle callback after EVE Online login."""
    # Validate state to prevent CSRF attacks
    state = request.args.get("state")
    if state != session.pop("state", None):
        return "State mismatch! Potential CSRF attack.", 400

    # Exchange authorization code for tokens
    code = request.args.get("code")
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": CALLBACK_URL,
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
    )

    if response.status_code != 200:
        return "Token exchange failed.", 400

    tokens = response.json()
    session["access_token"] = tokens["access_token"]

    # Fetch character information
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    char_info = requests.get("https://esi.evetech.net/latest/verify/", headers=headers).json()
    session["character_name"] = char_info["CharacterName"]

    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    """Log out the user and clear the session."""
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
