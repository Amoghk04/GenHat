#!/bin/bash

# GenHat Setup and Run Script
# This script helps set up and run both backend and frontend

set -e

echo "🎩 GenHat - Document Intelligence Platform Setup"
echo "================================================"
echo ""

# Check if we're in the right directory
if [ ! -f "Backend/app.py" ] || [ ! -f "Frontend/package.json" ]; then
    echo "❌ Error: Please run this script from the GenHat root directory"
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
echo "📋 Checking prerequisites..."

if ! command_exists python3; then
    echo "❌ Python 3 is not installed. Please install Python 3.10 or higher."
    exit 1
fi

if ! command_exists node; then
    echo "❌ Node.js is not installed. Please install Node.js 16 or higher."
    exit 1
fi

if ! command_exists npm; then
    echo "❌ npm is not installed. Please install npm."
    exit 1
fi

echo "✅ Prerequisites check passed"
echo ""

# Setup Backend
echo "🔧 Setting up Backend..."
cd Backend

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "✅ Backend setup complete"
echo ""

# Check for environment variables
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found in Backend/"
    echo "Creating template .env file..."
    cat > .env << EOF
# Backend Environment Variables
DOCUMINT_DATA_DIR=./data/projects
DOCUMINT_FRONTEND_DIST=../Frontend/dist

# Gemini API (required for AI analysis)
VITE_GEMINI_API_KEY=your_gemini_api_key_here

# Azure Speech (required for podcast generation)
SPEECH_API_KEY=your_azure_speech_key_here
SPEECH_REGION=your_azure_region_here
EOF
    echo "📝 Please edit Backend/.env and add your API keys"
    echo ""
fi

cd ..

# Setup Frontend
echo "🔧 Setting up Frontend..."
cd Frontend

if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies..."
    npm install
fi

echo "Building TypeScript..."
npm run build

echo "✅ Frontend setup complete"
echo ""

cd ..

echo "✨ Setup complete!"
echo ""
echo "📖 Next steps:"
echo "1. Edit Backend/.env and add your API keys (Gemini, Azure Speech)"
echo "2. Start the backend: cd Backend && source .venv/bin/activate && python app.py"
echo "3. In a new terminal, start the frontend: cd Frontend && npm start"
echo ""
echo "Or use the quick start script:"
echo "  ./run.sh backend   # Start backend server"
echo "  ./run.sh frontend  # Start frontend app"
echo "  ./run.sh both      # Start both (requires tmux)"
echo ""
