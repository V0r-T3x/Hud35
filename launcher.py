#!/usr/bin/env python3
from flask import Flask, request, redirect, url_for, flash, Response, render_template
from spotipy.oauth2 import SpotifyOAuth
from datetime import datetime, timedelta
from collections import Counter
import os, toml, time, requests, subprocess, sys, signal, urllib.parse, socket, logging, threading, json

app = Flask(__name__)
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response
app.secret_key = 'hud-launcher-secret-key'

CONFIG_PATH = "config.toml"
DEFAULT_CONFIG = {
    "display": {
        #"type": "st7789",
        "type": "framebuffer",
        "framebuffer": "/dev/fb1",
        "rotation": 0,
        #"st7789": {
        #    "spi_port": 0,
        #    "spi_cs": 1,
        #    "dc_pin": 9,
        #    "backlight_pin": 13,
        #    "rotation": 0,
        #    "spi_speed": 60000000
        #}
    },
    "fonts": {
        "large_font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "large_font_size": 36,
        "medium_font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "medium_font_size": 24,
        "small_font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "small_font_size": 16,
        "spot_large_font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "spot_large_font_size": 26,
        "spot_medium_font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "spot_medium_font_size": 18,
        "spot_small_font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "spot_small_font_size": 12
    },
    "api_keys": {
        "openweather": "",
        "google_geo": "",
        "client_id": "",
        "client_secret": ""
    },
    "settings": {
        "fallback_city": "",
        "use_gpsd": True,
        "use_google_geo": True,
        "time_display": True,
        "enable_current_track_display": True
    },
    "clock": {
        "type": "digital",
        "background": "color", 
        "color": "#000000"
    },
    "wifi": {
        "ap_ssid": "Neonwifi-Manager",
        "ap_ip": "192.168.42.1",
    },
    "buttons": {
        "button_a": 5,
        "button_b": 6,
        "button_x": 16,
        "button_y": 24
    },
    "auto_start": {
        "auto_start_hud35": True,
        "auto_start_neonwifi": True,
        "check_internet": True
    },
    "ui": {
        "theme": "dark"
    }
}

hud35_process = None
neonwifi_process = None
last_logged_song = None
def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f:
            toml.dump(DEFAULT_CONFIG, f)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, 'r') as f:
            loaded_config = toml.load(f)
        
        import copy
        merged_config = copy.deepcopy(DEFAULT_CONFIG)
        
        for category, items in loaded_config.items():
            if category in merged_config and isinstance(merged_config[category], dict):
                for key, value in items.items():
                    merged_config[category][key] = value
            else:
                merged_config[category] = items

        save_config(merged_config)
        return merged_config
    except Exception as e:
        logger = logging.getLogger('Launcher')
        logger.error(f"Error loading or merging config: {e}. Backing up and using defaults.")
        if os.path.exists(CONFIG_PATH):
            os.rename(CONFIG_PATH, f"{CONFIG_PATH}.bak")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        toml.dump(config, f)

def setup_logging():
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('hud35.log')
        ]
    )
    return logging.getLogger('Launcher')

def check_internet_connection(timeout=5):
    try:
        response = requests.get("http://www.google.com", timeout=timeout)
        return response.status_code == 200
    except requests.RequestException:
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=timeout)
            return True
        except socket.error:
            return False

def wait_for_internet(timeout=60, check_interval=5):
    logger = logging.getLogger('Launcher')
    logger.info("🔍 Waiting for internet connection...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_internet_connection():
            logger.info("✅ Internet connection established")
            return True
        logger.info("⏳ No internet connection, waiting...")
        time.sleep(check_interval)
    logger.error("❌ Internet connection timeout")
    return False

def auto_launch_applications():
    logger = logging.getLogger('Launcher')
    config = load_config()
    auto_config = config.get("auto_start", {})
    logger.info("🔧 Auto-launching applications based on configuration...")
    if auto_config.get("check_internet", True):
        if not wait_for_internet(timeout=30):
            logger.warning("❌ No internet - starting neonwifi if enabled")
            if auto_config.get("auto_start_neonwifi", True):
                start_neonwifi()
            return
    if auto_config.get("auto_start_neonwifi", True):
        start_neonwifi()
    if auto_config.get("auto_start_hud35", True):
        spotify_authenticated, _ = check_spotify_auth()
        config_ready = is_config_ready()
        if config_ready and spotify_authenticated:
            start_hud35()
            logger.info("✅ HUD35 auto-started")
        else:
            if not config_ready: pass # The reason is already logged by is_config_ready()
            elif not spotify_authenticated: logger.warning("⚠️ HUD35 not auto-started: Spotify not authenticated.")

def is_config_ready():
    config = load_config()
    logger = logging.getLogger('Launcher')
    missing_keys = []
    if not config["api_keys"].get("openweather"):
        missing_keys.append("OpenWeather")
    if not config["api_keys"].get("client_id"):
        missing_keys.append("Spotify Client ID")
    if not config["api_keys"].get("client_secret"):
        missing_keys.append("Spotify Client Secret")
    
    if missing_keys:
        logger.warning(f"Configuration is missing the following required API keys: {', '.join(missing_keys)}")
        return False
    
    return True

def check_spotify_auth():
    config = load_config()
    if not config["api_keys"]["client_id"] or not config["api_keys"]["client_secret"]:
        return False, None
    try:
        if not os.path.exists(".spotify_cache"):
            return False, None
        sp_oauth = SpotifyOAuth(
            client_id=config["api_keys"]["client_id"],
            client_secret=config["api_keys"]["client_secret"],
            redirect_uri="http://127.0.0.1:5000/callback",
            scope="user-read-currently-playing",
            cache_path=".spotify_cache"
        )
        token_info = sp_oauth.get_cached_token()
        if not token_info:
            return False, None
        if isinstance(token_info, dict):
            access_token = token_info.get('access_token')
        else:
            access_token = token_info
            
        if not access_token:
            return False, None
        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            response = requests.get('https://api.spotify.com/v1/me', headers=headers, timeout=5)
            if response.status_code == 200:
                return True, "Valid token"
            else:
                print(f"Token validation failed with status {response.status_code}")
                return False, None
        except Exception as e:
            print(f"Token validation error: {e}")
            return False, None
    except Exception as e:
        print(f"Error checking Spotify auth: {e}")
        return False, None

def is_hud35_running():
    global hud35_process
    if hud35_process is not None:
        if hud35_process.poll() is None:
            return True
        else:
            hud35_process = None
    return False

def is_neonwifi_running():
    global neonwifi_process
    if neonwifi_process is not None:
        if neonwifi_process.poll() is None:
            return True
        else:
            neonwifi_process = None
    try:
        result = subprocess.run(['pgrep', '-f', 'neonwifi.py'], 
                            capture_output=True, text=True)
        return bool(result.stdout.strip())
    except Exception:
        return False

def parse_song_from_log(log_line):
    if 'Now playing:' in log_line:
        try:
            if '🎵 Now playing:' in log_line:
                song_part = log_line.split('🎵 Now playing: ')[1].strip()
            else:
                song_part = log_line.split('Now playing: ')[1].strip()
            if ' -- ' in song_part:
                artist_part, song = song_part.split(' -- ', 1)
            elif ' - ' in song_part:
                artist_part, song = song_part.split(' - ', 1)
            else:
                artist_part = 'Unknown Artist'
                song = song_part
            artists = [artist.strip() for artist in artist_part.split(',')]
            return {
                'song': song.strip(),
                'artist': artist_part.strip(),
                'artists': artists,
                'full_track': f"{artist_part} -- {song}".strip()
            }
        except Exception as e:
            logger = logging.getLogger('Launcher')
            logger.error(f"Error parsing song from log: {e}")
            return None
    return None

def start_hud35():
    global hud35_process, last_logged_song
    logger = logging.getLogger('Launcher')
    if is_hud35_running():
        logger.warning("HUD35 is already running, no action taken.")
        return False, "HUD35 is already running"
    try:
        hud35_process = subprocess.Popen(
            [sys.executable, 'hud35.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        logger.info(f"🚀 Starting HUD35 with PID: {hud35_process.pid}")
        def log_hud35_output():
            for line in iter(hud35_process.stdout.readline, ''):
                if line.strip():
                    logger.info(f"[HUD35] {line.strip()}")
                    # PUT IT HERE - replace the existing song logging
                    song_info = parse_song_from_log(line)
                    if song_info:
                        update_song_count(song_info)
        def monitor_current_track_state():
            while hud35_process and hud35_process.poll() is None:
                log_current_track_state()
                time.sleep(1)
        output_thread = threading.Thread(target=log_hud35_output)
        output_thread.daemon = True
        output_thread.start()
        track_monitor_thread = threading.Thread(target=monitor_current_track_state)
        track_monitor_thread.daemon = True
        track_monitor_thread.start()
        time.sleep(2)
        if hud35_process.poll() is None:
            return True, "HUD35 started successfully"
        else:
            return False, "HUD35 failed to start (check hud35.log for details)"
    except Exception as e:
        logger.error(f"Error starting HUD35: {str(e)}")
        return False, f"Error starting HUD35: {str(e)}"

def stop_hud35():
    global hud35_process, last_logged_song
    logger = logging.getLogger('Launcher')
    if not is_hud35_running():
        logger.warning("HUD35 is not running, no action taken.")
        return False, "HUD35 is not running"
    try:
        logger.info(f"🛑 Stopping HUD35 with PID: {hud35_process.pid}...")
        hud35_process.terminate()
        try:
            hud35_process.wait(timeout=5)
            logger.info(f"HUD35 process {hud35_process.pid} terminated gracefully.")
        except subprocess.TimeoutExpired:
            hud35_process.kill()
            hud35_process.wait()
        hud35_process = None
        last_logged_song = None
        logger.info("HUD35 stopped successfully")
        return True, "HUD35 stopped successfully"
    except Exception as e:
        logger.error(f"Error stopping HUD35: {str(e)}")
        return False, f"Error stopping HUD35: {str(e)}"

def start_neonwifi():
    global neonwifi_process
    logger = logging.getLogger('Launcher')
    if is_neonwifi_running():
        logger.warning("neonwifi is already running, no action taken.")
        return False, "neonwifi is already running"
    try:
        neonwifi_process = subprocess.Popen(
            [sys.executable, 'neonwifi.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        logger.info(f"🚀 Starting neonwifi with PID: {neonwifi_process.pid}")
        def log_neonwifi_output():
            for line in iter(neonwifi_process.stdout.readline, ''):
                if line.strip():
                    logger.info(f"[neonwifi] {line.strip()}")
        output_thread = threading.Thread(target=log_neonwifi_output)
        output_thread.daemon = True
        output_thread.start()
        time.sleep(3)
        if neonwifi_process.poll() is None:
            return True, "neonwifi started successfully"
        else:
            return False, "neonwifi failed to start (check hud35.log for details)"
    except Exception as e:
        logger.error(f"Error starting neonwifi: {str(e)}")
        return False, f"Error starting neonwifi: {str(e)}"

def stop_neonwifi():
    global neonwifi_process
    logger = logging.getLogger('Launcher')
    if not is_neonwifi_running():
        logger.warning("neonwifi is not running, no action taken.")
        return False, "neonwifi is not running"
    try:
        pid_to_stop = neonwifi_process.pid if neonwifi_process else "N/A"
        logger.info(f"🛑 Stopping neonwifi with PID: {pid_to_stop}...")
        if neonwifi_process:
            neonwifi_process.terminate()
            try:
                neonwifi_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                neonwifi_process.kill()
                neonwifi_process.wait()
            neonwifi_process = None
        subprocess.run(['pkill', '-f', 'neonwifi.py'], check=False)
        time.sleep(2)
        logger.info("neonwifi stopped successfully")
        return True, "neonwifi stopped successfully"
    except Exception as e:
        logger.error(f"Error stopping neonwifi: {str(e)}")
        return False, f"Error stopping neonwifi: {str(e)}"

@app.context_processor
def utility_processor():
    return dict(zip=zip)

@app.route('/')
def index():
    config = load_config()
    auto_config = config.get("auto_start", {})
    ui_config = config.get("ui", {"theme": "dark"}) 
    config_ready = is_config_ready()
    spotify_configured = bool(config["api_keys"]["client_id"] and config["api_keys"]["client_secret"])
    spotify_authenticated, _ = check_spotify_auth()
    hud35_running = is_hud35_running()
    neonwifi_running = is_neonwifi_running()
    enable_current_track = config["settings"].get("enable_current_track_display", True)
    return render_template(
        'setup.html', 
        config=config, 
        config_ready=config_ready,
        spotify_configured=spotify_configured,
        spotify_authenticated=spotify_authenticated,
        hud35_running=hud35_running,
        neonwifi_running=neonwifi_running,
        auto_config=auto_config,
        enable_current_track_display=enable_current_track,
        ui_config=ui_config
    )

@app.route('/toggle_theme', methods=['POST'])
def toggle_theme():
    config = load_config()
    new_theme = request.form.get('theme', 'dark')
    if 'ui' not in config:
        config['ui'] = {}
    config['ui']['theme'] = new_theme
    save_config(config)
    return redirect(url_for('index'))

@app.route('/toggle_themeac', methods=['POST'])
def toggle_themeac():
    config = load_config()
    new_theme = request.form.get('theme', 'dark')
    if 'ui' not in config:
        config['ui'] = {}
    config['ui']['theme'] = new_theme
    save_config(config)
    return redirect(url_for('advanced_config'))

@app.route('/save_all_config', methods=['POST'])
def save_all_config():
    config = load_config()

    # API Keys
    config["api_keys"]["openweather"] = request.form.get('openweather', '')
    config["api_keys"]["client_id"] = request.form.get('client_id', '')
    config["api_keys"]["client_secret"] = request.form.get('client_secret', '')
    config["api_keys"]["google_geo"] = request.form.get('google_geo', '')

    # Auto-start settings
    auto_start_hud35 = 'auto_start_hud35' in request.form
    auto_start_neonwifi = 'auto_start_neonwifi' in request.form
    config["auto_start"] = {
        "auto_start_hud35": auto_start_hud35,
        "auto_start_neonwifi": auto_start_neonwifi
    }

    save_config(config)
    if is_hud35_running():
        stop_hud35()
        time.sleep(3)
    if auto_start_hud35 == True:
        start_hud35()
    if is_neonwifi_running():
        stop_neonwifi()
        time.sleep(3)
    if auto_start_neonwifi == True:
        start_neonwifi()
    flash('success', 'All settings saved successfully!')
    return redirect(url_for('index'))

@app.route('/start_hud35', methods=['POST'])
def start_hud35_route():
    success, message = start_hud35()
    if success:
        flash('success', message)
    else:
        flash('error', message)
    return redirect(url_for('index'))

@app.route('/stop_hud35', methods=['POST'])
def stop_hud35_route():
    success, message = stop_hud35()
    if success:
        flash('success', message)
    else:
        flash('error', message)
    return redirect(url_for('index'))

@app.route('/start_neonwifi', methods=['POST'])
def start_neonwifi_route():
    success, message = start_neonwifi()
    if success:
        flash('success', message)
    else:
        flash('error', message)
    return redirect(url_for('index'))

@app.route('/stop_neonwifi', methods=['POST'])
def stop_neonwifi_route():
    success, message = stop_neonwifi()
    if success:
        flash('success', message)
    else:
        flash('error', message)
    return redirect(url_for('index'))

@app.route('/spotify_auth')
def spotify_auth_page():
    config = load_config()
    lan_ips = []
    try:
        hostname = socket.gethostname()
        all_ips = socket.getaddrinfo(hostname, None)
        for addr_info in all_ips:
            ip = addr_info[4][0]
            if '.' in ip and not ip.startswith('127.'):
                lan_ips.append(ip)
        lan_ips = list(set(lan_ips))
    except Exception:
        pass


    if not config["api_keys"]["client_id"] or not config["api_keys"]["client_secret"]:
        flash('error', 'Please save Spotify Client ID and Secret first.')
        return redirect(url_for('index'))
    
    port = request.host.split(':')[-1] if ':' in request.host else '5000'
    
    # Prefer LAN IP for easier one-click auth if available, otherwise fallback to localhost
    if lan_ips:
        # Use the first LAN IP found. The user must add this to their Spotify Dashboard.
        redirect_uri = f"http://{lan_ips[0]}:{port}/callback"
    else:
        # Fallback for systems where LAN IP can't be determined.
        redirect_uri = f"http://127.0.0.1:{port}/callback"

    try:
        sp_oauth = SpotifyOAuth(
            client_id=config["api_keys"]["client_id"],
            client_secret=config["api_keys"]["client_secret"],
            redirect_uri=redirect_uri,
            scope="user-read-currently-playing",
            cache_path=".spotify_cache",
            show_dialog=True
        )
        auth_url = sp_oauth.get_authorize_url()
        return render_template('spotify_auth.html', auth_url=auth_url, lan_ips=lan_ips, port=port)
    except Exception as e:
        flash('error', f'Spotify authentication error: {str(e)}')
        return redirect(url_for('index'))

@app.route('/callback', methods=['POST'])
def callback():
    config = load_config()
    logger = logging.getLogger('Launcher')

    # Handle both GET from Spotify redirect and POST from manual paste
    if request.method == 'POST':
        callback_url = request.form.get('callback_url', '').strip()
        if not callback_url:
            flash('error', 'Please paste the callback URL')
            return redirect(url_for('spotify_auth_page'))
        parsed_url = urllib.parse.urlparse(callback_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
    else: # GET request, which is not yet handled by this route.
        # This part of the logic will be added in the next step.
        # For now, we are just modifying the POST logic.
        flash('error', 'Automated callback not yet implemented for GET.')
        return redirect(url_for('spotify_auth_page'))

    try:
        if 'error' in query_params:
            error = query_params['error'][0]
            flash('error', f'Spotify authentication failed: {error}')
            return redirect(url_for('index'))
        if 'code' not in query_params:
            flash('error', 'No authorization code found in the URL.')
            return redirect(url_for('spotify_auth_page'))
        
        port = request.host.split(':')[-1] if ':' in request.host else '5000'
        redirect_uri = f"http://127.0.0.1:{port}/callback"
        
        logger.info(f"Attempting Spotify authentication with redirect URI: {redirect_uri}")
        code = query_params.get('code')[0]
        logger.info(f"Received Spotify authorization code starting with: {code[:10]}...")
        sp_oauth = SpotifyOAuth(
            client_id=config["api_keys"]["client_id"],
            client_secret=config["api_keys"]["client_secret"],
            redirect_uri=redirect_uri,
            scope="user-read-currently-playing",
            cache_path=".spotify_cache"
        )
        logger.info("Requesting access token from Spotify...")
        token_info = sp_oauth.get_access_token(code)
        if token_info:
            logger.info("✅ Spotify authentication successful! Token received.")
            flash('success', 'Spotify authentication successful!')
        else:
            logger.error("❌ Spotify authentication failed: get_access_token returned no token.")
            flash('error', 'Spotify authentication failed.')
    except Exception as e:
        logger.error(f"❌ Exception during Spotify token exchange: {str(e)}")
        flash('error', f'Authentication error: {str(e)}')
        if os.path.exists(".spotify_cache"):
            os.remove(".spotify_cache")
    return redirect(url_for('index'))

@app.route('/view_logs')
def view_logs():
    lines = request.args.get('lines', 100, type=int)
    live = request.args.get('live', False, type=bool)
    config = load_config()
    ui_config = config.get("ui", {"theme": "dark"})
    current_theme = ui_config.get("theme", "dark")
    log_file = 'hud35.log'
    
    if not os.path.exists(log_file):
        return "No log file found", 404
    
    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if lines > 0 else all_lines
            log_content = ''.join(recent_lines)
    except Exception as e:
        log_content = f"Error reading log file: {str(e)}"
    
    if live:
        return log_content
    
    return render_template('logs.html',
        log_content=log_content,
        lines=lines,
        current_theme=current_theme
    )

@app.route('/clear_logs', methods=['POST'])
def clear_logs():
    log_file = 'hud35.log'
    try:
        with open(log_file, 'w') as f:
            f.write('')
        return 'Logs cleared', 200
    except Exception as e:
        return f'Error clearing logs: {str(e)}', 500

@app.route('/music_stats_data')
def music_stats_data():
    try:
        lines = int(request.args.get('lines', 1000))
    except:
        lines = 1000
    song_counts = load_song_counts()
    song_stats, artist_stats = generate_music_stats(song_counts, lines)
    song_chart_data = generate_chart_data(song_stats, 'Songs')
    artist_chart_data = generate_chart_data(artist_stats, 'Artists')
    song_chart_items = list(zip(song_chart_data['labels'], song_chart_data['data'], song_chart_data['colors']))
    artist_chart_items = list(zip(artist_chart_data['labels'], artist_chart_data['data'], artist_chart_data['colors']))
    
    total_plays = sum(song_counts.values())
    unique_songs = len(song_counts)
    unique_artists = len(artist_stats)
    return {
        'song_chart_items': song_chart_items,
        'artist_chart_items': artist_chart_items,
        'total_plays': total_plays,
        'unique_songs': unique_songs,
        'unique_artists': unique_artists
    }

@app.route('/music_stats')
def music_stats():
    config = load_config()
    ui_config = config.get("ui", {"theme": "dark"})
    try:
        lines = int(request.args.get('lines', 1000))
    except:
        lines = 1000
    song_counts = load_song_counts()
    song_stats, artist_stats = generate_music_stats(song_counts, lines)
    song_chart_data = generate_chart_data(song_stats, 'Songs')
    artist_chart_data = generate_chart_data(artist_stats, 'Artists')
    song_chart_items = list(zip(song_chart_data['labels'], song_chart_data['data'], song_chart_data['colors']))
    artist_chart_items = list(zip(artist_chart_data['labels'], artist_chart_data['data'], artist_chart_data['colors']))
    total_plays = sum(song_counts.values())
    unique_songs = len(song_counts)
    unique_artists = len(artist_stats)
    return render_template('music_stats.html', 
                        song_chart_items=song_chart_items,
                        artist_chart_items=artist_chart_items,
                        lines=lines,
                        total_plays=total_plays,
                        unique_songs=unique_songs,
                        unique_artists=unique_artists,
                        ui_config=ui_config)

@app.route('/stream/current_track')
def stream_current_track():
    def generate():
        last_data = None
        while True:
            current_track = get_current_track()
            track_data = {
                'song': current_track['song'],
                'artist': current_track['artist'],
                'album': current_track['album'],
                'progress': current_track['progress'],
                'duration': current_track['duration'],
                'is_playing': current_track['is_playing'],
                'has_track': current_track['has_track'],
                'timestamp': datetime.now().isoformat()
            }
            if track_data != last_data:
                yield f"data: {json.dumps(track_data)}\n\n"
                last_data = track_data
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/current_track')
def api_current_track():
    current_track = get_current_track()
    return {
        'track': current_track,
        'timestamp': datetime.now().isoformat()
    }

@app.route('/clear_song_logs', methods=['POST'])
def clear_song_logs():
    try:
        with open('song_counts.toml', 'w') as f:
            f.write('# Song play counts\n')
            f.write('# Generated by HUD35 Launcher\n\n')
            f.write('[song_counts]\n')
        return 'Song logs cleared', 200
    except Exception as e:
        return f'Error clearing song logs: {str(e)}', 500

@app.route('/advanced_config')
def advanced_config():
    config = load_config()
    config_ready = is_config_ready()
    spotify_configured = bool(config["api_keys"]["client_id"] and config["api_keys"]["client_secret"])
    spotify_authenticated, _ = check_spotify_auth()
    ui_config = config.get("ui", {"theme": "dark"})
    return render_template('advanced_config.html',
            config=config, 
            spotify_configured=spotify_configured,
            spotify_authenticated=spotify_authenticated,
            ui_config=ui_config
        )

@app.route('/save_advanced_config', methods=['POST'])
def save_advanced_config():
    config = load_config()

    # API Keys (were missing from this handler)
    config["api_keys"]["openweather"] = request.form.get('openweather', '')
    config["api_keys"]["client_id"] = request.form.get('client_id', '')
    config["api_keys"]["client_secret"] = request.form.get('client_secret', '')
    config["api_keys"]["google_geo"] = request.form.get('google_geo', '')

    try:
        config["display"]["type"] = request.form.get('display_type', 'framebuffer')
        config["display"]["framebuffer"] = request.form.get('framebuffer_device', '/dev/fb1')
        config["display"]["rotation"] = int(request.form.get('rotation', 0))
        if "st7789" not in config["display"]:
            config["display"]["st7789"] = {}
        config["display"]["st7789"]["spi_port"] = int(request.form.get('spi_port', 0))
        config["display"]["st7789"]["spi_cs"] = int(request.form.get('spi_cs', 1))
        config["display"]["st7789"]["dc_pin"] = int(request.form.get('dc_pin', 9))
        config["display"]["st7789"]["backlight_pin"] = int(request.form.get('backlight_pin', 13))
        config["display"]["st7789"]["spi_speed"] = int(request.form.get('spi_speed', 60000000))
        config["fonts"]["large_font_path"] = request.form.get('large_font_path', '')
        config["fonts"]["large_font_size"] = int(request.form.get('large_font_size', 36))
        config["fonts"]["medium_font_path"] = request.form.get('medium_font_path', '')
        config["fonts"]["medium_font_size"] = int(request.form.get('medium_font_size', 24))
        config["fonts"]["small_font_path"] = request.form.get('small_font_path', '')
        config["fonts"]["small_font_size"] = int(request.form.get('small_font_size', 16))
        config["fonts"]["spot_large_font_path"] = request.form.get('spot_large_font_path', '')
        config["fonts"]["spot_large_font_size"] = int(request.form.get('spot_large_font_size', 26))
        config["fonts"]["spot_medium_font_path"] = request.form.get('spot_medium_font_path', '')
        config["fonts"]["spot_medium_font_size"] = int(request.form.get('spot_medium_font_size', 18))
        config["fonts"]["spot_small_font_path"] = request.form.get('spot_small_font_path', '')
        config["fonts"]["spot_small_font_size"] = int(request.form.get('spot_small_font_size', 12))
        if "buttons" not in config:
            config["buttons"] = {}
        config["buttons"]["button_a"] = int(request.form.get('button_a', 5))
        config["buttons"]["button_b"] = int(request.form.get('button_b', 6))
        config["buttons"]["button_x"] = int(request.form.get('button_x', 16))
        config["buttons"]["button_y"] = int(request.form.get('button_y', 24))
        config["wifi"]["ap_ssid"] = request.form.get('ap_ssid', 'Neonwifi-Manager')
        config["wifi"]["ap_ip"] = request.form.get('ap_ip', '192.168.42.1')
        config["settings"]["progressbar_display"] = 'progressbar_display' in request.form
        config["settings"]["time_display"] = 'time_display' in request.form
        config["settings"]["start_screen"] = request.form.get('start_screen', 'weather')
        config["settings"]["use_gpsd"] = 'use_gpsd' in request.form
        config["settings"]["use_google_geo"] = 'use_google_geo' in request.form
        config["settings"]["enable_current_track_display"] = 'enable_current_track_display' in request.form        
        config["clock"]["background"] = request.form.get('clock_background', 'color')
        config["clock"]["color"] = request.form.get('clock_color', '#000000')
        config["clock"]["type"] = request.form.get('clock_type', 'digital')
        save_config(config)
        flash('success', 'Advanced configuration saved successfully!')
        if is_hud35_running():
            stop_hud35()
            start_hud35()
        if is_neonwifi_running():
            stop_neonwifi()
            start_neonwifi()
    except Exception as e:
        flash('error', f'Error saving configuration: {str(e)}')
    return redirect(url_for('advanced_config'))

@app.route('/reset_advanced_config', methods=['POST'])
def reset_advanced_config():
    config = load_config()
    config["display"] = DEFAULT_CONFIG["display"].copy()
    config["fonts"] = DEFAULT_CONFIG["fonts"].copy()
    config["buttons"] = DEFAULT_CONFIG["buttons"].copy()
    preserved_api_keys = config["api_keys"].copy()
    preserved_settings = config["settings"].copy()
    preserved_auto_start = config.get("auto_start", {}).copy()
    preserved_ui = config.get("ui", {}).copy()
    config["api_keys"] = preserved_api_keys
    config["settings"].update({
        "start_screen": "weather",
        "progressbar_display": True,
        "time_display": True,
        "use_gpsd": True,
        "use_google_geo": True
    })
    config["auto_start"] = preserved_auto_start
    config["settings"] = preserved_settings
    config["ui"] = preserved_ui
    save_config(config)
    flash('success', 'Advanced configuration reset to defaults!')
    return redirect(url_for('advanced_config'))

def get_last_logged_song():
    if not os.path.exists('songs.toml'):
        return None
    try:
        with open('songs.toml', 'r') as f:
            content = f.read()
        data = toml.loads(content)
        plays = data.get('play', [])
        if not plays:
            return None
        last_play = plays[-1]
        return last_play.get('full_track')
    except Exception as e:
        logger = logging.getLogger('Launcher')
        logger.error(f"Error reading last logged song: {e}")
        return None

def log_current_track_state():
    global last_logged_song
    try:
        if not os.path.exists('.current_track_state.toml'):
            return
        state_data = toml.load('.current_track_state.toml')
        track_data = state_data.get('current_track', {})
        if not track_data.get('title') or track_data.get('title') in ['No track playing', 'Unknown Track']:
            return
        current_position = track_data.get('current_position', 0)
        duration = track_data.get('duration', 1)
        if duration > 0 and (current_position / duration) < 0.1:
            return        
        artists_data = track_data.get('artists', '')
        artists_list = []
        if isinstance(artists_data, list):
            artists_list = [str(artist).strip() for artist in artists_data if artist and str(artist).strip()]
        elif isinstance(artists_data, str) and artists_data.strip():
            artists_list = [artist.strip() for artist in artists_data.split(',') if artist.strip()]
        else:
            artists_list = ['Unknown Artist']
        if not artists_list:
            artists_list = ['Unknown Artist']
        artist_str = ', '.join(artists_list)
        current_song = f"{artist_str} -- {track_data.get('title', '')}".strip()
        if last_logged_song and current_song == last_logged_song:
            return
        song_info = {
            'song': track_data.get('title', ''),
            'artists': artists_list,
            'full_track': current_song
        }
        update_song_count(song_info)
    except Exception as e:
        logger = logging.getLogger('Launcher')
        logger.error(f"Error logging from current track state: {e}")

def update_song_count(song_info):
    global last_logged_song
    logger = logging.getLogger('Launcher')
    current_song = song_info.get('full_track', '').strip()
    if last_logged_song and current_song == last_logged_song:
        return
    try:
        song_counts = load_song_counts()
        if current_song in song_counts:
            song_counts[current_song] += 1
        else:
            song_counts[current_song] = 1
        save_song_counts(song_counts)
        logger.info(f"🎵 Updated count: {song_info.get('song', 'Unknown Track')} - Total plays: {song_counts[current_song]}")
        last_logged_song = current_song
    except Exception as e:
        logger.error(f"Error updating song count: {e}")

def get_current_track():
    try:
        state_file = '.current_track_state.toml'
        if os.path.exists(state_file):
            state_data = toml.load(state_file)
            track_data = state_data.get('current_track', {})
            timestamp = track_data.get('timestamp', 0)
            if time.time() - timestamp < 60:
                progress_sec = track_data.get('current_position', 0)
                duration_sec = track_data.get('duration', 0)
                progress_min = progress_sec // 60
                progress_sec = progress_sec % 60
                duration_min = duration_sec // 60
                duration_sec = duration_sec % 60
                artists = track_data.get('artists', 'Unknown Artist')
                if isinstance(artists, list):
                    artists_str = ', '.join(artists)
                else:
                    artists_str = artists
                return {
                    'song': track_data.get('title', 'Unknown Track'),
                    'artist': artists_str,
                    'album': track_data.get('album', 'Unknown Album'),
                    'progress': f"{progress_min}:{progress_sec:02d}",
                    'duration': f"{duration_min}:{duration_sec:02d}",
                    'is_playing': track_data.get('is_playing', False),
                    'has_track': track_data.get('title') != 'No track playing'
                }
        return {
            'song': 'No track playing',
            'artist': '',
            'album': '',
            'progress': '0:00',
            'duration': '0:00',
            'is_playing': False,
            'has_track': False
        }
    except Exception as e:
        logger = logging.getLogger('Launcher')
        logger.error(f"Error getting current track: {e}")
        return {
            'song': 'Error loading track',
            'artist': '',
            'album': '',
            'progress': '0:00',
            'duration': '0:00',
            'is_playing': False,
            'has_track': False
        }

def load_song_counts():
    if not os.path.exists('song_counts.toml'):
        return {}
    try:
        with open('song_counts.toml', 'r') as f:
            data = toml.load(f)
        return data.get('song_counts', {})
    except Exception as e:
        logger = logging.getLogger('Launcher')
        logger.error(f"Error loading song counts: {e}")
        return {}

def save_song_counts(song_counts):
    try:
        data = {'song_counts': song_counts}
        with open('song_counts.toml', 'w') as f:
            toml.dump(data, f)
    except Exception as e:
        logger = logging.getLogger('Launcher')
        logger.error(f"Error saving song counts: {e}")

def generate_music_stats(song_counts, max_items=1000):
    song_counter = Counter(song_counts)
    artist_counter = Counter()
    for song_key, count in song_counts.items():
        if ' -- ' in song_key:
            try:
                artist_part, song_part = song_key.split(' -- ', 1)
                artists = [a.strip() for a in artist_part.split(',')]
                for artist in artists:
                    if artist and artist != 'Unknown Artist':
                        artist_counter[artist] += count
            except:
                artist_counter['Unknown Artist'] += count
        else:
            artist_counter['Unknown Artist'] += count
    top_songs = dict(song_counter.most_common(max_items))
    top_artists = dict(artist_counter.most_common(max_items))
    return top_songs, top_artists

def generate_chart_data(stats, label_type):
    if not stats:
        return {'labels': [], 'data': [], 'colors': []}
    labels = list(stats.keys())
    data = list(stats.values())
    colors = []
    for i in range(len(labels)):
        hue = (i * 137.5) % 360
        colors.append(f'hsl({hue}, 70%, 60%)')
    return {
        'labels': labels,
        'data': data,
        'colors': colors,
        'label_type': label_type
    }

def cleanup():
    logger = logging.getLogger('Launcher')
    global hud35_process, neonwifi_process
    logger.info("🧹 Performing cleanup...")
    if hud35_process and hud35_process.poll() is None:
        logger.info("Stopping HUD35 process...")
        hud35_process.terminate()
        try:
            hud35_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("HUD35 didn't terminate gracefully, killing...")
            hud35_process.kill()
            hud35_process.wait()
        hud35_process = None
    if neonwifi_process and neonwifi_process.poll() is None:
        logger.info("Stopping neonwifi process...")
        neonwifi_process.terminate()
        try:
            neonwifi_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("neonwifi didn't terminate gracefully, killing...")
            neonwifi_process.kill()
            neonwifi_process.wait()
        neonwifi_process = None
    subprocess.run(['pkill', '-f', 'hud35.py'], check=False, timeout=5)
    subprocess.run(['pkill', '-f', 'neonwifi.py'], check=False, timeout=5)
    logger.info("Cleanup completed")

def signal_handler(sig, frame):
    logger = logging.getLogger('Launcher')
    logger.info("")
    logger.info("Shutting down launcher...")
    cleanup()
    os._exit(0)

def main():
    load_config()
    logger = setup_logging()
    logger.info("🚀 Starting HUD35 Launcher")
    
    def get_lan_ips():
        ips = []
        try:
            hostname = socket.gethostname()
            all_ips = socket.getaddrinfo(hostname, None)
            for addr_info in all_ips:
                ip = addr_info[4][0]
                if '.' in ip and not ip.startswith('127.'):
                    ips.append(ip)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
                    if local_ip not in ips and not local_ip.startswith('127.'):
                        ips.append(local_ip)
            except:
                pass
        except Exception as e:
            logger.warning(f"Could not determine LAN IP: {e}")
        return list(set(ips))
    
    lan_ips = get_lan_ips()
    auto_launch_applications()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    import logging as pylogging
    log = pylogging.getLogger('werkzeug')
    log.setLevel(pylogging.WARNING)
    port = 5000
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', port))
        s.close()
        if lan_ips:
            for ip in lan_ips:
                logger.info(f"📍 Web UI available at: http://{ip}:{port}")
        else:
            logger.info(f"📍 Web UI available at: http://127.0.0.1:{port}")
        logger.info("⏹️  Press Ctrl+C to stop the launcher")
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except OSError as e:
        if "Address already in use" in str(e):
            logger.error(f"❌ Port {port} is already in use. Please stop the other application using it.")
        else:
            logger.error(f"❌ Failed to start web server: {e}")
        cleanup()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    finally:
        cleanup()