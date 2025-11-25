"""
Browser Output Server for OBS
Simple Flask server that serves subtitle display page
"""

from flask import Flask, render_template_string, jsonify, request
from flask_cors import CORS
import os
import json
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Path to subtitles file
SUBTITLES_FILE = Path(__file__).parent / "subtitles.txt"
CONFIG_FILE = Path(__file__).parent / "config.json"


def load_browser_config():
    """Load browser output configuration"""
    # Default config
    default_config = {
        'main': {
            'font': 'Arial',
            'font_size': 32,
            'color': '#FFFFFF',
            'shadow_color': '#000000',
            'bg_opacity': 0.7
        },
        'trans1': {
            'font': 'Arial',
            'font_size': 28,
            'color': '#FFFF00',
            'shadow_color': '#000000',
            'bg_opacity': 0.7
        },
        'trans2': {
            'font': 'Arial',
            'font_size': 28,
            'color': '#00FFFF',
            'shadow_color': '#000000',
            'bg_opacity': 0.7
        }
    }

    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                browser_config = config.get('browser_output', {})

                # Merge with defaults to ensure all keys exist
                for key in ['main', 'trans1', 'trans2']:
                    if key not in browser_config:
                        browser_config[key] = default_config[key]
                    else:
                        # Ensure all sub-keys exist
                        for subkey in ['font', 'font_size', 'color', 'shadow_color', 'bg_opacity']:
                            if subkey not in browser_config[key]:
                                browser_config[key][subkey] = default_config[key][subkey]

                return browser_config
    except Exception as e:
        print(f"Error loading browser config: {e}")

    return default_config


@app.route('/')
def index():
    """Serve subtitle display page"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>jimakuChan Subtitles</title>
    <style>
        body {
            margin: 0;
            padding: 20px;
            background: transparent;
            font-family: Arial, sans-serif;
            overflow: hidden;
        }

        .subtitle-container {
            display: flex;
            flex-direction: column;
            gap: 10px;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }

        .subtitle-line {
            font-weight: bold;
            text-align: center;
            padding: 10px 20px;
            text-shadow:
                2px 2px 4px var(--shadow-color),
                -2px -2px 4px var(--shadow-color),
                2px -2px 4px var(--shadow-color),
                -2px 2px 4px var(--shadow-color);
        }

        .main-line {
            /* Styles applied dynamically via JavaScript */
        }

        .trans1-line {
            /* Styles applied dynamically via JavaScript */
        }

        .trans2-line {
            /* Styles applied dynamically via JavaScript */
        }

        .hidden {
            display: none;
        }
    </style>
</head>
<body>
    <div class="subtitle-container">
        <div id="main" class="subtitle-line main-line hidden"></div>
        <div id="trans1" class="subtitle-line trans1-line hidden"></div>
        <div id="trans2" class="subtitle-line trans2-line hidden"></div>
    </div>

    <script>
        let lastContent = '';
        let currentConfig = null;

        async function updateConfig() {
            try {
                const response = await fetch('/api/config');
                const config = await response.json();

                // Only update if config changed
                if (JSON.stringify(config) !== JSON.stringify(currentConfig)) {
                    currentConfig = config;
                    applyStyles(config);
                }
            } catch (error) {
                console.error('Error fetching config:', error);
            }
        }

        function applyStyles(config) {
            const mainEl = document.getElementById('main');
            const trans1El = document.getElementById('trans1');
            const trans2El = document.getElementById('trans2');

            // Apply main styles
            mainEl.style.fontFamily = config.main.font + ', sans-serif';
            mainEl.style.color = config.main.color;
            mainEl.style.setProperty('--shadow-color', config.main.shadow_color);
            mainEl.style.fontSize = (config.main.font_size || 32) + 'px';
            mainEl.style.backgroundColor = 'rgba(0, 0, 0, ' + (config.main.bg_opacity || 0.7) + ')';
            mainEl.style.borderRadius = '8px';

            // Apply trans1 styles
            trans1El.style.fontFamily = config.trans1.font + ', sans-serif';
            trans1El.style.color = config.trans1.color;
            trans1El.style.setProperty('--shadow-color', config.trans1.shadow_color);
            trans1El.style.fontSize = (config.trans1.font_size || 28) + 'px';
            trans1El.style.backgroundColor = 'rgba(0, 0, 0, ' + (config.trans1.bg_opacity || 0.7) + ')';
            trans1El.style.borderRadius = '8px';

            // Apply trans2 styles
            trans2El.style.fontFamily = config.trans2.font + ', sans-serif';
            trans2El.style.color = config.trans2.color;
            trans2El.style.setProperty('--shadow-color', config.trans2.shadow_color);
            trans2El.style.fontSize = (config.trans2.font_size || 28) + 'px';
            trans2El.style.backgroundColor = 'rgba(0, 0, 0, ' + (config.trans2.bg_opacity || 0.7) + ')';
            trans2El.style.borderRadius = '8px';
        }

        async function updateSubtitles() {
            try {
                const response = await fetch('/api/subtitles');
                const data = await response.json();

                if (data.content !== lastContent) {
                    lastContent = data.content;

                    // Parse subtitle lines
                    const lines = data.content.split('\\n').filter(l => l.trim());

                    // Clear all
                    document.getElementById('main').classList.add('hidden');
                    document.getElementById('trans1').classList.add('hidden');
                    document.getElementById('trans2').classList.add('hidden');

                    // Update each line
                    lines.forEach(line => {
                        if (line.startsWith('[Main]')) {
                            const text = line.replace('[Main]', '').trim();
                            const el = document.getElementById('main');
                            el.textContent = text;
                            el.classList.remove('hidden');
                        } else if (line.startsWith('[Trans1]')) {
                            const text = line.replace('[Trans1]', '').trim();
                            const el = document.getElementById('trans1');
                            el.textContent = text;
                            el.classList.remove('hidden');
                        } else if (line.startsWith('[Trans2]')) {
                            const text = line.replace('[Trans2]', '').trim();
                            const el = document.getElementById('trans2');
                            el.textContent = text;
                            el.classList.remove('hidden');
                        } else {
                            // No prefix - treat as main
                            const el = document.getElementById('main');
                            el.textContent = line;
                            el.classList.remove('hidden');
                        }
                    });
                }
            } catch (error) {
                console.error('Error fetching subtitles:', error);
            }
        }

        // Poll config every 2 seconds
        setInterval(updateConfig, 2000);
        updateConfig();

        // Poll subtitles every 100ms for smooth updates
        setInterval(updateSubtitles, 100);
        updateSubtitles();
    </script>
</body>
</html>
    """

    return html


@app.route('/api/subtitles')
def get_subtitles():
    """API endpoint to get current subtitles"""
    try:
        if SUBTITLES_FILE.exists():
            with open(SUBTITLES_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                return jsonify({'content': content})
    except Exception as e:
        print(f"Error reading subtitles: {e}")

    return jsonify({'content': ''})


@app.route('/api/config')
def get_config():
    """API endpoint to get current browser config (for live updates)"""
    config = load_browser_config()
    return jsonify(config)


def run_server(port=8765):
    """Run the browser output server"""
    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)


if __name__ == '__main__':
    run_server()
