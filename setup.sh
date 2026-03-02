#!/bin/bash
set -e  # Exit on error

echo "============================================"
echo "KnockOff Video Generator - Setup Script"
echo "============================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Installation directory (defaults to ~/KnockOff)
INSTALL_DIR="${1:-$HOME/KnockOff}"
EASY_WAV2LIP_DIR="$HOME/Easy-Wav2Lip"

echo "📍 Installation directory: $INSTALL_DIR"
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to print status
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Checking System Requirements"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check for Python 3.12
if command_exists python3.12; then
    PYTHON_VERSION=$(python3.12 --version)
    print_status "Python 3.12 found: $PYTHON_VERSION"
else
    print_error "Python 3.12 not found"
    echo "Please install Python 3.12:"
    echo "  brew install python@3.12"
    exit 1
fi

# Check for ffmpeg
if command_exists ffmpeg; then
    FFMPEG_VERSION=$(ffmpeg -version | head -n 1)
    print_status "ffmpeg found: $FFMPEG_VERSION"
else
    print_error "ffmpeg not found"
    echo "Please install ffmpeg:"
    echo "  brew install ffmpeg"
    exit 1
fi

# Check for git
if command_exists git; then
    GIT_VERSION=$(git --version)
    print_status "git found: $GIT_VERSION"
else
    print_error "git not found"
    echo "Please install git:"
    echo "  brew install git"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Creating Directory Structure"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create main installation directory if it doesn't exist
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Create required subdirectories
directories=(
    "avatars"
    "broll"
    "overlays"
    "music"
    "scripts"
    "templates"
    "tools"
    "logs"
    "comparisons"
    ".tmp/avatar/input"
    ".tmp/avatar/output"
    ".tmp/avatar/audio"
    "models/piper"
)

for dir in "${directories[@]}"; do
    mkdir -p "$dir"
    print_status "Created directory: $dir"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Setting Up Python Virtual Environment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -d ".venv" ]; then
    print_warning "Virtual environment already exists, skipping creation"
else
    python3.12 -m venv .venv
    print_status "Created Python virtual environment"
fi

# Activate virtual environment
source .venv/bin/activate
print_status "Activated virtual environment"

# Upgrade pip
pip install --upgrade pip > /dev/null 2>&1
print_status "Upgraded pip to latest version"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Installing Python Dependencies"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "Installing from requirements.txt (this may take several minutes)..."
    pip install -r requirements.txt
    print_status "Installed all Python dependencies"
else
    print_error "requirements.txt not found in $INSTALL_DIR"
    echo "Please ensure requirements.txt is present"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5: Installing Easy-Wav2Lip"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -d "$EASY_WAV2LIP_DIR" ]; then
    print_warning "Easy-Wav2Lip already exists at $EASY_WAV2LIP_DIR"
    read -p "Do you want to reinstall? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$EASY_WAV2LIP_DIR"
        print_status "Removed existing Easy-Wav2Lip installation"
    else
        print_status "Keeping existing Easy-Wav2Lip installation"
    fi
fi

if [ ! -d "$EASY_WAV2LIP_DIR" ]; then
    echo "Cloning Easy-Wav2Lip repository..."
    cd ~
    git clone https://github.com/anothermartz/Easy-Wav2Lip.git
    cd "$EASY_WAV2LIP_DIR"

    print_status "Cloned Easy-Wav2Lip to $EASY_WAV2LIP_DIR"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "IMPORTANT: Easy-Wav2Lip Setup Instructions"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Please complete the Easy-Wav2Lip setup manually:"
    echo ""
    echo "1. Navigate to: $EASY_WAV2LIP_DIR"
    echo "2. Follow the installation instructions in their README.md"
    echo "3. Download required models (wav2lip.pth, wav2lip_gan.pth)"
    echo "4. Verify installation by running a test"
    echo ""
    print_warning "Automated Easy-Wav2Lip setup not yet implemented"
    echo ""
fi

cd "$INSTALL_DIR"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 6: Downloading Piper TTS Models"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Piper model URLs (from rhasspy/piper releases)
PIPER_MODELS_URL="https://github.com/rhasspy/piper/releases/latest/download"

# Download Joe (male voice)
if [ ! -f "models/piper/en_US-joe-medium.onnx" ]; then
    echo "Downloading Joe voice model..."
    curl -L "${PIPER_MODELS_URL}/voice-en-us-joe-medium.tar.gz" -o models/piper/joe.tar.gz
    cd models/piper
    tar -xzf joe.tar.gz
    rm joe.tar.gz
    cd "$INSTALL_DIR"
    print_status "Downloaded Joe (male) voice model"
else
    print_status "Joe voice model already exists"
fi

# Download Lessac (female voice)
if [ ! -f "models/piper/en_US-lessac-medium.onnx" ]; then
    echo "Downloading Lessac voice model..."
    curl -L "${PIPER_MODELS_URL}/voice-en-us-lessac-medium.tar.gz" -o models/piper/lessac.tar.gz
    cd models/piper
    tar -xzf lessac.tar.gz
    rm lessac.tar.gz
    cd "$INSTALL_DIR"
    print_status "Downloaded Lessac (female) voice model"
else
    print_status "Lessac voice model already exists"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 7: Creating Sample Template"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create sample script template if it doesn't exist
if [ ! -f "templates/video-script-template.md" ]; then
    cat > templates/video-script-template.md << 'EOF'
---
Title: Your Video Title
Duration: 90s
Format: portrait
Avatar: your-avatar-name
Voice: joe
---

# Your Video Title

This is the opening line. Write naturally, as you would speak.

[OVERLAY: product-demo.png | 5s]

Continue your script here. The overlay will appear during this section.

More content that gets converted to speech.

[BROLL: demo-footage.mp4 | 8s]

This section plays over the B-roll footage.

Final thoughts and call to action.

[CTA: Subscribe Now | Hit the bell for notifications]

[MUSIC: upbeat.mp3 | -12dB]
EOF
    print_status "Created sample script template"
else
    print_status "Script template already exists"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 8: Verifying Installation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check Python packages
echo "Checking Python packages..."
REQUIRED_PACKAGES=("piper-tts" "torch" "moviepy" "opencv-python")
for package in "${REQUIRED_PACKAGES[@]}"; do
    if python -c "import ${package//-/_}" 2>/dev/null; then
        print_status "$package installed"
    else
        print_warning "$package may not be properly installed"
    fi
done

# Check directories
echo ""
echo "Checking directory structure..."
for dir in "${directories[@]}"; do
    if [ -d "$dir" ]; then
        print_status "$dir exists"
    else
        print_error "$dir missing"
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "KnockOff has been installed to: $INSTALL_DIR"
echo ""
echo "Next Steps:"
echo "1. Add your avatar video to avatars/ folder"
echo "2. Add B-roll clips to broll/ folder"
echo "3. Create your first script using templates/video-script-template.md"
echo "4. Complete Easy-Wav2Lip setup at $EASY_WAV2LIP_DIR"
echo ""
echo "To activate the virtual environment:"
echo "  cd $INSTALL_DIR"
echo "  source .venv/bin/activate"
echo ""
echo "To generate your first video:"
echo "  python tools/generate_avatar_video.py --script scripts/my-video.md --avatar my-avatar"
echo ""
echo "For more information, see:"
echo "  - README.md - Quick start guide"
echo "  - KNOCKOFF-GENERATOR.md - Complete documentation"
echo "  - PRODUCTION-WORKFLOW.md - Step-by-step workflow"
echo ""
