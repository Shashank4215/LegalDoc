# Single Port Setup Guide

This guide explains how to run both frontend and backend on a single port (8000).

## Overview

The FastAPI backend now serves:
- **API endpoints** at `/api/*` (e.g., `/api/chat`, `/api/sessions`)
- **Frontend static files** at `/` (root and all other routes)
- **Static assets** (JS/CSS) at `/assets/*`

## Quick Start

1. **Ensure frontend is built:**
   ```bash
   cd chat-companion-hub
   npm run build
   ```

2. **Start the FastAPI server:**
   ```bash
   uvicorn chat_api:app --reload --port 8000
   ```

3. **Access the application:**
   - Frontend: http://localhost:8000
   - API Health: http://localhost:8000/api/health
   - API Docs: http://localhost:8000/docs

## How It Works

### Static File Serving

The backend serves static files from `chat-companion-hub/dist/`:
- `/assets/*` → Serves JS/CSS files from `dist/assets/`
- `/favicon.ico`, `/robots.txt`, etc. → Serves files from `dist/` root
- All other routes → Serves `index.html` (for SPA routing)

### API Routes

All API routes are prefixed with `/api/`:
- `GET /api/health` - Health check
- `GET /api/sessions` - List chat sessions
- `POST /api/sessions` - Create new session
- `GET /api/sessions/{id}` - Get session with messages
- `DELETE /api/sessions/{id}` - Delete session
- `POST /api/chat` - Send chat message

### SPA Routing

For Single Page Application (SPA) routing, all non-API routes return `index.html`, allowing React Router (or similar) to handle client-side routing.

## Development vs Production

### Development Mode

If you want to use Vite dev server for hot reload:
```bash
# Terminal 1: Backend
uvicorn chat_api:app --reload --port 8000

# Terminal 2: Frontend (Vite dev server)
cd chat-companion-hub
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

Then access frontend at http://localhost:5173 (Vite default port).

### Production Mode

For production, use the single port setup:
```bash
# Build frontend first
cd chat-companion-hub
npm run build

# Start backend (serves frontend automatically)
cd ..
uvicorn chat_api:app --host 0.0.0.0 --port 8000
```

## Configuration

### Frontend API Base URL

The frontend uses `VITE_API_BASE_URL` environment variable. When served from the same port:
- **Built with default**: Uses `http://localhost:8000` (works fine)
- **Built with empty**: Uses relative URLs `/api/*` (also works)

To rebuild with relative URLs:
```bash
cd chat-companion-hub
VITE_API_BASE_URL= npm run build
```

### CORS

CORS is configured but less critical when serving from the same origin. It's still enabled for:
- Development (Vite dev server on different port)
- External API access if needed

## Troubleshooting

### Frontend not loading

1. Check that `dist` folder exists: `ls chat-companion-hub/dist/`
2. Verify `index.html` exists: `ls chat-companion-hub/dist/index.html`
3. Check FastAPI logs for errors

### API calls failing

1. Check browser console for CORS errors
2. Verify API routes are accessible: `curl http://localhost:8000/api/health`
3. Check that `API_BASE_URL` matches server URL

### Static assets not loading

1. Verify assets folder exists: `ls chat-companion-hub/dist/assets/`
2. Check browser Network tab for 404 errors
3. Ensure FastAPI can access the dist folder

### SPA routing not working

1. Verify the catch-all route is after API routes in `chat_api.py`
2. Check that `index.html` is being served for non-API routes
3. Verify React Router (or your routing library) is configured correctly

## File Structure

```
QPPChatbot/
├── chat_api.py              # FastAPI app (serves API + frontend)
├── chat-companion-hub/
│   ├── dist/                # Built frontend files
│   │   ├── index.html       # Main HTML file
│   │   ├── assets/          # JS/CSS files
│   │   ├── favicon.ico
│   │   └── robots.txt
│   └── src/                 # Frontend source (for development)
└── ...
```

## Production Deployment

For production deployment:

1. **Build frontend:**
   ```bash
   cd chat-companion-hub
   npm run build
   ```

2. **Run with production server:**
   ```bash
   # Using uvicorn
   uvicorn chat_api:app --host 0.0.0.0 --port 8000 --workers 4
   
   # Or using gunicorn
   gunicorn chat_api:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
   ```

3. **Use reverse proxy (nginx) for SSL:**
   ```nginx
   server {
       listen 443 ssl;
       server_name your-domain.com;
       
       location / {
           proxy_pass http://localhost:8000;
       }
   }
   ```

## Benefits of Single Port Setup

✅ **Simpler deployment** - One service to manage  
✅ **No CORS issues** - Same origin for frontend and API  
✅ **Easier SSL** - One certificate for everything  
✅ **Better performance** - No cross-origin requests  
✅ **Production ready** - Standard pattern for web apps  

Enjoy your unified deployment! 🚀

