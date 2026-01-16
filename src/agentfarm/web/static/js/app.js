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

// Streaming message tracking
let streamingMessages = {}; // request_id -> {agent, content, messageId}

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
    setupTokenDashboard();

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

        case 'llm_stream_chunk':
            // Handle streaming LLM output
            handleStreamChunk(data);
            break;

        case 'llm_response':
            // Finalize streaming message when LLM response completes
            if (data.streaming && data.request_id) {
                finalizeStreamingMessage(data.request_id);
            }
            // Track tokens for dashboard
            trackTokensFromEvent(data);
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

// Handle streaming chunk from LLM
function handleStreamChunk(data) {
    const { request_id, agent, chunk } = data;
    if (!request_id || !chunk) return;

    const agentId = agent || 'orchestrator';

    if (!streamingMessages[request_id]) {
        // Create new streaming message
        let agentObj = AGENTS.find(a => a.id === agentId);
        if (!agentObj) {
            agentObj = {
                id: agentId,
                name: agentId.toUpperCase(),
                color: AGENT_COLORS[agentId] || '#00fff2'
            };
        }

        const messageId = Date.now();
        const message = {
            id: messageId,
            agent: agentObj,
            content: chunk,
            time: new Date().toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            streaming: true  // Mark as streaming
        };

        messages.push(message);
        streamingMessages[request_id] = {
            agent: agentId,
            content: chunk,
            messageId: messageId
        };
    } else {
        // Append to existing streaming message
        streamingMessages[request_id].content += chunk;

        // Update the message in the messages array
        const msgIndex = messages.findIndex(m => m.id === streamingMessages[request_id].messageId);
        if (msgIndex !== -1) {
            messages[msgIndex].content = streamingMessages[request_id].content;
        }
    }

    renderMessages();
}

// Finalize streaming message (remove streaming indicator)
function finalizeStreamingMessage(request_id) {
    if (!streamingMessages[request_id]) return;

    const msgIndex = messages.findIndex(m => m.id === streamingMessages[request_id].messageId);
    if (msgIndex !== -1) {
        messages[msgIndex].streaming = false;
    }

    delete streamingMessages[request_id];
    renderMessages();
}

// Render messages
function renderMessages() {
    messagesContainer.innerHTML = messages.slice(-50).map(msg => {
        const color = msg.agent.color || AGENT_COLORS[msg.agent.id] || '#00fff2';
        const name = msg.agent.name || msg.agent.id.toUpperCase();
        const streamingCursor = msg.streaming ? '<span class="streaming-cursor">▌</span>' : '';
        const streamingClass = msg.streaming ? ' streaming' : '';
        return `
            <div class="message ${msg.agent.id}${streamingClass}">
                <div class="message-header">
                    <span class="message-agent" style="color: ${color};">
                        ${name}
                    </span>
                    <span class="message-time">${msg.time}</span>
                    ${msg.streaming ? '<span class="streaming-badge">STREAMING</span>' : ''}
                </div>
                <div class="message-content">${escapeHtml(msg.content)}${streamingCursor}</div>
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

// =============================================================================
// TOKEN DASHBOARD
// =============================================================================

let tokenDashboardInterval = null;
let agentTokens = {}; // Track tokens per agent

function setupTokenDashboard() {
    // Toggle collapse
    const toggle = document.getElementById('token-dashboard-toggle');
    const dashboard = document.getElementById('token-dashboard');

    if (toggle && dashboard) {
        toggle.addEventListener('click', () => {
            dashboard.classList.toggle('collapsed');
        });
    }

    // Start polling for performance metrics
    updateTokenDashboard();
    tokenDashboardInterval = setInterval(updateTokenDashboard, 5000); // Every 5 seconds
}

async function updateTokenDashboard() {
    try {
        const response = await fetch('/api/hardware/performance');
        if (!response.ok) return;

        const data = await response.json();
        const overall = data.overall || {};
        const byAgent = data.by_agent || {};

        // Calculate totals from by_model stats
        let totalTokens = 0;
        for (const modelStats of Object.values(data.by_model || {})) {
            if (modelStats.tokens) {
                totalTokens += modelStats.tokens.total || 0;
            }
        }

        // Update overview metrics
        const totalTokensEl = document.getElementById('total-tokens');
        const avgTps = document.getElementById('avg-tps');
        const latencyP95 = document.getElementById('latency-p95');

        if (totalTokensEl) {
            totalTokensEl.textContent = formatNumber(totalTokens);
        }

        if (avgTps && overall.avg_tokens_per_second !== undefined) {
            avgTps.textContent = overall.avg_tokens_per_second.toFixed(1);
        }

        // Get P95 from first model with data
        let p95Latency = 0;
        for (const modelStats of Object.values(data.by_model || {})) {
            if (modelStats.latency_ms && modelStats.latency_ms.p95) {
                p95Latency = modelStats.latency_ms.p95;
                break;
            }
        }
        if (latencyP95) {
            latencyP95.textContent = Math.round(p95Latency) + 'ms';
        }

        // Update agent grid
        updateAgentTokenGrid(byAgent);

    } catch (err) {
        console.error('Failed to update token dashboard:', err);
    }
}

function updateAgentTokenGrid(agentData) {
    const grid = document.getElementById('agent-token-grid');
    if (!grid) return;

    // Merge with tracked tokens from streaming
    const mergedData = { ...agentTokens };
    for (const [agent, stats] of Object.entries(agentData)) {
        // API returns nested format with tokens.input, tokens.output
        const tokens = stats.tokens || {};
        mergedData[agent] = {
            input_tokens: tokens.input || stats.input_tokens || 0,
            output_tokens: tokens.output || stats.output_tokens || 0,
            requests: stats.total_requests || stats.requests || 0,
        };
    }

    // Generate cards
    const agentOrder = ['planner', 'executor', 'verifier', 'reviewer', 'ux', 'orchestrator'];
    const cards = [];

    for (const agentId of agentOrder) {
        const stats = mergedData[agentId];
        if (!stats) continue;

        const color = AGENT_COLORS[agentId] || '#00fff2';
        const input = stats.input_tokens || 0;
        const output = stats.output_tokens || 0;
        const requests = stats.requests || 0;

        cards.push(`
            <div class="agent-token-card" style="border-color: ${color}">
                <div class="agent-name" style="color: ${color}">${agentId.toUpperCase()}</div>
                <div class="agent-stats">
                    <span>IN: <span class="stat-value">${formatNumber(input)}</span></span>
                    <span>OUT: <span class="stat-value">${formatNumber(output)}</span></span>
                </div>
                <div class="agent-stats">
                    <span>REQ: <span class="stat-value">${requests}</span></span>
                </div>
            </div>
        `);
    }

    grid.innerHTML = cards.join('');
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

// Track tokens from LLM events
function trackTokensFromEvent(data) {
    const agent = data.agent || 'unknown';
    if (!agentTokens[agent]) {
        agentTokens[agent] = { input_tokens: 0, output_tokens: 0, requests: 0 };
    }

    if (data.input_tokens) {
        agentTokens[agent].input_tokens += data.input_tokens;
    }
    if (data.output_tokens) {
        agentTokens[agent].output_tokens += data.output_tokens;
    }
    if (data.success !== undefined) {
        agentTokens[agent].requests += 1;
    }
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

    // Initialize monetization UI
    initMonetization();
});

// =============================================================================
// MONETIZATION UI
// =============================================================================

let currentUserData = null;
let selectedRating = null;

async function initMonetization() {
    // Load user data
    await loadUserData();

    // Wire up upgrade button
    const upgradeBtn = document.getElementById('upgrade-btn');
    if (upgradeBtn) {
        upgradeBtn.addEventListener('click', () => openModal('upgrade-modal'));
    }

    // Wire up feedback button
    const feedbackBtn = document.getElementById('feedback-btn');
    if (feedbackBtn) {
        feedbackBtn.addEventListener('click', () => openModal('feedback-modal'));
    }

    // Wire up modal close buttons
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', () => {
            const modalId = btn.getAttribute('data-modal');
            if (modalId) closeModal(modalId);
        });
    });

    // Close modals on backdrop click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.add('hidden');
            }
        });
    });

    // Wire up checkout button
    const checkoutBtn = document.getElementById('checkout-early-access');
    if (checkoutBtn) {
        checkoutBtn.addEventListener('click', () => startCheckout('early_access'));
    }

    // Wire up token pack buttons
    document.querySelectorAll('.token-pack').forEach(btn => {
        btn.addEventListener('click', () => {
            const pack = btn.getAttribute('data-pack');
            startCheckout(`token_pack_${pack}`);
        });
    });

    // Wire up feedback submit
    const submitFeedbackBtn = document.getElementById('submit-feedback');
    if (submitFeedbackBtn) {
        submitFeedbackBtn.addEventListener('click', submitFeedback);
    }

    // Wire up star rating
    const starRating = document.getElementById('star-rating');
    if (starRating) {
        starRating.querySelectorAll('.star').forEach(star => {
            star.addEventListener('click', () => {
                selectedRating = parseInt(star.getAttribute('data-rating'));
                updateStarDisplay();
            });
            star.addEventListener('mouseenter', () => {
                highlightStars(parseInt(star.getAttribute('data-rating')));
            });
        });
        starRating.addEventListener('mouseleave', () => {
            updateStarDisplay();
        });
    }

    // Wire up context save
    const saveContextBtn = document.getElementById('save-context');
    if (saveContextBtn) {
        saveContextBtn.addEventListener('click', saveCompanyContext);
    }
}

async function loadUserData() {
    try {
        const response = await fetch('/api/user');
        if (response.ok) {
            currentUserData = await response.json();
            updateCreditsDisplay();
        }
    } catch (e) {
        console.error('Failed to load user data:', e);
    }
}

function updateCreditsDisplay() {
    if (!currentUserData) return;

    const creditsEl = document.getElementById('credits-balance');
    const tierBadge = document.getElementById('tier-badge');
    const freeCurrent = document.getElementById('free-current');
    const checkoutBtn = document.getElementById('checkout-early-access');

    if (creditsEl) {
        if (currentUserData.tier === 'early_access') {
            creditsEl.textContent = '∞';
        } else {
            creditsEl.textContent = currentUserData.tokens_remaining;
        }
    }

    if (tierBadge) {
        tierBadge.textContent = currentUserData.tier.toUpperCase().replace('_', ' ');
        tierBadge.className = 'tier-badge ' + currentUserData.tier;
    }

    // Update tier comparison in upgrade modal
    if (currentUserData.tier === 'early_access') {
        if (freeCurrent) freeCurrent.style.display = 'none';
        if (checkoutBtn) {
            checkoutBtn.textContent = 'AKTIV';
            checkoutBtn.disabled = true;
        }
    }
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('hidden');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('hidden');
    }
}

async function startCheckout(productType) {
    try {
        const response = await fetch('/api/subscription/checkout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product_type: productType })
        });

        if (response.ok) {
            const data = await response.json();
            if (data.checkout_url) {
                window.location.href = data.checkout_url;
            }
        } else {
            const error = await response.json();
            alert('Kunde inte starta checkout: ' + (error.error || 'Okänt fel'));
        }
    } catch (e) {
        console.error('Checkout error:', e);
        alert('Ett fel uppstod vid checkout');
    }
}

async function submitFeedback() {
    const category = document.getElementById('feedback-category').value;
    const message = document.getElementById('feedback-message').value.trim();
    const email = document.getElementById('feedback-email').value.trim();

    if (!message) {
        alert('Skriv ett meddelande');
        return;
    }

    const submitBtn = document.getElementById('submit-feedback');
    submitBtn.disabled = true;
    submitBtn.textContent = 'SKICKAR...';

    try {
        const response = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                category,
                message,
                email: email || null,
                rating: selectedRating
            })
        });

        if (response.ok) {
            // Clear form
            document.getElementById('feedback-message').value = '';
            document.getElementById('feedback-email').value = '';
            selectedRating = null;
            updateStarDisplay();

            // Close modal
            closeModal('feedback-modal');

            // Show success message
            addMessage('system', 'Tack för din feedback!', 'success');
        } else {
            const error = await response.json();
            alert('Kunde inte skicka feedback: ' + (error.error || 'Okänt fel'));
        }
    } catch (e) {
        console.error('Feedback error:', e);
        alert('Ett fel uppstod');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'SKICKA';
    }
}

function highlightStars(rating) {
    document.querySelectorAll('#star-rating .star').forEach((star, idx) => {
        star.classList.toggle('hovered', idx < rating);
    });
}

function updateStarDisplay() {
    document.querySelectorAll('#star-rating .star').forEach((star, idx) => {
        star.classList.remove('hovered');
        star.classList.toggle('active', selectedRating && idx < selectedRating);
    });
}

async function saveCompanyContext() {
    const context = document.getElementById('company-context').value.trim();
    const saveBtn = document.getElementById('save-context');

    saveBtn.disabled = true;
    saveBtn.textContent = 'SPARAR...';

    try {
        const response = await fetch('/api/user/context', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ context })
        });

        if (response.ok) {
            closeModal('context-modal');
            addMessage('system', 'Företagskontext sparad', 'success');
        } else {
            const error = await response.json();
            alert('Kunde inte spara: ' + (error.error || 'Okänt fel'));
        }
    } catch (e) {
        console.error('Save context error:', e);
        alert('Ett fel uppstod');
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = 'SPARA';
    }
}

// Check for payment result in URL
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('payment') === 'success') {
    setTimeout(() => {
        addMessage('system', 'Betalning genomförd! Välkommen till Early Access.', 'success');
        loadUserData(); // Refresh user data
    }, 1000);
    // Clear URL params
    window.history.replaceState({}, document.title, window.location.pathname);
} else if (urlParams.get('payment') === 'cancelled') {
    setTimeout(() => {
        addMessage('system', 'Betalning avbruten.', 'warning');
    }, 1000);
    window.history.replaceState({}, document.title, window.location.pathname);
}
