#!/bin/bash
# Ollama Concurrency Configuration for AgentFarm
# Run this on your Ollama VM (via Proxmox passthrough)

set -e

echo "=== AgentFarm Ollama Configuration ==="
echo ""

# Configuration for AMD RX 7800 XT (16GB VRAM)
OLLAMA_NUM_PARALLEL=4      # Max parallel requests
OLLAMA_MAX_LOADED_MODELS=2 # Max models in VRAM at once
OLLAMA_KEEP_ALIVE="5m"     # Keep model loaded for 5 min

echo "Settings:"
echo "  OLLAMA_NUM_PARALLEL=$OLLAMA_NUM_PARALLEL"
echo "  OLLAMA_MAX_LOADED_MODELS=$OLLAMA_MAX_LOADED_MODELS"
echo "  OLLAMA_KEEP_ALIVE=$OLLAMA_KEEP_ALIVE"
echo ""

# Check if running as root (needed for systemd)
if [ "$EUID" -ne 0 ]; then
    echo "Note: Run as root to configure systemd service"
    echo ""
    echo "Manual configuration - add to your shell profile:"
    echo ""
    echo "  export OLLAMA_NUM_PARALLEL=$OLLAMA_NUM_PARALLEL"
    echo "  export OLLAMA_MAX_LOADED_MODELS=$OLLAMA_MAX_LOADED_MODELS"
    echo "  export OLLAMA_KEEP_ALIVE=$OLLAMA_KEEP_ALIVE"
    echo ""
    exit 0
fi

# Create systemd override for Ollama
mkdir -p /etc/systemd/system/ollama.service.d/

cat > /etc/systemd/system/ollama.service.d/agentfarm.conf << EOF
[Service]
Environment="OLLAMA_NUM_PARALLEL=$OLLAMA_NUM_PARALLEL"
Environment="OLLAMA_MAX_LOADED_MODELS=$OLLAMA_MAX_LOADED_MODELS"
Environment="OLLAMA_KEEP_ALIVE=$OLLAMA_KEEP_ALIVE"
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF

echo "Created systemd override at /etc/systemd/system/ollama.service.d/agentfarm.conf"

# Reload systemd
systemctl daemon-reload

# Restart Ollama
echo "Restarting Ollama service..."
systemctl restart ollama

# Verify
sleep 2
if systemctl is-active --quiet ollama; then
    echo ""
    echo "✓ Ollama restarted successfully!"
    echo ""
    echo "Current settings:"
    systemctl show ollama --property=Environment | tr ' ' '\n' | grep OLLAMA
else
    echo ""
    echo "✗ Ollama failed to start. Check: journalctl -u ollama"
    exit 1
fi

echo ""
echo "=== VRAM Usage Guide ==="
echo ""
echo "Model              | VRAM  | Max Parallel (16GB)"
echo "-------------------|-------|--------------------"
echo "llama3.2:3b        | ~2GB  | 6-8"
echo "qwen2.5-coder:7b   | ~5GB  | 2-3"
echo "qwen3:14b          | ~9GB  | 1"
echo "mistral-nemo:12b   | ~8GB  | 1"
echo ""
echo "Recommended: Use qwen2.5-coder:7b as primary model"
echo "  - Good code quality"
echo "  - 2-3 parallel requests with 16GB VRAM"
echo ""
echo "Done!"
