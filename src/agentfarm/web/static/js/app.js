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

        case 'workflow_start':
            isRunning = true;
            executeBtn.disabled = true;
            executeBtn.querySelector('span').textContent = 'RUNNING...';
            ['plan', 'execute', 'verify', 'review'].forEach(s => setStageStatus(s, null));
            addMessage('orchestrator', `Initiating workflow: "${data.task}" via ${data.provider.toUpperCase()}`);
            break;

        case 'stage_change':
            setStageStatus(data.stage, data.status);
            if (data.status === 'active') {
                // Set active agent based on stage
                const stageToAgent = {
                    'plan': 'planner',
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
            if (data.success) {
                addMessage('orchestrator', '✓ Workflow completed successfully.');
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

        default:
            console.log('Unknown message type:', data.type, data);
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

    stage.classList.remove('active', 'complete', 'error');
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

    // Multi-provider mode - no provider selection needed
    ws.send(JSON.stringify({
        type: 'execute',
        task: task,
        workdir: workingDir,
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

// Start
document.addEventListener('DOMContentLoaded', () => {
    init();
    musicController.init();
});
