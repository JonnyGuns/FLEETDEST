from flask import Flask, session, redirect, url_for, request, jsonify, render_template
import requests
import os
import json

app = Flask(__name__)
app.secret_key = "e05f71dcab14188c6c174f33339910870067423832c85387bbf565e3840e6c1e"

# Your ESI developer credentials
CLIENT_ID = "83344efb272d4e469c40bec7934b050f"
SECRET_KEY = "HdhcdDgExQj0jBZ88tif4JgBgiQcSkqSs1DRdvFP"
CALLBACK_URL = "https://fleet-dest-cbbf9384726f.herokuapp.com/callback"

SCOPES = "esi-ui.write_waypoint.v1"

# Load systems data
with open("systems.json", "r") as f:
    SYSTEMS = json.load(f)

# Login route
@app.route("/login")
def login():
    state = os.urandom(16).hex()
    session["state"] = state
    esi_url = (
        f"https://login.eveonline.com/v2/oauth/authorize/"
        f"?response_type=code&redirect_uri={CALLBACK_URL}"
        f"&client_id={CLIENT_ID}&scope={SCOPES}&state={state}"
    )
    return redirect(esi_url)

# Callback route
@app.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")

    if state != session.get("state"):
        return "Invalid state parameter", 400

    # Exchange authorization code for access token
    token_url = "https://login.eveonline.com/v2/oauth/token"
    auth = (CLIENT_ID, SECRET_KEY)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": CALLBACK_URL,
    }
    token_response = requests.post(token_url, headers=headers, data=data, auth=auth)

    if token_response.status_code != 200:
        return "Failed to fetch access token", 400

    access_token = token_response.json()["access_token"]

    # Fetch character information
    verify_url = "https://esi.evetech.net/verify/"
    verify_response = requests.get(verify_url, headers={"Authorization": f"Bearer {access_token}"})
    if verify_response.status_code != 200:
        return "Failed to verify token", 400

    character_info = verify_response.json()
    character_name = character_info["CharacterName"]

    # Store character in session
    if "characters" not in session:
        session["characters"] = {}
    session["characters"][character_name] = {"access_token": access_token}
    session.modified = True

    print("Updated session['characters']:", session["characters"])
    return redirect(url_for("index"))

# Home page
@app.route("/")
def index():
    characters = session.get("characters", {})
    return render_template("index.html", characters=characters)

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
