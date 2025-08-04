#!/bin/bash

# Setup script for Speech Assistant

echo "Setting up Speech Assistant..."

# Check if Python 3.9+ is installed
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.9"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" = "$required_version" ]; then
    echo "✓ Python $python_version is installed"
else
    echo "✗ Python 3.9+ is required. Current version: $python_version"
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv .venv

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -e .

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << EOF
# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Server Configuration
PORT=5050
HOST=0.0.0.0
EOF
    echo "⚠️  Please update the .env file with your OpenAI API key"
else
    echo "✓ .env file already exists"
fi

# Create necessary directories
echo "Creating directories..."
mkdir -p static templates moving_requests

echo "✓ Setup complete!"
echo ""
echo "To run the application:"
echo "  source .venv/bin/activate"
echo "  python main.py"
echo ""
echo "Or with Docker:"
echo "  docker-compose -f docker/docker-compose.yml up --build" 