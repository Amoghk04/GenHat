#!/bin/bash

# GenHat Run Script
# Quick start script for backend and frontend

set -e

MODE=${1:-both}

case "$MODE" in
    backend)
        echo "🚀 Starting Backend Server..."
        cd Backend
        source .venv/bin/activate
        python app.py
        ;;
    
    frontend)
        echo "🚀 Starting Frontend Application..."
        cd Frontend
        npm start
        ;;
    
    both)
        if ! command -v tmux >/dev/null 2>&1; then
            echo "❌ tmux is not installed. Please install tmux or run backend and frontend separately."
            echo ""
            echo "Terminal 1: ./run.sh backend"
            echo "Terminal 2: ./run.sh frontend"
            exit 1
        fi
        
        echo "🚀 Starting Backend and Frontend in tmux..."
        
        # Create new tmux session
        tmux new-session -d -s genhat
        
        # Split window horizontally
        tmux split-window -h
        
        # Run backend in left pane
        tmux select-pane -t 0
        tmux send-keys "cd Backend && source .venv/bin/activate && python app.py" C-m
        
        # Run frontend in right pane
        tmux select-pane -t 1
        tmux send-keys "cd Frontend && npm start" C-m
        
        # Attach to session
        echo "✅ Started in tmux session 'genhat'"
        echo "   Use 'tmux attach -t genhat' to view"
        echo "   Press Ctrl+B then D to detach"
        echo "   Use 'tmux kill-session -t genhat' to stop"
        echo ""
        
        tmux attach -t genhat
        ;;
    
    *)
        echo "Usage: ./run.sh [backend|frontend|both]"
        echo ""
        echo "Options:"
        echo "  backend   - Start only the backend server"
        echo "  frontend  - Start only the frontend application"
        echo "  both      - Start both in tmux (default)"
        exit 1
        ;;
esac
