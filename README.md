# FluxFlow Backend

Code execution API for FluxFlow app. Deployed on Render.com free tier.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API info |
| `/health` | GET | Health check |
| `/languages` | GET | List supported languages |
| `/run` | POST | Execute code |

## Run Code API

```bash
POST /run
Content-Type: application/json

{
    "code": "print('Hello World')",
    "language": "python",
    "input": ""
}
```

**Response:**
```json
{
    "success": true,
    "output": "Hello World\n",
    "error": "",
    "exit_code": 0,
    "language": "python"
}
```

## Supported Languages

- **python** - Python 3.11
- **c** - C (GCC)
- **cpp** - C++ (G++ with C++17)

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py

# Or with gunicorn
gunicorn --bind 0.0.0.0:10000 main:app
```

## Docker

```bash
# Build
docker build -t fluxflow-backend .

# Run
docker run -p 10000:10000 fluxflow-backend
```

## Deploy to Render

1. Push to GitHub
2. Go to render.com → New Web Service
3. Connect your repo
4. Set Environment: Docker
5. Instance Type: Free
6. Health Check Path: /health
7. Deploy!

## Limits

- Execution timeout: 5 seconds
- Code size: 10,000 characters max
- Output size: 50,000 characters max
