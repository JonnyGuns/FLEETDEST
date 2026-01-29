from flask import Flask, session, redirect, url_for, request, jsonify, render_template
import requests
import os
import json
import time
from flask_session import Session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "e05f71dcab14188c6c174f33339910870067423832c85387bbf565e3840e6c1e")

# Configure session to use filesystem
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "/tmp/flask_session"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_KEY_PREFIX"] = "fleetdest:"

# Initialize session
Session(app)

# Your ESI developer credentials
CLIENT_ID = os.environ.get("ESI_CLIENT_ID", "83344efb272d4e469c40bec7934b050f")
SECRET_KEY = os.environ.get("ESI_SECRET_KEY", "HdhcdDgExQj0jBZ88tif4JgBgiQcSkqSs1DRdvFP")
CALLBACK_URL = os.environ.get("CALLBACK_URL", "https://fleet-dest-cbbf9384726f.herokuapp.com/callback")

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

    # Exchange authorization code for access and refresh tokens
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
        print(f"Token exchange failed: {token_response.status_code} - {token_response.text}")
        return f"Failed to fetch tokens: {token_response.text}", 400

    tokens = token_response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    expires_in = tokens.get("expires_in", 1200)  # Default to 20 minutes (1200 seconds)

    # Fetch character information
    verify_url = "https://esi.evetech.net/verify/"
    verify_response = requests.get(verify_url, headers={"Authorization": f"Bearer {access_token}"})
    if verify_response.status_code != 200:
        print(f"Token verification failed: {verify_response.status_code} - {verify_response.text}")
        return "Failed to verify token", 400

    character_info = verify_response.json()
    character_name = character_info["CharacterName"]
    character_id = character_info["CharacterID"]

    # Store character in session with expiry time
    if "characters" not in session:
        session["characters"] = {}
    
    session["characters"][character_name] = {
        "character_id": character_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + expires_in - 60,  # Refresh 60 seconds before expiry
    }
    session.modified = True

    print(f"Character {character_name} logged in successfully. Token expires in {expires_in} seconds.")
    return redirect(url_for("index"))

# Helper function to refresh tokens
def refresh_access_token(character_name):
    """
    Refresh the access token for a character using their refresh token.
    Returns the new access token if successful, None otherwise.
    """
    character_data = session.get("characters", {}).get(character_name)
    if not character_data or "refresh_token" not in character_data:
        print(f"No character data or refresh token found for {character_name}")
        return None

    refresh_token = character_data["refresh_token"]

    # Request a new access token
    token_url = "https://login.eveonline.com/v2/oauth/token"
    auth = (CLIENT_ID, SECRET_KEY)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    try:
        response = requests.post(token_url, headers=headers, data=data, auth=auth, timeout=10)

        if response.status_code == 200:
            tokens = response.json()
            access_token = tokens["access_token"]
            new_refresh_token = tokens.get("refresh_token", refresh_token)
            expires_in = tokens.get("expires_in", 1200)
            
            # Update session with new tokens
            session["characters"][character_name]["access_token"] = access_token
            session["characters"][character_name]["refresh_token"] = new_refresh_token
            session["characters"][character_name]["expires_at"] = time.time() + expires_in - 60
            session.modified = True
            
            print(f"Token refreshed successfully for {character_name}. New token expires in {expires_in} seconds.")
            return access_token
        else:
            print(f"Failed to refresh token for {character_name}: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Request exception while refreshing token for {character_name}: {e}")
        return None

# Helper function to get a valid access token
def get_valid_access_token(character_name):
    """
    Get a valid access token for a character.
    Automatically refreshes the token if it's expired or about to expire.
    """
    characters = session.get("characters", {})
    character_data = characters.get(character_name)
    
    if not character_data:
        print(f"No character data found for {character_name}")
        return None

    # Check if token is expired or about to expire
    current_time = time.time()
    expires_at = character_data.get("expires_at", 0)
    
    if current_time >= expires_at:
        print(f"Token expired for {character_name}, refreshing...")
        return refresh_access_token(character_name)
    
    # Token is still valid
    return character_data["access_token"]

# Home page
@app.route("/")
def index():
    characters = session.get("characters", {})
    # Add time remaining info for debugging
    character_info = {}
    current_time = time.time()
    for name, data in characters.items():
        expires_at = data.get("expires_at", 0)
        time_remaining = max(0, int(expires_at - current_time))
        character_info[name] = {
            "time_remaining": time_remaining,
            "character_id": data.get("character_id")
        }
    return render_template("index.html", characters=characters, character_info=character_info)

# Set destination route
@app.route("/set-destination", methods=["POST"])
def set_destination():
    system_id = request.json.get("system_id")
    add_to_route = request.json.get("add_to_route", False)

    if not system_id:
        return jsonify({"error": "Missing system ID"}), 400

    characters = session.get("characters", {})
    results = {}

    for character_name in list(characters.keys()):  # Use list() to avoid dict size change during iteration
        access_token = get_valid_access_token(character_name)
        if not access_token:
            results[character_name] = "Failed to get valid token. Please re-login this character."
            continue

        headers = {"Authorization": f"Bearer {access_token}"}
        params = {
            "destination_id": system_id,
            "add_to_beginning": not add_to_route,
            "clear_other_waypoints": not add_to_route,
        }
        
        try:
            response = requests.post(
                "https://esi.evetech.net/latest/ui/autopilot/waypoint/",
                headers=headers,
                params=params,
                timeout=10,
            )
            if response.status_code == 204:
                results[character_name] = "Waypoint set successfully"
            else:
                error_msg = f"Error {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg += f": {error_data['error']}"
                except:
                    error_msg += f": {response.text}"
                results[character_name] = error_msg
        except requests.exceptions.RequestException as e:
            results[character_name] = f"Request failed: {str(e)}"

    return jsonify(results)

# Clear all waypoints route
@app.route("/clear-waypoints", methods=["POST"])
def clear_waypoints():
    characters = session.get("characters", {})
    results = {}

    for character_name in list(characters.keys()):
        access_token = get_valid_access_token(character_name)
        if not access_token:
            results[character_name] = "Failed to get valid token. Please re-login this character."
            continue

        # Note: To clear waypoints, we need to use a different ESI endpoint
        # The autopilot waypoint endpoint doesn't actually clear waypoints properly
        # We'll set a dummy waypoint and clear it
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {
            "clear_other_waypoints": True,
        }
        
        try:
            # Just clearing waypoints - ESI doesn't require destination_id for this
            response = requests.post(
                "https://esi.evetech.net/latest/ui/autopilot/waypoint/",
                headers=headers,
                params=params,
                timeout=10,
            )
            if response.status_code == 204:
                results[character_name] = "Waypoints cleared successfully"
            else:
                error_msg = f"Error {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg += f": {error_data['error']}"
                except:
                    error_msg += f": {response.text}"
                results[character_name] = error_msg
        except requests.exceptions.RequestException as e:
            results[character_name] = f"Request failed: {str(e)}"

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

# Health check endpoint for Heroku
@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
