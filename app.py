from flask import Flask, session, redirect, url_for, request, jsonify, render_template
import requests
import os
import json
import secrets

app = Flask(__name__)
app.secret_key = "e05f71dcab14188c6c174f33339910870067423832c85387bbf565e3840e6c1e"


AUTH_URL = "https://login.eveonline.com/v2/oauth/authorize"

# Your ESI developer credentials
CLIENT_ID = "83344efb272d4e469c40bec7934b050f"
SECRET_KEY = "HdhcdDgExQj0jBZ88tif4JgBgiQcSkqSs1DRdvFP"
CALLBACK_URL = "https://fleet-dest-cbbf9384726f.herokuapp.com/callback"
#EVE Online Token URL
TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
SCOPES = "esi-ui.write_waypoint.v1"

# Load systems data
with open("systems.json", "r") as f:
    SYSTEMS = json.load(f)

# Login route
import secrets

@app.route("/login")
def login():
    state = secrets.token_hex(16)
    session['oauth_state'] = state
    auth_url = (
        f"{AUTH_URL}?response_type=code"
        f"&redirect_uri={CALLBACK_URL}"
        f"&client_id={CLIENT_ID}"
        f"&state={state}"
    )
    return redirect(auth_url)


@app.route("/callback")
def callback():
    state = request.args.get('state')
    if state != session.get('oauth_state'):
        return "State mismatch! Potential CSRF attack.", 400
    # Proceed with the token exchange process


    # Exchange the authorization code for an access token
    code = request.args.get('code')
    token_data = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'redirect_uri': CALLBACK_URL,
    }
    response = requests.post(TOKEN_URL, data=token_data)
    token_response = response.json()

    if response.status_code != 200:
        return f"Token exchange failed: {token_response.get('error_description', 'Unknown error')}"

    # Save user data to the session
    session['access_token'] = token_response['access_token']
    session['refresh_token'] = token_response.get('refresh_token')
    session['expires_in'] = token_response.get('expires_in')
    session['logged_in'] = True

    return redirect('/')  # Redirect to the app's home page


# Home page
@app.route('/')
def home():
    # Check if the user is logged in by verifying session variables
    if not session.get('logged_in'):
        return redirect('/login')  # Redirect to login if not logged in
    return render_template('index.html')  # Serve your app's main page


# Set destination route #
@app.route("/set-destination", methods=["POST"])
def set_destination():
    system_id = request.json.get("system_id")
    add_to_route = request.json.get("add_to_route", False)

    if not system_id:
        return jsonify({"error": "Missing system ID"}), 400

    characters = session.get("characters", {})
    results = {}

    for character_name, character_data in characters.items():
        headers = {"Authorization": f"Bearer {character_data['access_token']}"}
        params = {
            "destination_id": system_id,
            "add_to_beginning": not add_to_route,
            "clear_other_waypoints": not add_to_route,
        }
        response = requests.post(
            "https://esi.evetech.net/v2/ui/autopilot/waypoint/",
            headers=headers,
            params=params,
        )
        if response.status_code == 204:
            results[character_name] = "Waypoint set successfully"
        else:
            results[character_name] = f"Error: {response.text}"

    return jsonify(results)

# Systems route for autocomplete
@app.route("/systems")
def systems():
    return jsonify(SYSTEMS)

# Logout route
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/logout-character/<character_name>", methods=["POST"])
def logout_character(character_name):
    characters = session.get("characters", {})
    if character_name in characters:
        del characters[character_name]
        session["characters"] = characters
        session.modified = True
        return jsonify({"message": f"{character_name} logged out successfully"}), 200
    return jsonify({"error": f"{character_name} not found"}), 404


if __name__ == "__main__":
    app.run(debug=True)
