"""
FluxFlow Backend - Code Execution API
Deployed on Render.com Free Tier
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import tempfile
import os
import sys
import time
import json

# Firebase Admin SDK for FCM Push Notifications
import firebase_admin
from firebase_admin import credentials, messaging

app = Flask(__name__)
CORS(app, origins=["*"])  # Allow all origins for mobile app

# Configuration
MAX_EXECUTION_TIME = 5  # seconds
MAX_OUTPUT_SIZE = 50000  # characters

# ============== FIREBASE INITIALIZATION ==============
# Load Firebase credentials from environment variable
firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")
if firebase_creds_json:
    try:
        cred = credentials.Certificate(json.loads(firebase_creds_json))
        firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin SDK initialized")
    except Exception as e:
        print(f"⚠️ Firebase init failed: {e}")
else:
    print("⚠️ FIREBASE_CREDENTIALS not set - FCM disabled")


def set_limits():
    """Set resource limits for subprocess"""
    # Limit memory to 50MB
    resource.setrlimit(resource.RLIMIT_AS, (50 * 1024 * 1024, 50 * 1024 * 1024))
    # Limit CPU time
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))


# ============== ROUTES ==============

@app.route('/', methods=['GET'])
def home():
    """Root endpoint"""
    return jsonify({
        "name": "FluxFlow Backend API",
        "version": "1.0.0",
        "endpoints": {
            "/health": "Health check",
            "/run": "Execute code (POST)",
            "/languages": "Supported languages (GET)"
        }
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint - Render pings this"""
    from datetime import datetime
    return jsonify({
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": time.time(),
        "datetime": datetime.now().isoformat()
    })


# ============== SUPABASE CONNECTION ==============
from supabase import create_client, Client

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

def get_supabase() -> Client:
    """Get Supabase client"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise Exception("Supabase credentials not configured")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


@app.route('/trigger-weekly-winner', methods=['GET'])
def announce_weekly_winner():
    """
    Jealousy Engine - Auto-announce weekly champion
    
    1. Find top scorer by weekly_points
    2. Create news post with winner's name
    3. Reset all weekly_points to 0 for next week
    
    Triggered by cron-job.org every Sunday at 23:55
    """
    try:
        supabase = get_supabase()
        
        # 1. Find the Top Scorer
        response = supabase.table('students') \
            .select('id, name, regd_no, weekly_points, subscription_tier') \
            .order('weekly_points', desc=True) \
            .limit(1) \
            .execute()
            
        if not response.data or len(response.data) == 0:
            return jsonify({
                "status": "no_data",
                "message": "No students found"
            })
            
        winner = response.data[0]
        winner_name = winner['name']
        score = winner['weekly_points']
        tier = winner.get('subscription_tier', 'free').upper()
        
        # 2. Create the "Jealousy" News Post
        news_title = f"🏆 Week's Champion: {winner_name}!"
        news_body = f"{winner_name} ({tier}) topped the coding leaderboard with {score} points! Can you beat them next week? Start solving challenges now!"
        
        supabase.table('news').insert({
            "title": news_title,
            "description": news_body,
            "image_url": "https://img.icons8.com/fluency/240/trophy.png"
        }).execute()
        
        # 3. RESET everyone's weekly points for the new week
        supabase.table('students').update({"weekly_points": 0}).neq("id", "00000000-0000-0000-0000-000000000000").execute()
        
        return jsonify({
            "status": "success",
            "winner": winner_name,
            "points": score,
            "news_created": True,
            "points_reset": True
        })
        
    except Exception as e:
        print(f"❌ Weekly winner error: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/languages', methods=['GET'])
def languages():
    """List supported programming languages"""
    return jsonify({
        "languages": [
            {"id": "python", "name": "Python 3.11", "extension": ".py"},
            {"id": "c", "name": "C (GCC)", "extension": ".c"},
            {"id": "cpp", "name": "C++ (G++)", "extension": ".cpp"},
            {"id": "java", "name": "Java", "extension": ".java"},
        ]
    })


# ============== FCM PUSH NOTIFICATION WEBHOOK ==============

@app.route('/webhook-news-notification', methods=['POST'])
def send_news_notification():
    """
    Supabase Database Webhook - Called on news INSERT
    Sends FCM push notification to all subscribed students
    """
    try:
        payload = request.json
        if not payload:
            return jsonify({"error": "No payload"}), 400
        
        # Supabase sends the new row in 'record'
        record = payload.get('record', {})
        
        title = record.get('title', 'New Update')
        body = record.get('description', 'Check the app for details!')
        
        # Check if Firebase is initialized
        if not firebase_admin._apps:
            return jsonify({"error": "Firebase not configured"}), 503
        
        # Create FCM message for topic
        message = messaging.Message(
            notification=messaging.Notification(
                title=f"📢 {title}",
                body=body,
            ),
            topic="all_students",  # All subscribed users receive this
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    icon="notification_icon",
                    color="#00FFFF",
                    sound="default",
                )
            ),
        )
        
        # Send the notification
        response = messaging.send(message)
        
        return jsonify({
            "success": True,
            "message_id": response,
            "topic": "all_students"
        })
        
    except Exception as e:
        print(f"FCM Error: {e}")
        return jsonify({"error": str(e)}), 500


# ============== HYBRID CODE EXECUTION (JDoodle + Piston) ==============

# Get JDoodle credentials from environment (optional, set in Render)
import os
JDOODLE_ID = os.environ.get('JDOODLE_CLIENT_ID', '')
JDOODLE_SECRET = os.environ.get('JDOODLE_CLIENT_SECRET', '')

@app.route('/run-code', methods=['POST'])
def run_hybrid_code():
    """
    Hybrid Code Execution - JDoodle first, Piston fallback
    
    Supported languages: c, cpp, python, java, js, csharp, go, kotlin, swift, dart
    
    Request body:
    {
        "script": "print('Hello')",
        "language": "python",
        "stdin": ""
    }
    """
    import requests
    
    data = request.json
    if not data:
        return jsonify({"error": "No JSON body provided", "success": False}), 400
    
    script = data.get('script', '')
    language = data.get('language', 'python').lower()
    stdin = data.get('stdin', '')
    
    if not script:
        return jsonify({"error": "No script provided", "success": False}), 400
    
    # === ATTEMPT 1: JDOODLE (if configured) ===
    if JDOODLE_ID and JDOODLE_SECRET:
        try:
            jdoodle_map = {
                "c": "c",
                "cpp": "cpp17",
                "python": "python3",
                "java": "java",
                "js": "nodejs",
                "csharp": "csharp",
                "go": "go",
                "kotlin": "kotlin",
                "swift": "swift",
                "dart": "dart"
            }
            
            jdoodle_lang = jdoodle_map.get(language, "python3")
            
            jdoodle_payload = {
                "clientId": JDOODLE_ID,
                "clientSecret": JDOODLE_SECRET,
                "script": script,
                "language": jdoodle_lang,
                "versionIndex": "0",
                "stdin": stdin
            }
            
            response = requests.post(
                "https://api.jdoodle.com/v1/execute",
                json=jdoodle_payload,
                timeout=30
            )
            result = response.json()
            
            if response.status_code == 200 and "output" in result:
                output = result.get("output", "")
                # Check if rate limited
                if "Daily Limit Reached" not in output:
                    return jsonify({
                        "success": True,
                        "output": output if output else "(No output)",
                        "error": "",
                        "source": "JDoodle",
                        "language": language
                    })
                # Fall through to Piston if rate limited
                
        except Exception as e:
            print(f"JDoodle failed, trying Piston: {e}")
    
    # === ATTEMPT 2: PISTON (Free & Unlimited) ===
    try:
        piston_map = {
            "c": "c",
            "cpp": "c++",
            "python": "python",
            "java": "java",
            "js": "javascript",
            "csharp": "csharp",
            "go": "go",
            "kotlin": "kotlin",
            "swift": "swift",
            "dart": "dart"
        }
        
        piston_lang = piston_map.get(language, "python")
        
        piston_payload = {
            "language": piston_lang,
            "version": "*",
            "files": [{"content": script}],
            "stdin": stdin
        }
        
        response = requests.post(
            "https://emkc.org/api/v2/piston/execute",
            json=piston_payload,
            timeout=30
        )
        result = response.json()
        
        if "run" in result:
            output = result["run"]["stdout"] + result["run"]["stderr"]
            exit_code = result["run"].get("code", 0)
            return jsonify({
                "success": exit_code == 0,
                "output": output if output else "(No output)",
                "error": result["run"]["stderr"] if exit_code != 0 else "",
                "source": "Piston",
                "language": language
            })
        else:
            error_msg = result.get("message", "Unknown error from Piston")
            return jsonify({
                "success": False,
                "output": "",
                "error": f"Piston Error: {error_msg}",
                "source": "Piston",
                "language": language
            })
            
    except requests.Timeout:
        return jsonify({"error": "Execution timeout", "success": False}), 408
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}", "success": False}), 500


@app.route('/run', methods=['POST'])
def run_code():
    """
    Execute code and return output
    
    Request body:
    {
        "code": "print('Hello World')",
        "language": "python",
        "input": ""  # optional stdin input
    }
    """
    try:
        data = request.json
        
        if not data:
            return jsonify({"error": "No JSON body provided"}), 400
        
        code = data.get('code', '')
        language = data.get('language', 'python').lower()
        stdin_input = data.get('input', '')
        
        if not code:
            return jsonify({"error": "No code provided"}), 400
        
        if len(code) > 10000:
            return jsonify({"error": "Code too long (max 10000 chars)"}), 400
        
        # Execute based on language
        if language == 'python':
            return execute_python(code, stdin_input)
        elif language == 'c':
            return execute_c(code, stdin_input)
        elif language == 'cpp':
            return execute_cpp(code, stdin_input)
        else:
            return jsonify({"error": f"Unsupported language: {language}"}), 400
            
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500


# ============== EXECUTORS ==============

def execute_python(code: str, stdin_input: str = "") -> tuple:
    """Execute Python code safely with timeout"""
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, temp_file],
                input=stdin_input,
                capture_output=True,
                text=True,
                timeout=MAX_EXECUTION_TIME
            )
            
            output = result.stdout[:MAX_OUTPUT_SIZE]
            error = result.stderr[:MAX_OUTPUT_SIZE]
            
            return jsonify({
                "success": result.returncode == 0,
                "output": output,
                "error": error,
                "exit_code": result.returncode,
                "language": "python"
            })
            
        finally:
            os.unlink(temp_file)
        
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "output": "",
            "error": f"Execution timeout ({MAX_EXECUTION_TIME}s limit exceeded)",
            "exit_code": -1
        }), 408
    except Exception as e:
        return jsonify({
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1
        }), 500


def execute_c(code: str, stdin_input: str = "") -> tuple:
    """Compile and execute C code"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, 'program.c')
            binary = os.path.join(tmpdir, 'program')
            
            with open(source, 'w') as f:
                f.write(code)
            
            # Compile with GCC
            compile_result = subprocess.run(
                ['gcc', source, '-o', binary, '-lm'],  # -lm for math library
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if compile_result.returncode != 0:
                return jsonify({
                    "success": False,
                    "output": "",
                    "error": compile_result.stderr[:MAX_OUTPUT_SIZE],
                    "exit_code": compile_result.returncode,
                    "phase": "compilation",
                    "language": "c"
                })
            
            # Execute binary
            run_result = subprocess.run(
                [binary],
                input=stdin_input,
                capture_output=True,
                text=True,
                timeout=MAX_EXECUTION_TIME
            )
            
            return jsonify({
                "success": run_result.returncode == 0,
                "output": run_result.stdout[:MAX_OUTPUT_SIZE],
                "error": run_result.stderr[:MAX_OUTPUT_SIZE],
                "exit_code": run_result.returncode,
                "phase": "execution",
                "language": "c"
            })
            
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "output": "",
            "error": f"Execution timeout ({MAX_EXECUTION_TIME}s limit exceeded)",
            "exit_code": -1
        }), 408
    except Exception as e:
        return jsonify({
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1
        }), 500


def execute_cpp(code: str, stdin_input: str = "") -> tuple:
    """Compile and execute C++ code"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, 'program.cpp')
            binary = os.path.join(tmpdir, 'program')
            
            with open(source, 'w') as f:
                f.write(code)
            
            # Compile with G++
            compile_result = subprocess.run(
                ['g++', source, '-o', binary, '-std=c++17'],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if compile_result.returncode != 0:
                return jsonify({
                    "success": False,
                    "output": "",
                    "error": compile_result.stderr[:MAX_OUTPUT_SIZE],
                    "exit_code": compile_result.returncode,
                    "phase": "compilation", 
                    "language": "cpp"
                })
            
            # Execute binary
            run_result = subprocess.run(
                [binary],
                input=stdin_input,
                capture_output=True,
                text=True,
                timeout=MAX_EXECUTION_TIME
            )
            
            return jsonify({
                "success": run_result.returncode == 0,
                "output": run_result.stdout[:MAX_OUTPUT_SIZE],
                "error": run_result.stderr[:MAX_OUTPUT_SIZE],
                "exit_code": run_result.returncode,
                "phase": "execution",
                "language": "cpp"
            })
            
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "output": "",
            "error": f"Execution timeout ({MAX_EXECUTION_TIME}s limit exceeded)",
            "exit_code": -1
        }), 408
    except Exception as e:
        return jsonify({
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1
        }), 500


# ============== MAIN ==============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    print(f"🚀 FluxFlow Backend starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
