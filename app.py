from flask import Flask, request, redirect, jsonify, session
import psycopg2
import requests
import os
from flask_cors import CORS
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app)

app.secret_key = 'aabbccddeeffgghhii'
# Load environment variables
load_dotenv()

# Google OAuth config
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
DEFAULT_REDIRECT_URI = "https://backend-1-y7sg.onrender.com/auth/google/callback"

TOKEN_URI = "https://oauth2.googleapis.com/token"
USER_INFO_URI = "https://www.googleapis.com/oauth2/v2/userinfo"
UNITY_WEBGL_URL = "https://play.unity.com/en/games/a132ab5a-4b4f-4599-a485-7f383168e08c/web"

# AWS PostgreSQL config
DB_HOST = "database-1.crusmywccxmp.eu-north-1.rds.amazonaws.com"
DB_NAME = "Garden"
DB_USER = "postgresArr"
DB_PASSWORD = "Aromal-11-2003"

# Connect to PostgreSQL
def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn
# Add this to app.py
def initialize_database():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Create tables if they don't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gtokens (
                email VARCHAR(255) PRIMARY KEY,access_token TEXT
            );
            
            CREATE TABLE IF NOT EXISTS players (
                email VARCHAR(255) PRIMARY KEY,
                points INTEGER DEFAULT 0,
                last_login TIMESTAMP,
                FOREIGN KEY (email) REFERENCES gtokens (email)
            );
            
            CREATE TABLE IF NOT EXISTS tiles (
                email VARCHAR(255),
                position_x FLOAT,
                position_y FLOAT,
                position_z FLOAT,
                tile_type VARCHAR(100) NOT NULL,
                last_updated TIMESTAMP,
                PRIMARY KEY (email, position_x, position_y, position_z),
                FOREIGN KEY (email) REFERENCES gtokens (email)
            );
            
            CREATE TABLE IF NOT EXISTS player_positions (
                email VARCHAR(255) PRIMARY KEY,
                position_x FLOAT NOT NULL,
                position_y FLOAT NOT NULL,
                position_z FLOAT NOT NULL,
                last_updated TIMESTAMP,
                FOREIGN KEY (email) REFERENCES gtokens (email)
            );
            
            CREATE TABLE IF NOT EXISTS player_xp (
                email VARCHAR(255) PRIMARY KEY,
                current_level INTEGER DEFAULT 1,
                total_xp INTEGER DEFAULT 0,
                FOREIGN KEY (email) REFERENCES gtokens (email)
            );
            
            CREATE TABLE IF NOT EXISTS inventory_items (
               id SERIAL PRIMARY KEY,
                email VARCHAR(255),
                item_name VARCHAR(100) NOT NULL,
                quantity INTEGER NOT NULL,
                FOREIGN KEY (email) REFERENCES gtokens (email)
            );
        """)
        conn.commit()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Error initializing database: {e}")
    finally:
        cur.close()
        conn.close()

# Call this when the app starts
database_initialized = False

@app.before_request
def setup_database_before_request():
    global database_initialized
    if not database_initialized:
        initialize_database()
        database_initialized = True
# Store Google token in PostgreSQL
def store_token(email, access_token):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO gtokens (email, access_token)
        VALUES (%s, %s)
        ON CONFLICT (email)
        DO UPDATE SET access_token = EXCLUDED.access_token;
    """, (email, access_token))
    conn.commit()
    cur.close()
    conn.close()

# Google OAuth login route - this will be opened in browser

@app.route('/login')
def login():
    # Check if a custom redirect URI was provided (for Windows builds)
    redirect_uri = request.args.get('redirect_uri', DEFAULT_REDIRECT_URI)
    
    # Store the redirect_uri in session for later use
    session['redirect_uri'] = redirect_uri
    
    auth_uri = (
        "https://accounts.google.com/o/oauth2/auth"
        "?response_type=code"
        f"&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={DEFAULT_REDIRECT_URI}"  # Always use the backend callback first
        "&scope=openid%20email%20profile"
    )
    return redirect(auth_uri)

# Handle Google OAuth callback
@app.route('/auth/google/callback')
def google_callback():
    code = request.args.get('code')
    
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": DEFAULT_REDIRECT_URI,  # Use the same URI as in the auth request
        "grant_type": "authorization_code",
    }
    
    # Get access token
    token_response = requests.post(TOKEN_URI, data=data)
    token_data = token_response.json()
    access_token = token_data.get("access_token")

    # Get user info
    headers = {"Authorization": f"Bearer {access_token}"}
    user_info_response = requests.get(USER_INFO_URI, headers=headers)
    user_info = user_info_response.json()
    email = user_info.get("email")

    # Store in database
    if email and access_token:
        store_token(email, access_token)
        
        # Check if this is a Windows build redirect (has custom redirect URI)
        final_redirect_uri = session.get('redirect_uri')
        if final_redirect_uri and "localhost:3000" in final_redirect_uri:
            # For Windows builds, redirect to the local HTTP listener
            return redirect(f"{final_redirect_uri}?email={email}&token={access_token}")
        else:
            # Return the WebGL version for browser-based usage
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Login Successful</title>
                <script>
                    window.onload = function() {
                        console.log("OAuth callback window loaded");
                        try {
                            // Check if we were opened from another window
                            if (window.opener) {
                                console.log("Sending login data to Unity WebGL");
                                // Send message to parent window
                                window.opener.postMessage({
                                    type: 'LOGIN_SUCCESS',
                                    email: '%s',
                                    token: '%s'
                                }, '*');
                                
                                // Close this window after sending the message
                                setTimeout(function() {
                                    window.close();
                                }, 1000);
                            } else {
                                console.log("No opener found, redirecting");
                                // If not in a popup, redirect to the game with parameters
                                window.location.href = '%s?email=%s&token=%s';
                            }
                        } catch(e) {
                            console.error("Error in callback window:", e);
                            alert("Login successful! You can close this window and return to the game.");
                        }
                    };
                </script>
                <style>
                    body { 
                        font-family: Arial, sans-serif; 
                        text-align: center; 
                        padding-top: 50px;
                        background-color: #f0f8ff;
                    }
                    .success {
                        color: #2e8b57;
                        margin-bottom: 20px;
                    }
                    .info {
                        color: #4169e1;
                        font-size: 16px;
                    }
                </style>
            </head>
            <body>
                <h2 class="success">Login Successful!</h2>
                <p class="info">Logged in as: %s</p>
                <p>Returning to the game...</p>
            </body>
            </html>
            """ % (email, access_token, UNITY_WEBGL_URL, email, access_token, email)
    else:
        return jsonify({"error": "Login failed"}), 400

# Save player position
def save_player_position(email, pos_x, pos_y, pos_z):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO player_positions (email, position_x, position_y, position_z, last_updated)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (email)
        DO UPDATE SET 
            position_x = %s,
            position_y = %s,
            position_z = %s,
            last_updated = CURRENT_TIMESTAMP
    """, (email, pos_x, pos_y, pos_z, pos_x, pos_y, pos_z))
    conn.commit()
    cur.close()
    conn.close()

# Load player position
def load_player_position(email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT position_x, position_y, position_z
        FROM player_positions
        WHERE email = %s
    """, (email,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    if result:
        return result[0], result[1], result[2]
    else:
        return None, None, None

# Save player data and tile changes
# Example for save_game endpoint
@app.route('/save_game', methods=['POST'])
def save_game():
    try:
        data = request.json
        email = data.get('email')
        access_token = data.get('token')
        
        # Verify token matches what we have in database
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT access_token FROM gtokens WHERE email = %s", (email,))
            result = cur.fetchone()
            
            if not result or result[0] != access_token:
                return jsonify({"error": "Unauthorized", "details": "Invalid token"}), 401
            
            # Token is valid, save player data
            points = data.get('points', 0)
            player_pos_x = data.get('player_position_x')
            player_pos_y = data.get('player_position_y')
            player_pos_z = data.get('player_position_z')
            
            # Save or update player record
            cur.execute("""
                INSERT INTO players (email, points, last_login)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (email)
                DO UPDATE SET 
                    points = %s,
                    last_login = CURRENT_TIMESTAMP
            """, (email, points, points))
            
            # Save player position if provided
            if player_pos_x is not None and player_pos_y is not None:
                save_player_position(email, player_pos_x, player_pos_y, player_pos_z)
            
            # Process tile data
            tile_data = data.get('tile_data', [])
            for tile in tile_data:
                tile_name = tile.get('tileName')
                pos_x = tile.get('x')
                pos_y = tile.get('y')
                pos_z = tile.get('z')
                
                # Insert or update each tile
                cur.execute("""
                    INSERT INTO tiles (email, position_x, position_y, position_z, tile_type, last_updated)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (email, position_x, position_y, position_z)
                    DO UPDATE SET 
                        tile_type = %s,
                        last_updated = CURRENT_TIMESTAMP
                """, (email, pos_x, pos_y, pos_z, tile_name, tile_name))
            
            conn.commit()
            print(f"Game saved for {email}: {len(tile_data)} tiles, points: {points}")
            return jsonify({"success": True})
            
        except Exception as e:
            conn.rollback()
            print(f"Error saving game data: {e}")
            return jsonify({"error": "Database error", "details": str(e)}), 500
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error processing save_game request: {e}")
        return jsonify({"error": "Request error", "details": str(e)}), 400


# Add this to app.py
@app.route('/test_db', methods=['GET'])
def test_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        tables = []
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        for table in cur.fetchall():
            tables.append(table[0])
        cur.close()
        conn.close()
        
        return jsonify({
            "status": "Database connection successful",
            "tables": tables
        })
    except Exception as e:
        return jsonify({
            "status": "Database connection failed",
            "error": str(e)
        }), 500
# Load player data and tile changes
@app.route('/load_game', methods=['POST'])
def load_game():
    data = request.json
    email = data.get('email')
    access_token = data.get('token')
    
    # Verify token
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token FROM gtokens WHERE email = %s", (email,))
    result = cur.fetchone()
    
    if not result or result[0] != access_token:
        cur.close()
        conn.close()
        return jsonify({"error": "Unauthorized"}), 401
    
    # Token is valid, load player data
    cur.execute("""
        SELECT points FROM players
        WHERE email = %s
    """, (email,))
    
    player_result = cur.fetchone()
    
    # If player record doesn't exist, create one
    if not player_result:
        cur.execute("""
            INSERT INTO players (email, points, last_login)
            VALUES (%s, 0, CURRENT_TIMESTAMP)
        """, (email,))
        conn.commit()
        player_points = 0
    else:
        player_points = player_result[0]
    
    # Load player position
    pos_x, pos_y, pos_z = load_player_position(email)
    if pos_x is None:
        pos_x = data.get('player_position_x', 0)
        pos_y = data.get('player_position_y', 0)
        pos_z = data.get('player_position_z', 0)
    
    # Load tile data
    cur.execute("""
        SELECT position_x, position_y, position_z, tile_type
        FROM tiles
        WHERE email = %s
    """, (email,))
    
    tiles = cur.fetchall()
    tile_list = []
    
    for tile in tiles:
        tile_list.append({
            "x": tile[0],
            "y": tile[1],
            "z": tile[2],
            "tileName": tile[3]
        })
    
    cur.close()
    conn.close()
    
    return jsonify({
        "success": True,
        "points": player_points,
        "tile_data": tile_list,
        "player_position_x": pos_x,
        "player_position_y": pos_y,
        "player_position_z": pos_z
    })

# Optional: Add endpoint to delete specific tiles (useful for cleaning up)
@app.route('/delete_tile', methods=['POST'])
def delete_tile():
    data = request.json
    email = data.get('email')
    access_token = data.get('token')
    pos_x = data.get('x')
    pos_y = data.get('y')
    pos_z = data.get('z')
    
    # Verify token
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token FROM gtokens WHERE email = %s", (email,))
    result = cur.fetchone()
    
    if not result or result[0] != access_token:
        cur.close()
        conn.close()
        return jsonify({"error": "Unauthorized"}), 401
    
    # Delete the tile
    cur.execute("""
        DELETE FROM tiles
        WHERE email = %s AND position_x = %s AND position_y = %s AND position_z = %s
    """, (email, pos_x, pos_y, pos_z))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({"success": True})



    # Add these functions after your existing database functions

# XP system functions
def save_player_xp(email, current_level, total_xp):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO player_xp (email, current_level, total_xp)
        VALUES (%s, %s, %s)
        ON CONFLICT (email)
        DO UPDATE SET 
            current_level = %s,
            total_xp = %s
    """, (email, current_level, total_xp, current_level, total_xp))
    conn.commit()
    cur.close()
    conn.close()

def load_player_xp(email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT current_level, total_xp
        FROM player_xp
        WHERE email = %s
    """, (email,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    if result:
        return result[0], result[1]  # current_level, total_xp
    else:
        return 1, 0  # Default values if no record found

# Inventory functions
def save_inventory_items(email, items):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # First delete any existing items for this user
    cur.execute("DELETE FROM inventory_items WHERE email = %s", (email,))
    
    # Then insert all current items
    for item in items:
        item_name = item.get('itemName')
        quantity = item.get('quantity')
        
        if quantity > 0:  # Only save items with quantity > 0
            cur.execute("""
                INSERT INTO inventory_items (email, item_name, quantity)
                VALUES (%s, %s, %s)
            """, (email, item_name, quantity))
    
    conn.commit()
    cur.close()
    conn.close()

def load_inventory_items(email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT item_name, quantity
        FROM inventory_items
        WHERE email = %s
    """, (email,))
    
    items = []
    for row in cur.fetchall():
        items.append({
            "itemName": row[0],
            "quantity": row[1]
        })
    
    cur.close()
    conn.close()
    return items

# Add these new endpoints to handle XP and inventory data

# Add XP/level save endpoint (can be added to existing save_game route)
@app.route('/save_xp', methods=['POST'])
def save_xp():
    data = request.json
    email = data.get('email')
    access_token = data.get('token')
    
    # Verify token matches what we have in database
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token FROM gtokens WHERE email = %s", (email,))
    result = cur.fetchone()
    
    if not result or result[0] != access_token:
        cur.close()
        conn.close()
        return jsonify({"error": "Unauthorized"}), 401
    
    # Token is valid, save XP data
    current_level = data.get('current_level', 1)
    total_xp = data.get('total_xp', 0)
    
    save_player_xp(email, current_level, total_xp)
    
    cur.close()
    conn.close()
    
    return jsonify({"success": True})

# Add XP/level load endpoint
@app.route('/load_xp', methods=['POST'])
def load_xp():
    data = request.json
    email = data.get('email')
    access_token = data.get('token')
    
    # Verify token
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token FROM gtokens WHERE email = %s", (email,))
    result = cur.fetchone()
    
    if not result or result[0] != access_token:
        cur.close()
        conn.close()
        return jsonify({"error": "Unauthorized"}), 401
    
    # Token is valid, load XP data
    current_level, total_xp = load_player_xp(email)
    
    cur.close()
    conn.close()
    
    return jsonify({
        "success": True,
        "current_level": current_level,
        "total_xp": total_xp
    })

# Add inventory save endpoint
@app.route('/save_inventory', methods=['POST'])
def save_inventory():
    try:
        data = request.json
        email = data.get('email')
        access_token = data.get('token')
        
        # Verify token
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT access_token FROM gtokens WHERE email = %s", (email,))
            result = cur.fetchone()
            
            if not result or result[0] != access_token:
                return jsonify({"error": "Unauthorized", "details": "Invalid token"}), 401
            
            # Token is valid, save inventory data
            inventory_items = data.get('inventory_items', [])
            
            # First delete any existing items for this user
            cur.execute("DELETE FROM inventory_items WHERE email = %s", (email,))
            
            # Then insert all current items
            item_count = 0
            for item in inventory_items:
                item_name = item.get('itemName')
                quantity = item.get('quantity', 0)
                
                if quantity > 0:  # Only save items with quantity > 0
                    cur.execute("""
                        INSERT INTO inventory_items (email, item_name, quantity)
                        VALUES (%s, %s, %s)
                    """, (email, item_name, quantity))
                    item_count += 1
            
            conn.commit()
            print(f"Saved {item_count} inventory items for {email}")
            
            return jsonify({"success": True})
            
        except Exception as e:
            conn.rollback()
            print(f"Error saving inventory: {e}")
            return jsonify({"error": "Database error", "details": str(e)}), 500
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error processing save_inventory request: {e}")
        return jsonify({"error": "Request error", "details": str(e)}), 400
# Add inventory load endpoint
@app.route('/load_inventory', methods=['POST'])
def load_inventory():
    data = request.json
    email = data.get('email')
    access_token = data.get('token')
    
    # Verify token
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token FROM gtokens WHERE email = %s", (email,))
    result = cur.fetchone()
    
    if not result or result[0] != access_token:
        cur.close()
        conn.close()
        return jsonify({"error": "Unauthorized"}), 401
    
    # Token is valid, load inventory data
    items = load_inventory_items(email)
    
    cur.close()
    conn.close()
    
    return jsonify({
        "success": True,
        "inventory_items": items
    })

@app.route('/logout', methods=['POST'])
def logout():
    data = request.json
    email = data.get('email')
    access_token = data.get('token')
    
    # Verify token before proceeding
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token FROM gtokens WHERE email = %s", (email,))
    result = cur.fetchone()
    
    if not result or result[0] != access_token:
        cur.close()
        conn.close()
        return jsonify({"error": "Unauthorized"}), 401
    
    # Optional: Invalidate the token in database
    # You could set it to NULL or flag it as inactive
    cur.execute("""
        UPDATE gtokens
        SET access_token = NULL
        WHERE email = %s
    """, (email,))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({"success": True, "message": "Successfully logged out"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)