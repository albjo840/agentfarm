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

// Message expansion settings
const MESSAGE_TRUNCATE_LENGTH = 200;
let expandedMessages = new Set(); // Track expanded message IDs

// Agent status tracking
let agentStates = {
    orchestrator: 'idle',
    planner: 'idle',
    executor: 'idle',
    verifier: 'idle',
    reviewer: 'idle',
    ux: 'idle'
};

// DOM Elements
const messagesContainer = document.getElementById('messages');
const taskInput = document.getElementById('task-input');
const executeBtn = document.getElementById('execute-btn');

// Initialize
function init() {
    console.log('App init() called');
    console.log('window.RobotVisualizer:', window.RobotVisualizer);

    // Initialize robot visualizer
    if (window.RobotVisualizer) {
        console.log('Creating RobotVisualizer...');
        robotVisualizer = new RobotVisualizer('robot-arena');
        robotVisualizer.init();
        console.log('RobotVisualizer initialized');
    } else {
        console.warn('RobotVisualizer not found - robots will not be displayed');
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
            // Reset all agent states to idle
            Object.keys(agentStates).forEach(id => setAgentState(id, 'idle'));
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
            // Refresh user data to update workflow counter
            loadUserData();
            break;

        case 'workflow_result':
            if (data.summary) {
                addMessage('orchestrator', `Summary: ${data.summary.substring(0, 300)}...`);
            }
            addMessage('orchestrator', `Total tokens used: ${data.tokens?.toLocaleString() || '0'}`);
            break;

        case 'workflow_error':
            // Detailed error with traceback
            isRunning = false;
            executeBtn.disabled = false;
            executeBtn.querySelector('span').textContent = 'EXECUTE';
            setActiveAgent('orchestrator');
            // Reset all agent states to idle
            Object.keys(agentStates).forEach(id => setAgentState(id, 'idle'));
            // Stop idle behavior when workflow ends
            if (robotVisualizer) {
                robotVisualizer.stopIdleBehavior();
                AGENTS.forEach(agent => {
                    robotVisualizer.returnHome(agent.id);
                    robotVisualizer.setWorking(agent.id, false);
                });
            }
            // Check if this is a "no workflows remaining" error
            if (data.upgrade_url) {
                addMessage('orchestrator', `✗ ${data.error}`);
                // Show Beta Operator modal
                openModal('beta-operator-modal');
            } else {
                // Show full error message with traceback (expandable)
                const errorMsg = data.error || 'Unknown error';
                const traceback = data.traceback || '';
                const fullError = traceback ? `${errorMsg}\n\n--- TRACEBACK ---\n${traceback}` : errorMsg;
                addMessage('orchestrator', `✗ WORKFLOW ERROR:\n${fullError}`);
            }
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

    // Set agent to 'speaking' state briefly when they send a message
    if (agentStates[agentId] !== undefined) {
        setAgentState(agentId, 'speaking');
        // Return to working/idle after speaking animation
        setTimeout(() => {
            if (agentStates[agentId] === 'speaking') {
                setAgentState(agentId, activeAgent === agentId ? 'working' : 'idle');
            }
        }, 2000);
    }

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

        // Check if message needs truncation
        const content = msg.content || '';
        const isExpanded = expandedMessages.has(msg.id);
        const needsTruncation = content.length > MESSAGE_TRUNCATE_LENGTH && !msg.streaming;
        const displayContent = needsTruncation && !isExpanded
            ? content.substring(0, MESSAGE_TRUNCATE_LENGTH) + '...'
            : content;

        const expandableClass = needsTruncation ? ' expandable' : '';
        const expandedClass = isExpanded ? ' expanded' : '';

        return `
            <div class="message ${msg.agent.id}${streamingClass}${expandableClass}${expandedClass}" data-msg-id="${msg.id}">
                <div class="message-header">
                    <span class="message-agent" style="color: ${color};">
                        ${name}
                    </span>
                    <span class="message-time">${msg.time}</span>
                    ${msg.streaming ? '<span class="streaming-badge">STREAMING</span>' : ''}
                    <div class="message-actions">
                        <button class="msg-copy-btn" onclick="copyMessageToClipboard(${msg.id})" title="Kopiera">
                            <span class="copy-icon">⎘</span>
                        </button>
                    </div>
                </div>
                <div class="message-content">${escapeHtml(displayContent)}${streamingCursor}</div>
                ${needsTruncation ? `
                    <button class="msg-expand-btn" onclick="toggleMessageExpand(${msg.id})">
                        ${isExpanded ? '▲ COLLAPSE' : '▼ EXPAND'}
                    </button>
                ` : ''}
            </div>
        `;
    }).join('');

    // Auto-scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Toggle message expansion
function toggleMessageExpand(msgId) {
    if (expandedMessages.has(msgId)) {
        expandedMessages.delete(msgId);
    } else {
        expandedMessages.add(msgId);
    }
    renderMessages();
}

// Copy message content to clipboard
async function copyMessageToClipboard(msgId) {
    const msg = messages.find(m => m.id === msgId);
    if (!msg) return;

    try {
        await navigator.clipboard.writeText(msg.content);
        // Show feedback
        const btn = document.querySelector(`[data-msg-id="${msgId}"] .msg-copy-btn`);
        if (btn) {
            const originalText = btn.innerHTML;
            btn.innerHTML = '<span class="copy-icon">✓</span>';
            btn.classList.add('copied');
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.classList.remove('copied');
            }, 1500);
        }
    } catch (err) {
        console.error('Failed to copy:', err);
    }
}

// Set active agent
function setActiveAgent(agentId) {
    activeAgent = agentId;

    // Update agent states - set new agent to working, others to idle
    Object.keys(agentStates).forEach(id => {
        if (id === agentId) {
            setAgentState(id, 'working');
        } else if (agentStates[id] === 'working') {
            setAgentState(id, 'idle');
        }
    });

    if (robotVisualizer) {
        robotVisualizer.setActive(agentId);
        // Animate data transfer from orchestrator to active agent
        if (agentId !== 'orchestrator') {
            robotVisualizer.animateDataTransfer('orchestrator', agentId);
        }
    }
}

// Set agent state (idle, working, speaking)
function setAgentState(agentId, state) {
    agentStates[agentId] = state;
    updateAgentStatusIndicators();
}

// Update agent status indicators in UI
function updateAgentStatusIndicators() {
    Object.keys(agentStates).forEach(agentId => {
        const indicator = document.querySelector(`.agent-status-indicator[data-agent="${agentId}"]`);
        if (indicator) {
            indicator.classList.remove('idle', 'working', 'speaking');
            indicator.classList.add(agentStates[agentId]);
        }
    });
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
    console.log('executeTask called with:', task);
    console.log('isRunning:', isRunning, 'ws:', ws?.readyState);
    console.log('currentUserData:', currentUserData);

    if (isRunning) {
        addMessage('orchestrator', 'System är upptaget. Vänta tills pågående workflow är klart.');
        return;
    }

    if (!ws || ws.readyState !== WebSocket.OPEN) {
        addMessage('orchestrator', 'Inte ansluten till servern. Ladda om sidan.');
        return;
    }

    // Check if user has access (tryout, prompts, or admin)
    const hasAccess = currentUserData?.is_admin ||
                      currentUserData?.is_tryout ||
                      currentUserData?.prompts_remaining > 0 ||
                      currentUserData?.tier === 'early_access';

    console.log('hasAccess:', hasAccess);

    if (!hasAccess) {
        // Show tryout modal
        console.log('No access - opening tryout modal');
        openModal('tryout-modal');
        addMessage('orchestrator', '🔒 Du behöver starta en tryout för att köra workflows. Klicka på TRYOUT-knappen!');
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

    taskInput.addEventListener('keydown', (e) => {
        // Ctrl+Enter or Cmd+Enter to submit (textarea needs modifier key)
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
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

    // Also show download button
    showDownloadButton(projectPath);
}

function hideLaunchButton() {
    const container = document.getElementById('launch-container');
    if (container) {
        container.classList.add('hidden');
    }
    hideDownloadButton();
}

function showDownloadButton(projectPath) {
    let downloadContainer = document.getElementById('download-container');

    // Create download container if it doesn't exist
    if (!downloadContainer) {
        downloadContainer = document.createElement('div');
        downloadContainer.id = 'download-container';
        downloadContainer.className = 'download-container';
        downloadContainer.innerHTML = `
            <button class="download-zip-btn" onclick="downloadProjectZip()">
                <span class="download-icon">📦</span>
                <span>DOWNLOAD ZIP</span>
            </button>
        `;
        // Insert after launch container or in message flow
        const launchContainer = document.getElementById('launch-container');
        if (launchContainer && launchContainer.parentNode) {
            launchContainer.parentNode.insertBefore(downloadContainer, launchContainer.nextSibling);
        }
    }

    downloadContainer.classList.remove('hidden');
    downloadContainer.dataset.path = projectPath;
}

function hideDownloadButton() {
    const downloadContainer = document.getElementById('download-container');
    if (downloadContainer) {
        downloadContainer.classList.add('hidden');
    }
}

async function downloadProjectZip() {
    if (!currentProjectPath) {
        addMessage('orchestrator', '✗ No project path available');
        return;
    }

    addMessage('orchestrator', '📦 Förbereder ZIP-nedladdning...');

    try {
        // Create download link
        const downloadUrl = `/api/projects/download-zip?path=${encodeURIComponent(currentProjectPath)}`;

        // Create temporary link and click it
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = '';  // Let server set filename
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        addMessage('orchestrator', '✓ ZIP-nedladdning startad');
    } catch (err) {
        console.error('Download error:', err);
        addMessage('orchestrator', `✗ Nedladdning misslyckades: ${err.message}`);
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
    // Check if user has access first
    if (!currentUserData?.is_admin && !currentUserData?.is_tryout && !currentUserData?.prompts_remaining) {
        // Show tryout modal instead
        openModal('tryout-modal');
        addMessage('orchestrator', '🔒 VPN-access kräver att du startar en tryout först.');
        return;
    }

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
        } else if (result.require_tryout) {
            // Close QR modal and open tryout modal
            qrModal.classList.add('hidden');
            openModal('tryout-modal');
            addMessage('orchestrator', '🔒 VPN-access kräver att du startar en tryout först.');
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
    initFileUpload();

    // Initialize language toggle (i18n)
    if (window.i18n && window.i18n.initLanguageToggle) {
        window.i18n.initLanguageToggle();
    }

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

    // Wire up Beta Operator button
    const betaOperatorBtn = document.getElementById('beta-operator-btn');
    if (betaOperatorBtn) {
        betaOperatorBtn.addEventListener('click', () => {
            if (currentUserData?.is_beta_operator || currentUserData?.is_admin) {
                // Already Beta Operator - show status
                addMessage('orchestrator', '✓ Du är redan Beta Operator!');
            } else {
                // Show Beta Operator upgrade modal
                openModal('beta-operator-modal');
            }
        });
    }

    // Wire up Beta Operator checkout button
    const checkoutBetaBtn = document.getElementById('checkout-beta-operator');
    if (checkoutBetaBtn) {
        checkoutBetaBtn.addEventListener('click', () => startCheckout('beta_operator'));
    }

    // Wire up start tryout button (for first-time users)
    const startTryoutBtn = document.getElementById('start-tryout-btn');
    if (startTryoutBtn) {
        startTryoutBtn.addEventListener('click', startTryout);
    }

    // Wire up feedback button - now Beta Operator only
    const feedbackBtn = document.getElementById('feedback-btn');
    if (feedbackBtn) {
        feedbackBtn.addEventListener('click', () => {
            if (currentUserData?.is_beta_operator || currentUserData?.is_admin) {
                openModal('feedback-modal');
            } else {
                openModal('beta-operator-modal');
            }
        });
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

    // Wire up agent prompts button - Beta Operator only
    const agentPromptsBtn = document.getElementById('agent-prompts-btn');
    if (agentPromptsBtn) {
        agentPromptsBtn.addEventListener('click', () => {
            if (currentUserData?.is_beta_operator || currentUserData?.is_admin) {
                openModal('agent-prompts-modal');
            } else {
                openModal('beta-operator-modal');
            }
        });
    }

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
            updatePromptsDisplay();
        }
    } catch (e) {
        console.error('Failed to load user data:', e);
    }
}

async function startTryout() {
    console.log('startTryout called');
    const btn = document.getElementById('start-tryout-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>REGISTRERAR...</span>';
    }

    try {
        const response = await fetch('/api/user/tryout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        console.log('Tryout response status:', response.status);
        console.log('Tryout response headers:', response.headers.get('content-type'));

        // Get raw text first to debug
        const text = await response.text();
        console.log('Tryout raw response:', text.substring(0, 200));

        // Try to parse as JSON
        let data;
        try {
            data = JSON.parse(text);
        } catch (parseError) {
            console.error('JSON parse error:', parseError);
            console.error('Raw response was:', text);
            alert('Server returnerade ogiltig data. Kolla konsolen för detaljer.');
            return;
        }

        console.log('Tryout response data:', data);

        if (response.ok) {
            currentUserData = data.user;
            updateUserStatusDisplay();

            // Close modal
            closeModal('tryout-modal');

            // Show welcome message
            addMessage('orchestrator', '🎉 Välkommen! Du har nu 1 gratis workflow att testa. Skriv in en uppgift och klicka EXECUTE!');

            // Update tryout button
            updateTryoutButton();
        } else {
            alert('Kunde inte starta tryout: ' + (data.error || 'Okänt fel'));
        }
    } catch (e) {
        console.error('Tryout error:', e);
        alert('Ett fel uppstod: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span>▶ STARTA TRYOUT</span>';
        }
    }
}

function updateBetaOperatorButton() {
    const betaBtn = document.getElementById('beta-operator-btn');
    if (!betaBtn) return;

    if (currentUserData?.is_admin) {
        betaBtn.innerHTML = '<span class="beta-operator-icon">★</span><span class="beta-operator-label">ADMIN</span>';
        betaBtn.classList.add('active');
    } else if (currentUserData?.is_beta_operator) {
        const remaining = currentUserData.prompts_remaining || 0;
        betaBtn.innerHTML = `<span class="beta-operator-icon">⚡</span><span class="beta-operator-label">${remaining} KVAR</span>`;
        betaBtn.classList.add('active');
    } else if (currentUserData?.is_tryout || currentUserData?.prompts_remaining > 0) {
        const remaining = currentUserData.prompts_remaining || 0;
        betaBtn.innerHTML = `<span class="beta-operator-icon">▶</span><span class="beta-operator-label">${remaining} KVAR</span>`;
        betaBtn.classList.remove('active');
    } else {
        betaBtn.innerHTML = '<span class="beta-operator-icon">⚡</span><span class="beta-operator-label">BETA OPERATOR</span>';
        betaBtn.classList.remove('active');
    }
}

// Legacy alias
function updateTryoutButton() {
    updateBetaOperatorButton();
}

function updateUserStatusDisplay() {
    if (!currentUserData) return;

    const statusEl = document.getElementById('user-status');
    const tierBadge = document.getElementById('tier-badge');

    // Update status display
    if (statusEl) {
        if (currentUserData.is_admin) {
            statusEl.textContent = 'ADMIN';
        } else if (currentUserData.is_beta_operator) {
            statusEl.textContent = 'BETA OP';
        } else if (currentUserData.tier === 'early_access') {
            statusEl.textContent = 'PRO';
        } else if (currentUserData.is_tryout || currentUserData.prompts_remaining > 0) {
            statusEl.textContent = 'TRYOUT';
        } else {
            statusEl.textContent = 'GÄST';
        }
    }

    // Update tier badge
    if (tierBadge) {
        if (currentUserData.is_admin) {
            tierBadge.textContent = 'ADMIN';
            tierBadge.className = 'tier-badge admin';
        } else if (currentUserData.is_beta_operator) {
            tierBadge.textContent = 'BETA OPERATOR';
            tierBadge.className = 'tier-badge beta-operator';
        } else if (currentUserData.tier === 'early_access') {
            tierBadge.textContent = 'EARLY ACCESS';
            tierBadge.className = 'tier-badge early_access';
        } else if (currentUserData.is_tryout || currentUserData.prompts_remaining > 0) {
            tierBadge.textContent = '';
            tierBadge.className = 'tier-badge tryout';
        } else {
            tierBadge.textContent = '';
            tierBadge.className = 'tier-badge';
        }
    }

    // Update Beta Operator button
    updateBetaOperatorButton();

    // Update gated sections
    updateGatedSections();
}

function updateGatedSections() {
    const fileUploadSection = document.getElementById('file-upload-section');
    const feedbackBtn = document.getElementById('feedback-btn');
    const agentPromptsBtn = document.getElementById('agent-prompts-btn');

    // Beta Operator features require paid access
    const isBetaOperator = currentUserData?.is_admin ||
                          currentUserData?.is_beta_operator ||
                          currentUserData?.tier === 'early_access';

    // Basic workflow access (tryout or paid)
    const hasWorkflowAccess = currentUserData?.is_admin ||
                              currentUserData?.is_beta_operator ||
                              currentUserData?.is_tryout ||
                              currentUserData?.prompts_remaining > 0 ||
                              currentUserData?.tier === 'early_access';

    // File upload - Beta Operator only
    if (fileUploadSection) {
        if (isBetaOperator) {
            fileUploadSection.classList.remove('locked');
            const overlay = document.getElementById('file-upload-overlay');
            if (overlay) overlay.style.display = 'none';
        } else {
            fileUploadSection.classList.add('locked');
            const overlay = document.getElementById('file-upload-overlay');
            if (overlay) overlay.style.display = 'flex';
        }
    }

    // Feedback button - Beta Operator only
    if (feedbackBtn) {
        if (isBetaOperator) {
            feedbackBtn.classList.remove('locked');
            feedbackBtn.title = 'Skicka feedback';
        } else {
            feedbackBtn.classList.add('locked');
            feedbackBtn.title = 'Beta Operator krävs';
        }
    }

    // Agent prompts button - Beta Operator only
    if (agentPromptsBtn) {
        if (isBetaOperator) {
            agentPromptsBtn.classList.remove('locked');
            agentPromptsBtn.title = 'Anpassa agent system prompts';
        } else {
            agentPromptsBtn.classList.add('locked');
            agentPromptsBtn.title = 'Beta Operator krävs';
        }
    }
}

// Legacy function - redirect to new one
function updatePromptsDisplay() {
    updateUserStatusDisplay();
}

// Alias for backwards compatibility
function updateCreditsDisplay() {
    updatePromptsDisplay();
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

function togglePrivacySection() {
    const content = document.getElementById('privacy-content');
    const toggle = document.querySelector('.privacy-toggle');
    if (content && toggle) {
        content.classList.toggle('hidden');
        toggle.classList.toggle('expanded');
    }
}

async function startCheckout(productType) {
    try {
        // Use dedicated endpoint for Beta Operator
        const endpoint = productType === 'beta_operator'
            ? '/api/checkout/beta-operator'
            : '/api/subscription/checkout';

        const response = await fetch(endpoint, {
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
            if (error.already_upgraded) {
                addMessage('orchestrator', '✓ Du är redan Beta Operator!');
                closeModal('beta-operator-modal');
            } else {
                alert('Kunde inte starta checkout: ' + (error.error || 'Okänt fel'));
            }
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

// =============================================================================
// FILE UPLOAD (SecureVault)
// =============================================================================

const ALLOWED_FILE_TYPES = ['.txt', '.md', '.py', '.js', '.json', '.yaml', '.yml', '.csv', '.pdf'];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
let uploadedVaultFiles = [];

function initFileUpload() {
    const dropZone = document.getElementById('file-drop-zone');
    const fileInput = document.getElementById('file-input-hidden');
    const uploadSection = document.getElementById('file-upload-section');

    if (!dropZone || !fileInput) return;

    // Click to open file picker
    dropZone.addEventListener('click', () => {
        fileInput.click();
    });

    // File input change
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            uploadFiles(e.target.files);
        }
    });

    // Drag and drop handlers
    dropZone.addEventListener('dragenter', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('drag-active');
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('drag-active');
    });

    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('drag-active');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('drag-active');

        if (e.dataTransfer.files.length > 0) {
            uploadFiles(e.dataTransfer.files);
        }
    });

    // Load existing vault files
    loadVaultFiles();

    // Check tier and update UI
    checkFileUploadTier();
}

async function checkFileUploadTier() {
    const uploadSection = document.getElementById('file-upload-section');
    if (!uploadSection) return;

    try {
        const response = await fetch('/api/user');
        if (response.ok) {
            const user = await response.json();
            const canUpload = user.tier === 'early_access';

            if (canUpload) {
                uploadSection.classList.remove('locked');
                uploadSection.classList.add('unlocked');
            } else {
                uploadSection.classList.add('locked');
                uploadSection.classList.remove('unlocked');
            }
        }
    } catch (e) {
        console.error('Failed to check tier for file upload:', e);
    }
}

async function uploadFiles(files) {
    const uploadSection = document.getElementById('file-upload-section');

    // Check if locked (free tier)
    if (uploadSection && uploadSection.classList.contains('locked')) {
        addMessage('orchestrator', '⚠️ Filuppladdning kräver Early Access. Klicka på UPGRADE för att låsa upp.');
        return;
    }

    for (const file of files) {
        // Validate file type
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        if (!ALLOWED_FILE_TYPES.includes(ext)) {
            addMessage('orchestrator', `✗ Ogiltig filtyp: ${file.name}. Tillåtna: ${ALLOWED_FILE_TYPES.join(', ')}`);
            continue;
        }

        // Validate file size
        if (file.size > MAX_FILE_SIZE) {
            addMessage('orchestrator', `✗ Filen är för stor: ${file.name}. Max ${MAX_FILE_SIZE / 1024 / 1024}MB`);
            continue;
        }

        // Upload file
        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/files/upload', {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();

            if (response.ok) {
                addMessage('orchestrator', `✓ Fil uppladdad: ${file.name}`);
                loadVaultFiles(); // Refresh list
            } else {
                addMessage('orchestrator', `✗ Uppladdning misslyckades: ${result.error || 'Okänt fel'}`);
            }
        } catch (err) {
            console.error('Upload error:', err);
            addMessage('orchestrator', `✗ Uppladdning misslyckades: ${err.message}`);
        }
    }
}

async function loadVaultFiles() {
    const listContainer = document.getElementById('uploaded-files-list');
    if (!listContainer) return;

    try {
        const response = await fetch('/api/files/vault');
        if (response.ok) {
            const data = await response.json();
            uploadedVaultFiles = data.files || [];
            renderUploadedFiles();
        }
    } catch (e) {
        console.error('Failed to load vault files:', e);
    }
}

function renderUploadedFiles() {
    const listContainer = document.getElementById('uploaded-files-list');
    if (!listContainer) return;

    if (uploadedVaultFiles.length === 0) {
        listContainer.innerHTML = '<div class="vault-empty">Inga filer uppladdade</div>';
        return;
    }

    listContainer.innerHTML = uploadedVaultFiles.map(file => {
        const ext = file.name.split('.').pop().toLowerCase();
        const icon = getFileIcon(file.name);
        const size = formatFileSize(file.size);

        return `
            <div class="vault-file-item" data-filename="${escapeAttr(file.name)}">
                <span class="vault-file-icon">${icon}</span>
                <span class="vault-file-name">${escapeHtml(file.name)}</span>
                <span class="vault-file-size">${size}</span>
                <button class="vault-file-delete" onclick="deleteVaultFile('${escapeAttr(file.name)}')" title="Ta bort">
                    <span>✕</span>
                </button>
            </div>
        `;
    }).join('');
}

async function deleteVaultFile(filename) {
    try {
        const response = await fetch(`/api/files/vault/${encodeURIComponent(filename)}`, {
            method: 'DELETE',
        });

        if (response.ok) {
            addMessage('orchestrator', `✓ Fil borttagen: ${filename}`);
            loadVaultFiles();
        } else {
            const result = await response.json();
            addMessage('orchestrator', `✗ Kunde inte ta bort: ${result.error || 'Okänt fel'}`);
        }
    } catch (err) {
        console.error('Delete error:', err);
    }
}

// Check for payment result in URL
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('payment') === 'success') {
    setTimeout(() => {
        addMessage('system', '✓ Betalning genomförd! Dina prompts har lagts till.', 'success');
        loadUserData(); // Refresh user data to show new prompts
    }, 1000);
    // Clear URL params
    window.history.replaceState({}, document.title, window.location.pathname);
} else if (urlParams.get('payment') === 'cancelled') {
    setTimeout(() => {
        addMessage('system', 'Betalning avbruten.', 'warning');
    }, 1000);
    window.history.replaceState({}, document.title, window.location.pathname);
}

// =============================================================================
// AGENT CUSTOM PROMPTS (Card-based layout)
// =============================================================================

const AGENT_IDS = ['orchestrator', 'planner', 'ux_designer', 'executor', 'verifier', 'reviewer'];
let agentCustomPrompts = {};

function initAgentPrompts() {
    // Wire up character counting for all textareas
    document.querySelectorAll('.agent-custom-prompt').forEach(textarea => {
        textarea.addEventListener('input', () => {
            updateCardCharCount(textarea);
        });
    });

    // Wire up save-all button
    const saveAllBtn = document.getElementById('save-all-prompts');
    if (saveAllBtn) {
        saveAllBtn.addEventListener('click', saveAllAgentPrompts);
    }

    // Wire up clear-all button
    const clearAllBtn = document.getElementById('clear-all-prompts');
    if (clearAllBtn) {
        clearAllBtn.addEventListener('click', clearAllAgentPrompts);
    }
}

function updateCardCharCount(textarea) {
    const card = textarea.closest('.agent-card');
    if (!card) return;

    const countEl = card.querySelector('.char-count .count');
    if (countEl) {
        const count = textarea.value.length;
        countEl.textContent = count;
        countEl.style.color = count > 500 ? 'var(--red)' : 'inherit';
    }
}

async function openAgentPromptsModal() {
    // Load existing prompts from server
    try {
        const response = await fetch('/api/user/agent-prompts');
        if (response.ok) {
            const data = await response.json();
            agentCustomPrompts = data.prompts || {};
        }
    } catch (e) {
        console.error('Failed to load agent prompts:', e);
        agentCustomPrompts = {};
    }

    // Populate all textareas with saved prompts
    AGENT_IDS.forEach(agentId => {
        const textarea = document.querySelector(`.agent-custom-prompt[data-agent="${agentId}"]`);
        if (textarea) {
            textarea.value = agentCustomPrompts[agentId] || '';
            updateCardCharCount(textarea);
        }
    });

    openModal('agent-prompts-modal');
}

async function saveAllAgentPrompts() {
    const saveBtn = document.getElementById('save-all-prompts');
    if (!saveBtn) return;

    // Collect all prompts from textareas
    const prompts = {};
    let hasError = false;

    AGENT_IDS.forEach(agentId => {
        const textarea = document.querySelector(`.agent-custom-prompt[data-agent="${agentId}"]`);
        if (textarea) {
            const text = textarea.value.trim();
            if (text.length > 500) {
                hasError = true;
                // Highlight the card with error
                const card = textarea.closest('.agent-card');
                if (card) card.classList.add('error');
            } else {
                prompts[agentId] = text;
                // Remove error state
                const card = textarea.closest('.agent-card');
                if (card) card.classList.remove('error');
            }
        }
    });

    if (hasError) {
        addMessage('orchestrator', '✗ En eller flera prompter överskrider 500 tecken.');
        return;
    }

    saveBtn.disabled = true;
    saveBtn.innerHTML = '⏳ SPARAR...';

    try {
        const response = await fetch('/api/user/agent-prompts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompts: prompts })
        });

        if (response.ok) {
            agentCustomPrompts = prompts;
            addMessage('orchestrator', '✓ Alla agent-prompter sparade!');

            // Show success animation on cards
            document.querySelectorAll('.agent-card').forEach(card => {
                card.classList.add('saved');
                setTimeout(() => card.classList.remove('saved'), 1000);
            });
        } else {
            const error = await response.json();
            addMessage('orchestrator', `✗ Kunde inte spara: ${error.error || 'Okänt fel'}`);
        }
    } catch (e) {
        console.error('Save agent prompts error:', e);
        addMessage('orchestrator', '✗ Ett fel uppstod vid sparning.');
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = '💾 SPARA ALLA';
    }
}

async function clearAllAgentPrompts() {
    if (!confirm('Rensa ALLA anpassade prompter?')) return;

    // Clear all textareas
    AGENT_IDS.forEach(agentId => {
        const textarea = document.querySelector(`.agent-custom-prompt[data-agent="${agentId}"]`);
        if (textarea) {
            textarea.value = '';
            updateCardCharCount(textarea);
        }
    });

    // Save empty prompts
    await saveAllAgentPrompts();
}

// Initialize agent prompts when DOM is ready
document.addEventListener('DOMContentLoaded', initAgentPrompts);
