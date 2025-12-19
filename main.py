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
import resource
import signal

app = Flask(__name__)
CORS(app, origins=["*"])  # Allow all origins for mobile app

# Configuration
MAX_EXECUTION_TIME = 5  # seconds
MAX_OUTPUT_SIZE = 50000  # characters

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
    return jsonify({
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": time.time()
    })


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


# ============== PISTON API (FREE & UNLIMITED) ==============

# Language mapping: Flutter names -> Piston API names
LANGUAGE_MAP = {
    "c": "c",
    "cpp": "c++",       # Flutter sends 'cpp', Piston needs 'c++'
    "python": "python",
    "java": "java",
    "dart": "dart",
}

@app.route('/run-code', methods=['POST'])
@app.route('/run-piston', methods=['POST'])
def run_code_piston():
    """
    Piston API - Free & Unlimited code execution
    No API keys required!
    
    Request body:
    {
        "script": "print('Hello')",
        "language": "python",
        "stdin": ""
    }
    
    Supported languages: c, cpp, python, java, dart
    """
    try:
        import requests
        
        data = request.json
        if not data:
            return jsonify({"error": "No JSON body provided"}), 400
        
        script = data.get('script', '')
        language = data.get('language', 'python').lower()
        stdin = data.get('stdin', '')
        
        if not script:
            return jsonify({"error": "No script provided"}), 400
        
        # Map Flutter language names to Piston names
        target_lang = LANGUAGE_MAP.get(language, language)
        
        # Piston Public API (Free & Unlimited)
        piston_url = "https://emkc.org/api/v2/piston/execute"
        
        payload = {
            "language": target_lang,
            "version": "*",  # Use latest version
            "files": [{"content": script}],
            "stdin": stdin
        }
        
        response = requests.post(piston_url, json=payload, timeout=30)
        result = response.json()
        
        # Handle Piston response
        if "run" in result:
            output = result["run"]["stdout"] + result["run"]["stderr"]
            exit_code = result["run"].get("code", 0)
            return jsonify({
                "success": exit_code == 0,
                "output": output if output else "(No output)",
                "error": result["run"]["stderr"] if exit_code != 0 else "",
                "exit_code": exit_code,
                "language": language
            })
        else:
            error_msg = result.get("message", "Unknown error from Piston")
            return jsonify({
                "success": False,
                "output": "",
                "error": f"Piston Error: {error_msg}",
                "exit_code": -1,
                "language": language
            })
        
    except requests.Timeout:
        return jsonify({"error": "Piston API timeout"}), 408
    except Exception as e:
        return jsonify({"error": f"Piston error: {str(e)}"}), 500


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
