/**
 * AgentFarm Neural Interface
 * 80s Sci-Fi Retro Dashboard with Pixel Art Robots
 * Real-time WebSocket connection to backend
 */

// Use agents from robots.js or define fallback
const AGENTS = window.ROBOT_AGENTS || [
    { id: 'orchestrator', name: 'ORCHESTRATOR', color: '#00fff2' },
    { id: 'planner', name: 'PLANNER', color: '#0066ff' },
    { id: 'executor', name: 'EXECUTOR', color: '#ff00ff' },
    { id: 'verifier', name: 'VERIFIER', color: '#00ff88' },
    { id: 'reviewer', name: 'REVIEWER', color: '#ffff00' },
    { id: 'ux', name: 'UX DESIGNER', color: '#ff6b6b' },
];

// Agent colors for messages
const AGENT_COLORS = {
    orchestrator: '#00fff2',
    planner: '#0066ff',
    executor: '#ff00ff',
    verifier: '#00ff88',
    reviewer: '#ffff00',
    ux: '#ff6b6b'
};

// State
let activeAgent = null;
let messages = [];
let isRunning = false;
let tokenCount = 0;
let ws = null;
let workingDir = '.';
let availableProviders = [];
let robotVisualizer = null;
let currentProjectPath = null;

// DOM Elements
const messagesContainer = document.getElementById('messages');
const taskInput = document.getElementById('task-input');
const executeBtn = document.getElementById('execute-btn');

// Initialize
function init() {
    // Initialize robot visualizer
    if (window.RobotVisualizer) {
        robotVisualizer = new RobotVisualizer('robot-arena');
        robotVisualizer.init();
    }

    setupEventListeners();
    startClock();
    connectWebSocket();

    addMessage('orchestrator', 'System initialized. Connecting to neural network...');
}

// WebSocket connection
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        addMessage('orchestrator', 'Neural interface connected. Ready for commands.');
    };

    ws.onclose = () => {
        addMessage('orchestrator', 'Connection lost. Attempting reconnect...');
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleServerMessage(data);
    };
}

// Handle messages from server
function handleServerMessage(data) {
    switch (data.type) {
        case 'connected':
            workingDir = data.working_dir || '.';
            if (data.providers) {
                updateProviderSelect(data.providers);
            }
            break;

        case 'project_created':
            currentProjectPath = data.path;
            addMessage('orchestrator', `📁 Projekt skapat: ${data.path}`);
            // Hide launch button when new project starts
            hideLaunchButton();
            break;

        case 'workflow_start':
            isRunning = true;
            executeBtn.disabled = true;
            executeBtn.querySelector('span').textContent = 'RUNNING...';
            ['plan', 'ux_design', 'execute', 'verify', 'review'].forEach(s => setStageStatus(s, null));
            addMessage('orchestrator', `Initiating workflow: "${data.task}" via ${data.provider.toUpperCase()}`);
            // Start idle behavior for visual life
            if (robotVisualizer) {
                robotVisualizer.startIdleBehavior();
            }
            break;

        case 'stage_change':
            setStageStatus(data.stage, data.status);
            if (data.status === 'active') {
                // Set active agent based on stage
                const stageToAgent = {
                    'plan': 'planner',
                    'ux_design': 'ux',
                    'execute': 'executor',
                    'verify': 'verifier',
                    'review': 'reviewer'
                };
                setActiveAgent(stageToAgent[data.stage] || 'orchestrator');
            }
            break;

        case 'agent_message':
            addMessage(data.agent, data.content);
            // Animate robot communication
            if (robotVisualizer) {
                // Determine who is talking to whom
                const fromAgent = data.agent;
                const toAgent = data.target || 'orchestrator';

                // Queue the walk and speak animation
                robotVisualizer.queueCommunication(fromAgent, toAgent, data.content);
            }
            break;

        case 'agent_handoff':
            // When one agent hands off to another
            if (robotVisualizer && data.from && data.to) {
                robotVisualizer.queueCommunication(data.from, data.to, data.message || `Överlämnar till ${data.to}`);
            }
            break;

        case 'tokens_update':
            tokenCount = data.tokens || 0;
            document.getElementById('token-count').textContent = tokenCount.toLocaleString();
            break;

        case 'workflow_complete':
            isRunning = false;
            executeBtn.disabled = false;
            executeBtn.querySelector('span').textContent = 'EXECUTE';
            setActiveAgent('orchestrator');
            // Stop idle behavior when workflow ends
            if (robotVisualizer) {
                robotVisualizer.stopIdleBehavior();
                // Return all robots to home positions
                AGENTS.forEach(agent => {
                    robotVisualizer.returnHome(agent.id);
                    robotVisualizer.setWorking(agent.id, false);
                });
            }
            if (data.success) {
                addMessage('orchestrator', '✓ Workflow completed successfully.');
                // Show launch button if we have a project path
                if (currentProjectPath) {
                    showLaunchButton(currentProjectPath);
                }
            } else {
                addMessage('orchestrator', `✗ Workflow failed: ${data.error || 'Unknown error'}`);
            }
            break;

        case 'workflow_result':
            if (data.summary) {
                addMessage('orchestrator', `Summary: ${data.summary.substring(0, 300)}...`);
            }
            addMessage('orchestrator', `Total tokens used: ${data.tokens?.toLocaleString() || '0'}`);
            break;

        case 'pong':
            // Heartbeat response
            break;

        // ============================================
        // NEW EVENTS: Parallel Execution & Collaboration
        // ============================================

        case 'parallel_execution_start':
            // Parallel step execution starting
            addMessage('orchestrator', `⚡ Startar parallell exekvering: ${data.total_steps} steg i ${data.groups?.length || 0} grupper`);
            break;

        case 'parallel_group_start':
            // A group of parallel steps is starting
            addMessage('orchestrator', `▶ Kör ${data.step_ids?.length || 0} steg parallellt...`);
            // Mark multiple robots as working
            if (robotVisualizer && data.step_ids) {
                data.step_ids.forEach(() => {
                    robotVisualizer.setWorking('executor', true);
                });
            }
            break;

        case 'step_start':
            // Single step starting
            if (robotVisualizer) {
                robotVisualizer.setWorking('executor', true);
                if (data.parallel) {
                    // Mark as parallel-active for special animation
                    const robot = document.querySelector('[data-agent="executor"]');
                    if (robot) robot.classList.add('parallel-active');
                }
            }
            break;

        case 'step_complete':
            // Single step completed
            if (robotVisualizer) {
                robotVisualizer.setWorking('executor', false);
                const robot = document.querySelector('[data-agent="executor"]');
                if (robot) robot.classList.remove('parallel-active');
            }
            if (!data.success) {
                addMessage('executor', `✗ Steg ${data.step_id} misslyckades`);
            }
            break;

        case 'agent_collaboration':
            // Proactive collaboration between agents
            handleAgentCollaboration(data);
            break;

        case 'agent_thinking':
            // Agent is processing/thinking
            if (robotVisualizer && data.agent) {
                robotVisualizer.showThinkingAnimation(data.agent);
            }
            break;

        default:
            console.log('Unknown message type:', data.type, data);
    }
}

/**
 * Handle agent collaboration events - shows robots moving together and discussing
 */
function handleAgentCollaboration(data) {
    const { initiator, participants, collaboration_type, topic } = data;

    // Log collaboration to message stream
    const typeLabels = {
        'peer_review': '👀 Peer Review',
        'brainstorm': '💡 Brainstorm',
        'sanity_check': '✓ Sanity Check',
        'knowledge_share': '📚 Knowledge Share'
    };
    const typeLabel = typeLabels[collaboration_type] || collaboration_type;
    const participantNames = participants.filter(p => p !== initiator).join(', ');

    addMessage(initiator, `${typeLabel} med ${participantNames}: "${topic}"`);

    // Animate robots moving together
    if (robotVisualizer) {
        // Show collaboration visualization
        robotVisualizer.showCollaboration(initiator, participants, topic);

        // Move robots toward each other
        participants.forEach(participant => {
            if (participant !== initiator) {
                robotVisualizer.gravitateToward(participant, initiator, 80);
            }
        });

        // After collaboration, return to positions
        setTimeout(() => {
            participants.forEach(participant => {
                robotVisualizer.returnHome(participant);
            });
        }, 3000);
    }
}

// Update provider info (multi-provider mode - no dropdown needed)
function updateProviderSelect(providers) {
    availableProviders = providers;
    // In multi-provider mode, we just store the available providers
    // The orchestrator will automatically use the best provider for each agent
    console.log('Available providers:', providers.filter(p => p.available).map(p => p.name));
}

// Add message to stream
function addMessage(agentId, content) {
    let agent = AGENTS.find(a => a.id === agentId);

    // Create a fallback agent object if not found
    if (!agent) {
        agent = {
            id: agentId,
            name: agentId.toUpperCase(),
            color: AGENT_COLORS[agentId] || '#00fff2'
        };
    }

    const message = {
        id: Date.now(),
        agent: agent,
        content: content,
        time: new Date().toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    };

    messages.push(message);
    renderMessages();
}

// Make addMessage available globally for robots.js
window.addMessage = addMessage;

// Render messages
function renderMessages() {
    messagesContainer.innerHTML = messages.slice(-50).map(msg => {
        const color = msg.agent.color || AGENT_COLORS[msg.agent.id] || '#00fff2';
        const name = msg.agent.name || msg.agent.id.toUpperCase();
        return `
            <div class="message ${msg.agent.id}">
                <div class="message-header">
                    <span class="message-agent" style="color: ${color};">
                        ${name}
                    </span>
                    <span class="message-time">${msg.time}</span>
                </div>
                <div class="message-content">${escapeHtml(msg.content)}</div>
            </div>
        `;
    }).join('');

    // Auto-scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Set active agent
function setActiveAgent(agentId) {
    activeAgent = agentId;
    if (robotVisualizer) {
        robotVisualizer.setActive(agentId);
        // Animate data transfer from orchestrator to active agent
        if (agentId !== 'orchestrator') {
            robotVisualizer.animateDataTransfer('orchestrator', agentId);
        }
    }
}

// Update workflow stage
function setStageStatus(stageId, status) {
    const stage = document.getElementById(`stage-${stageId}`);
    if (!stage) return;

    stage.classList.remove('active', 'complete', 'error', 'skipped');
    if (status) stage.classList.add(status);

    const statusEl = stage.querySelector('.stage-status');
    switch (status) {
        case 'active':
            statusEl.textContent = 'PROCESSING';
            break;
        case 'complete':
            statusEl.textContent = 'COMPLETE';
            break;
        case 'error':
            statusEl.textContent = 'ERROR';
            break;
        case 'skipped':
            statusEl.textContent = 'SKIPPED';
            break;
        default:
            statusEl.textContent = 'STANDBY';
    }
}

// Execute task via WebSocket (multi-provider mode)
function executeTask(task) {
    if (isRunning || !ws || ws.readyState !== WebSocket.OPEN) {
        addMessage('orchestrator', 'Cannot execute: system busy or not connected.');
        return;
    }

    // Generate project name from task (first 3 words, sanitized)
    const projectName = task
        .split(/\s+/)
        .slice(0, 3)
        .join('-')
        .toLowerCase()
        .replace(/[^a-zA-Z0-9åäö-]/g, '')
        .replace(/-+/g, '-')
        .trim() || 'nytt-projekt';

    // Create project in ~/nya projekt/ and run workflow
    ws.send(JSON.stringify({
        type: 'create_project',
        name: projectName,
        prompt: task,
    }));
}

// Event listeners
function setupEventListeners() {
    executeBtn.addEventListener('click', () => {
        const task = taskInput.value.trim();
        if (task) {
            executeTask(task);
            taskInput.value = '';
        }
    });

    taskInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            executeBtn.click();
        }
    });
}

// Start clock
function startClock() {
    const update = () => {
        const now = new Date();
        document.getElementById('current-time').textContent =
            now.toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };
    update();
    setInterval(update, 1000);
}

// Utilities
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Synthwave Music Controller
const musicController = {
    audio: null,
    isPlaying: false,
    button: null,

    init() {
        this.audio = document.getElementById('bg-music');
        this.button = document.getElementById('music-toggle');

        if (!this.audio || !this.button) return;

        // Set initial volume
        this.audio.volume = 0.3;

        // Toggle on button click
        this.button.addEventListener('click', () => this.toggle());

        // Update button state when audio ends/plays
        this.audio.addEventListener('play', () => this.updateState(true));
        this.audio.addEventListener('pause', () => this.updateState(false));
        this.audio.addEventListener('ended', () => this.updateState(false));
    },

    toggle() {
        if (this.isPlaying) {
            this.audio.pause();
        } else {
            this.audio.play().catch(err => {
                console.log('Audio autoplay blocked:', err);
                addMessage('orchestrator', 'Click the music button again to start synthwave audio.');
            });
        }
    },

    updateState(playing) {
        this.isPlaying = playing;
        if (this.button) {
            this.button.classList.toggle('playing', playing);
        }
    }
};

// Heartbeat to keep connection alive
setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
    }
}, 30000);

// Launch button functions
function showLaunchButton(projectPath) {
    const container = document.getElementById('launch-container');
    const pathEl = document.getElementById('launch-path');

    if (container && pathEl) {
        pathEl.textContent = projectPath;
        container.classList.remove('hidden');
    }
}

function hideLaunchButton() {
    const container = document.getElementById('launch-container');
    if (container) {
        container.classList.add('hidden');
    }
}

async function launchProject() {
    if (!currentProjectPath) {
        addMessage('orchestrator', '✗ No project path available');
        return;
    }

    // Open file browser instead of local file manager
    openFileBrowser(currentProjectPath);
}

// ===========================================
// File Browser Functions
// ===========================================

let fileBrowserCurrentPath = null;

function openFileBrowser(path) {
    fileBrowserCurrentPath = path || null;
    const modal = document.getElementById('file-browser-modal');
    if (modal) {
        modal.classList.remove('hidden');
        loadDirectory(path);
    }
}

function closeFileBrowser() {
    const modal = document.getElementById('file-browser-modal');
    if (modal) {
        modal.classList.add('hidden');
    }
    closeFilePreview();
}

async function loadDirectory(path) {
    const fileList = document.getElementById('file-list');
    const pathEl = document.getElementById('file-browser-path');
    const upBtn = document.getElementById('file-browser-up');

    // Show loading
    fileList.innerHTML = '<div class="file-browser-loading">Laddar filer...</div>';

    try {
        const url = path ? `/api/files?path=${encodeURIComponent(path)}` : '/api/files';
        const response = await fetch(url);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Kunde inte ladda filer');
        }

        fileBrowserCurrentPath = data.path;
        pathEl.textContent = data.path;

        // Enable/disable up button
        upBtn.disabled = !data.can_go_up;
        upBtn.dataset.parentPath = data.parent_path || '';

        // Render files
        if (data.files.length === 0) {
            fileList.innerHTML = '<div class="file-list-empty">Mappen är tom</div>';
        } else {
            fileList.innerHTML = data.files.map(file => {
                const icon = file.is_dir ? '📁' : getFileIcon(file.name);
                const sizeStr = file.is_dir ? '' : formatFileSize(file.size);
                const dateStr = formatDate(file.modified);
                const typeClass = file.is_dir ? 'directory' : 'file';

                return `
                    <div class="file-item ${typeClass}"
                         data-path="${escapeAttr(file.path)}"
                         data-is-dir="${file.is_dir}">
                        <span class="file-icon">${icon}</span>
                        <span class="file-name">${escapeHtml(file.name)}</span>
                        <span class="file-size">${sizeStr}</span>
                        <span class="file-date">${dateStr}</span>
                    </div>
                `;
            }).join('');

            // Add click handlers
            fileList.querySelectorAll('.file-item').forEach(item => {
                item.addEventListener('click', () => handleFileClick(item));
            });
        }
    } catch (err) {
        fileList.innerHTML = `<div class="file-list-empty">Fel: ${escapeHtml(err.message)}</div>`;
    }
}

function handleFileClick(item) {
    const path = item.dataset.path;
    const isDir = item.dataset.isDir === 'true';

    if (isDir) {
        loadDirectory(path);
    } else {
        openFilePreview(path);
    }
}

async function openFilePreview(path) {
    const preview = document.getElementById('file-preview');
    const nameEl = document.getElementById('file-preview-name');
    const contentEl = document.getElementById('file-preview-content');
    const downloadLink = document.getElementById('file-preview-download');

    preview.classList.remove('hidden');
    nameEl.textContent = path.split('/').pop();
    contentEl.textContent = 'Laddar...';
    downloadLink.href = `/api/files/download?path=${encodeURIComponent(path)}`;

    try {
        const response = await fetch(`/api/files/content?path=${encodeURIComponent(path)}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Kunde inte läsa fil');
        }

        if (data.binary) {
            contentEl.innerHTML = `
                <div class="file-preview-binary">
                    <div class="binary-icon">📦</div>
                    <div>Binärfil (${formatFileSize(data.size)})</div>
                    <div>Typ: ${data.mime_type || 'okänd'}</div>
                </div>
            `;
        } else {
            contentEl.textContent = data.content || '(tom fil)';
        }
    } catch (err) {
        contentEl.textContent = `Fel: ${err.message}`;
    }
}

function closeFilePreview() {
    const preview = document.getElementById('file-preview');
    if (preview) {
        preview.classList.add('hidden');
    }
}

function navigateUp() {
    const upBtn = document.getElementById('file-browser-up');
    const parentPath = upBtn.dataset.parentPath;
    if (parentPath) {
        loadDirectory(parentPath);
    }
}

// File browser utility functions
function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const icons = {
        'py': '🐍', 'js': '📜', 'ts': '📘', 'html': '🌐', 'css': '🎨',
        'json': '📋', 'md': '📝', 'txt': '📄', 'yml': '⚙️', 'yaml': '⚙️',
        'png': '🖼️', 'jpg': '🖼️', 'jpeg': '🖼️', 'gif': '🖼️', 'svg': '🖼️',
        'pdf': '📕', 'zip': '📦', 'tar': '📦', 'gz': '📦',
        'sh': '⚡', 'bash': '⚡', 'sql': '🗃️', 'db': '🗃️',
    };
    return icons[ext] || '📄';
}

function formatFileSize(bytes) {
    if (bytes === null || bytes === undefined) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
}

function formatDate(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp * 1000);
    return date.toLocaleDateString('sv-SE') + ' ' + date.toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' });
}

function escapeAttr(str) {
    return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// QR Code Modal functions
async function generateNewVPNQR() {
    const qrModal = document.getElementById('qr-modal');
    const qrCode = document.getElementById('qr-code');
    const qrInfo = document.getElementById('qr-info');

    // Show modal with loading state
    qrCode.textContent = 'Genererar...';
    qrInfo.textContent = '';
    qrModal.classList.remove('hidden');

    try {
        const response = await fetch('/api/wireguard/new-peer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();

        if (response.ok && result.success) {
            qrCode.textContent = result.qr_text;
            qrInfo.innerHTML = `IP: <strong>${result.ip}</strong><br>Skanna QR-koden med WireGuard-appen`;
            addMessage('orchestrator', `🔐 Ny VPN-peer skapad: ${result.ip}`);
        } else {
            qrCode.textContent = '❌ Fel';
            qrInfo.textContent = result.error || 'Kunde inte generera QR-kod';
        }
    } catch (err) {
        qrCode.textContent = '❌ Fel';
        qrInfo.textContent = err.message;
    }
}

function closeQRModal() {
    const qrModal = document.getElementById('qr-modal');
    qrModal.classList.add('hidden');
}

// Start
document.addEventListener('DOMContentLoaded', () => {
    init();
    musicController.init();

    // Wire up launch button
    const launchBtn = document.getElementById('launch-btn');
    if (launchBtn) {
        launchBtn.addEventListener('click', launchProject);
    }

    // Wire up QR button
    const qrBtn = document.getElementById('qr-btn');
    if (qrBtn) {
        qrBtn.addEventListener('click', generateNewVPNQR);
    }

    // Wire up QR modal close
    const qrClose = document.getElementById('qr-close');
    if (qrClose) {
        qrClose.addEventListener('click', closeQRModal);
    }

    // Close modal on backdrop click
    const qrModal = document.getElementById('qr-modal');
    if (qrModal) {
        qrModal.addEventListener('click', (e) => {
            if (e.target === qrModal) {
                closeQRModal();
            }
        });
    }

    // Wire up file browser
    const fileBrowserClose = document.getElementById('file-browser-close');
    if (fileBrowserClose) {
        fileBrowserClose.addEventListener('click', closeFileBrowser);
    }

    const fileBrowserUp = document.getElementById('file-browser-up');
    if (fileBrowserUp) {
        fileBrowserUp.addEventListener('click', navigateUp);
    }

    const filePreviewClose = document.getElementById('file-preview-close');
    if (filePreviewClose) {
        filePreviewClose.addEventListener('click', closeFilePreview);
    }

    // Close file browser on backdrop click
    const fileBrowserModal = document.getElementById('file-browser-modal');
    if (fileBrowserModal) {
        fileBrowserModal.addEventListener('click', (e) => {
            if (e.target === fileBrowserModal) {
                closeFileBrowser();
            }
        });
    }
});
