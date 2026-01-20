/**
 * Pixel Art Robot Sprites with Walking Animation
 * SVG-based robots for AgentFarm visualization
 */

// Robot SVG templates - pixel art style with walk frames
const ROBOT_SPRITES = {
    orchestrator: `
        <svg viewBox="0 0 32 32" class="robot-svg">
            <!-- Body -->
            <rect x="8" y="12" width="16" height="14" fill="#00fff2"/>
            <rect x="10" y="14" width="12" height="10" fill="#003344"/>
            <!-- Head -->
            <rect x="10" y="4" width="12" height="10" fill="#00fff2"/>
            <rect x="12" y="6" width="8" height="6" fill="#001122"/>
            <!-- Eyes -->
            <rect x="13" y="7" width="2" height="2" fill="#00ffff" class="eye-left"/>
            <rect x="17" y="7" width="2" height="2" fill="#00ffff" class="eye-right"/>
            <!-- Antenna -->
            <rect x="15" y="1" width="2" height="4" fill="#00fff2"/>
            <circle cx="16" cy="1" r="2" fill="#ff0066"/>
            <!-- Arms -->
            <rect x="4" y="14" width="4" height="2" fill="#00fff2" class="arm-left"/>
            <rect x="24" y="14" width="4" height="2" fill="#00fff2" class="arm-right"/>
            <!-- Legs - animated -->
            <rect x="10" y="26" width="4" height="4" fill="#00fff2" class="leg-left"/>
            <rect x="18" y="26" width="4" height="4" fill="#00fff2" class="leg-right"/>
            <!-- Core glow -->
            <rect x="14" y="16" width="4" height="4" fill="#00ffff" opacity="0.8">
                <animate attributeName="opacity" values="0.4;1;0.4" dur="1s" repeatCount="indefinite"/>
            </rect>
        </svg>
    `,

    planner: `
        <svg viewBox="0 0 32 32" class="robot-svg">
            <!-- Body - blueprint style -->
            <rect x="8" y="14" width="16" height="12" fill="#0066ff"/>
            <rect x="10" y="16" width="12" height="8" fill="#001144"/>
            <!-- Head - thinking robot -->
            <rect x="9" y="4" width="14" height="12" fill="#0066ff"/>
            <rect x="11" y="6" width="10" height="8" fill="#002255"/>
            <!-- Eyes - wise -->
            <rect x="12" y="8" width="3" height="2" fill="#00ccff" class="eye-left"/>
            <rect x="17" y="8" width="3" height="2" fill="#00ccff" class="eye-right"/>
            <!-- Thinking gears -->
            <circle cx="7" cy="6" r="3" fill="#0088ff" stroke="#00ccff" stroke-width="1" class="gear">
                <animateTransform attributeName="transform" type="rotate" from="0 7 6" to="360 7 6" dur="3s" repeatCount="indefinite"/>
            </circle>
            <!-- Clipboard -->
            <rect x="20" y="18" width="8" height="10" fill="#004488" class="clipboard"/>
            <rect x="21" y="20" width="6" height="1" fill="#00ccff"/>
            <rect x="21" y="22" width="4" height="1" fill="#00ccff"/>
            <rect x="21" y="24" width="5" height="1" fill="#00ccff"/>
            <!-- Legs -->
            <rect x="10" y="26" width="4" height="4" fill="#0066ff" class="leg-left"/>
            <rect x="18" y="26" width="4" height="4" fill="#0066ff" class="leg-right"/>
        </svg>
    `,

    executor: `
        <svg viewBox="0 0 32 32" class="robot-svg">
            <!-- Body - powerful -->
            <rect x="6" y="12" width="20" height="14" fill="#ff00ff"/>
            <rect x="8" y="14" width="16" height="10" fill="#330033"/>
            <!-- Head - determined -->
            <rect x="8" y="4" width="16" height="10" fill="#ff00ff"/>
            <rect x="10" y="6" width="12" height="6" fill="#220022"/>
            <!-- Eyes - focused -->
            <rect x="11" y="7" width="4" height="3" fill="#ff66ff" class="eye-left"/>
            <rect x="17" y="7" width="4" height="3" fill="#ff66ff" class="eye-right"/>
            <!-- Visor line -->
            <rect x="10" y="8" width="12" height="1" fill="#ff00ff" opacity="0.5"/>
            <!-- Power core -->
            <rect x="13" y="16" width="6" height="6" fill="#ff00ff" class="power-core">
                <animate attributeName="fill" values="#ff00ff;#ffffff;#ff00ff" dur="0.5s" repeatCount="indefinite"/>
            </rect>
            <!-- Strong arms -->
            <rect x="2" y="13" width="4" height="6" fill="#ff00ff" class="arm-left"/>
            <rect x="26" y="13" width="4" height="6" fill="#ff00ff" class="arm-right"/>
            <!-- Tool hand -->
            <rect x="0" y="16" width="3" height="4" fill="#ff66ff"/>
            <rect x="29" y="16" width="3" height="4" fill="#ff66ff"/>
            <!-- Legs -->
            <rect x="8" y="26" width="6" height="4" fill="#ff00ff" class="leg-left"/>
            <rect x="18" y="26" width="6" height="4" fill="#ff00ff" class="leg-right"/>
        </svg>
    `,

    verifier: `
        <svg viewBox="0 0 32 32" class="robot-svg">
            <!-- Body - inspector -->
            <rect x="8" y="14" width="16" height="12" fill="#00ff88"/>
            <rect x="10" y="16" width="12" height="8" fill="#003322"/>
            <!-- Head -->
            <rect x="9" y="4" width="14" height="12" fill="#00ff88"/>
            <rect x="11" y="6" width="10" height="8" fill="#002211"/>
            <!-- Magnifying glass eye -->
            <circle cx="13" cy="9" r="3" fill="none" stroke="#00ffaa" stroke-width="2" class="eye-left"/>
            <rect x="15" y="11" width="3" height="1" fill="#00ffaa" transform="rotate(45 15 11)"/>
            <!-- Normal eye -->
            <rect x="18" y="8" width="2" height="2" fill="#00ffaa" class="eye-right"/>
            <!-- Checkmark badge -->
            <rect x="18" y="18" width="8" height="8" fill="#006644"/>
            <path d="M20 22 L22 24 L26 18" stroke="#00ff88" stroke-width="2" fill="none"/>
            <!-- Scanner beam -->
            <rect x="6" y="20" width="2" height="6" fill="#00ff88" opacity="0.6" class="scanner">
                <animate attributeName="opacity" values="0.3;1;0.3" dur="1.5s" repeatCount="indefinite"/>
            </rect>
            <!-- Legs -->
            <rect x="10" y="26" width="4" height="4" fill="#00ff88" class="leg-left"/>
            <rect x="18" y="26" width="4" height="4" fill="#00ff88" class="leg-right"/>
        </svg>
    `,

    reviewer: `
        <svg viewBox="0 0 32 32" class="robot-svg">
            <!-- Body - scholarly -->
            <rect x="8" y="14" width="16" height="12" fill="#ffff00"/>
            <rect x="10" y="16" width="12" height="8" fill="#333300"/>
            <!-- Head -->
            <rect x="9" y="4" width="14" height="12" fill="#ffff00"/>
            <rect x="11" y="6" width="10" height="8" fill="#222200"/>
            <!-- Glasses -->
            <rect x="11" y="7" width="4" height="3" fill="none" stroke="#ffffff" stroke-width="1"/>
            <rect x="17" y="7" width="4" height="3" fill="none" stroke="#ffffff" stroke-width="1"/>
            <rect x="15" y="8" width="2" height="1" fill="#ffffff"/>
            <!-- Eyes behind glasses -->
            <rect x="12" y="8" width="2" height="1" fill="#ffff88" class="eye-left"/>
            <rect x="18" y="8" width="2" height="1" fill="#ffff88" class="eye-right"/>
            <!-- Judge's gavel -->
            <rect x="24" y="12" width="6" height="3" fill="#884400" class="gavel"/>
            <rect x="26" y="15" width="2" height="6" fill="#663300"/>
            <!-- Star rating -->
            <polygon points="14,18 15,20 17,20 15.5,21.5 16,24 14,22.5 12,24 12.5,21.5 11,20 13,20" fill="#ffff00"/>
            <!-- Legs -->
            <rect x="10" y="26" width="4" height="4" fill="#ffff00" class="leg-left"/>
            <rect x="18" y="26" width="4" height="4" fill="#ffff00" class="leg-right"/>
        </svg>
    `,

    ux: `
        <svg viewBox="0 0 32 32" class="robot-svg">
            <!-- Body - creative -->
            <rect x="8" y="14" width="16" height="12" fill="#ff6b6b"/>
            <rect x="10" y="16" width="12" height="8" fill="#331111"/>
            <!-- Head - artistic -->
            <rect x="9" y="4" width="14" height="12" fill="#ff6b6b"/>
            <rect x="11" y="6" width="10" height="8" fill="#220808"/>
            <!-- Heart eyes -->
            <path d="M12 8 L13 7 L14 8 L13 10 Z" fill="#ff9999" class="eye-left"/>
            <path d="M18 8 L19 7 L20 8 L19 10 Z" fill="#ff9999" class="eye-right"/>
            <!-- Beret -->
            <ellipse cx="16" cy="4" rx="8" ry="2" fill="#ff4444"/>
            <circle cx="16" cy="2" r="2" fill="#ff4444"/>
            <!-- Paint palette -->
            <ellipse cx="6" cy="20" rx="5" ry="4" fill="#ffcccc" class="palette"/>
            <circle cx="4" cy="19" r="1.5" fill="#ff0000"/>
            <circle cx="6" cy="18" r="1.5" fill="#00ff00"/>
            <circle cx="8" cy="19" r="1.5" fill="#0000ff"/>
            <circle cx="6" cy="21" r="1.5" fill="#ffff00"/>
            <!-- Paintbrush -->
            <rect x="24" y="16" width="2" height="8" fill="#8b4513" class="brush"/>
            <rect x="23" y="14" width="4" height="3" fill="#ff6b6b"/>
            <!-- Legs -->
            <rect x="10" y="26" width="4" height="4" fill="#ff6b6b" class="leg-left"/>
            <rect x="18" y="26" width="4" height="4" fill="#ff6b6b" class="leg-right"/>
        </svg>
    `
};

// Robot agent definitions with positions (centered layout)
const ROBOT_AGENTS = [
    { id: 'orchestrator', name: 'ORCHESTRATOR', x: 50, y: 45, role: 'Koordinerar alla agenter' },
    { id: 'planner', name: 'PLANNER', x: 25, y: 20, role: 'Skapar exekveringsplaner' },
    { id: 'executor', name: 'EXECUTOR', x: 75, y: 20, role: 'Skriver och modifierar kod' },
    { id: 'verifier', name: 'VERIFIER', x: 25, y: 70, role: 'Testar och validerar' },
    { id: 'reviewer', name: 'REVIEWER', x: 75, y: 70, role: 'Granskar kodkvalitet' },
    { id: 'ux', name: 'DESIGNER', x: 50, y: 85, role: 'Skapar UI/UX design' },
];

class RobotVisualizer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.robots = new Map();
        this.activeRobot = null;
        this.speechTimeouts = new Map();
        this.walkingRobots = new Set();
        this.messageQueue = [];
        this.isProcessingQueue = false;
        // Idle behavior state
        this.idleIntervals = new Map();
        this.workingRobots = new Set();
        this.idleEnabled = true;
    }

    init() {
        console.log('RobotVisualizer.init() called, container:', this.container);
        if (!this.container) {
            console.error('Robot container not found!');
            return;
        }

        // Clear existing content
        this.container.innerHTML = '';
        this.container.classList.add('robot-arena');
        console.log('Creating', ROBOT_AGENTS.length, 'robots');

        // Create SVG for connection lines
        this.createConnectionsSVG();

        // Create robot elements
        ROBOT_AGENTS.forEach(agent => {
            const robotEl = this.createRobotElement(agent);
            this.container.appendChild(robotEl);
            this.robots.set(agent.id, {
                element: robotEl,
                data: agent,
                originalX: agent.x,
                originalY: agent.y,
                isWalking: false
            });
        });

        // Draw initial connections
        this.drawConnections();

        // Handle window resize
        window.addEventListener('resize', () => this.drawConnections());
    }

    createRobotElement(agent) {
        const robot = document.createElement('div');
        robot.className = 'robot-agent';
        robot.dataset.agent = agent.id;
        robot.style.left = `${agent.x}%`;
        robot.style.top = `${agent.y}%`;

        robot.innerHTML = `
            <div class="speech-bubble"></div>
            <div class="robot-sprite">
                ${ROBOT_SPRITES[agent.id] || ROBOT_SPRITES.orchestrator}
            </div>
            <div class="robot-name">${agent.name}</div>
            <div class="robot-provider"></div>
        `;

        // Click handler
        robot.addEventListener('click', () => {
            this.setActive(agent.id);
            if (window.addMessage) {
                window.addMessage(agent.id, agent.role);
            }
        });

        return robot;
    }

    createConnectionsSVG() {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'robot-connections');
        svg.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:1;';

        // Add gradient definition
        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        defs.innerHTML = `
            <linearGradient id="connection-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" style="stop-color:#00fff2;stop-opacity:0.2"/>
                <stop offset="100%" style="stop-color:#ff00ff;stop-opacity:0.2"/>
            </linearGradient>
            <linearGradient id="active-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" style="stop-color:#00fff2;stop-opacity:0.8"/>
                <stop offset="100%" style="stop-color:#ff00ff;stop-opacity:0.8"/>
            </linearGradient>
        `;
        svg.appendChild(defs);

        this.connectionsSVG = svg;
        this.container.appendChild(svg);
    }

    drawConnections() {
        if (!this.connectionsSVG) return;

        // Clear existing lines
        const existingLines = this.connectionsSVG.querySelectorAll('line');
        existingLines.forEach(line => line.remove());

        const orchestrator = this.robots.get('orchestrator');
        if (!orchestrator) return;

        const containerRect = this.container.getBoundingClientRect();

        // Draw lines from orchestrator to all other robots
        this.robots.forEach((robot, id) => {
            if (id === 'orchestrator') return;

            const oX = orchestrator.data.x;
            const oY = orchestrator.data.y;
            const rX = robot.data.x;
            const rY = robot.data.y;

            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', `${oX}%`);
            line.setAttribute('y1', `${oY}%`);
            line.setAttribute('x2', `${rX}%`);
            line.setAttribute('y2', `${rY}%`);
            line.setAttribute('stroke', 'url(#connection-gradient)');
            line.setAttribute('stroke-width', '2');
            line.setAttribute('stroke-dasharray', '5,5');
            line.dataset.target = id;

            this.connectionsSVG.appendChild(line);
        });
    }

    highlightConnection(fromId, toId) {
        const lines = this.connectionsSVG.querySelectorAll('line');
        lines.forEach(line => {
            if (line.dataset.target === toId || line.dataset.target === fromId) {
                line.setAttribute('stroke', 'url(#active-gradient)');
                line.setAttribute('stroke-width', '3');
                line.classList.add('active-connection');
            }
        });

        // Reset after animation
        setTimeout(() => {
            lines.forEach(line => {
                line.setAttribute('stroke', 'url(#connection-gradient)');
                line.setAttribute('stroke-width', '2');
                line.classList.remove('active-connection');
            });
        }, 2000);
    }

    getRobotColor(id) {
        const colors = {
            orchestrator: '#00fff2',
            planner: '#0066ff',
            executor: '#ff00ff',
            verifier: '#00ff88',
            reviewer: '#ffff00',
            ux: '#ff6b6b'
        };
        return colors[id] || '#00fff2';
    }

    setActive(agentId) {
        // Remove active class from all
        this.robots.forEach((robot) => {
            robot.element.classList.remove('active');
        });

        // Set new active
        this.activeRobot = agentId;
        const robot = this.robots.get(agentId);
        if (robot) {
            robot.element.classList.add('active');
        }
    }

    // Queue a communication event
    queueCommunication(fromId, toId, message) {
        this.messageQueue.push({ fromId, toId, message });
        this.processQueue();
    }

    async processQueue() {
        if (this.isProcessingQueue || this.messageQueue.length === 0) return;

        this.isProcessingQueue = true;

        while (this.messageQueue.length > 0) {
            const { fromId, toId, message } = this.messageQueue.shift();
            await this.walkAndSpeak(fromId, toId, message);
            await this.delay(500); // Small pause between communications
        }

        this.isProcessingQueue = false;
    }

    // Main communication method - robot walks to another and speaks
    async walkAndSpeak(fromId, toId, message) {
        const fromRobot = this.robots.get(fromId);
        const toRobot = this.robots.get(toId);

        if (!fromRobot || !toRobot) return;
        if (fromId === toId) {
            // Just speak in place
            this.speak(fromId, message);
            return;
        }

        // Highlight connection
        this.highlightConnection(fromId, toId);

        // Set active
        this.setActive(fromId);

        // Start walking animation
        fromRobot.element.classList.add('walking');
        fromRobot.isWalking = true;

        // Calculate position to walk to (near the target robot)
        const targetX = toRobot.data.x;
        const targetY = toRobot.data.y;
        const startX = fromRobot.originalX;
        const startY = fromRobot.originalY;

        // Walk towards target (stop at 70% of the way)
        const midX = startX + (targetX - startX) * 0.6;
        const midY = startY + (targetY - startY) * 0.6;

        // Determine walk direction for proper facing
        const direction = targetX > startX ? 'right' : 'left';
        fromRobot.element.classList.add(`facing-${direction}`);

        // Animate walk
        await this.animateWalk(fromRobot, midX, midY, 800);

        // Speak when arrived
        this.speak(fromId, message, true);

        // Wait for speech
        await this.delay(Math.min(message.length * 30, 3000) + 1000);

        // Walk back
        fromRobot.element.classList.remove(`facing-${direction}`);
        const returnDirection = startX > midX ? 'right' : 'left';
        fromRobot.element.classList.add(`facing-${returnDirection}`);

        await this.animateWalk(fromRobot, startX, startY, 600);

        // Clean up
        fromRobot.element.classList.remove('walking', 'facing-left', 'facing-right');
        fromRobot.isWalking = false;
    }

    async animateWalk(robot, targetX, targetY, duration) {
        return new Promise(resolve => {
            robot.element.style.transition = `left ${duration}ms ease-in-out, top ${duration}ms ease-in-out`;
            robot.element.style.left = `${targetX}%`;
            robot.element.style.top = `${targetY}%`;

            setTimeout(() => {
                robot.element.style.transition = '';
                resolve();
            }, duration);
        });
    }

    speak(agentId, message, persistent = false) {
        const robot = this.robots.get(agentId);
        if (!robot) return;

        // Clear any existing timeout
        if (this.speechTimeouts.has(agentId)) {
            clearTimeout(this.speechTimeouts.get(agentId));
        }

        // Set speech bubble content
        const bubble = robot.element.querySelector('.speech-bubble');
        if (bubble) {
            // Truncate long messages for display
            const displayMessage = message.length > 100 ? message.substring(0, 100) + '...' : message;
            bubble.textContent = displayMessage;
            robot.element.classList.add('speaking');

            // Auto-hide after delay (longer for persistent)
            const hideDelay = persistent ? Math.min(message.length * 30, 3000) + 500 : 4000;
            const timeout = setTimeout(() => {
                robot.element.classList.remove('speaking');
            }, hideDelay);
            this.speechTimeouts.set(agentId, timeout);
        }
    }

    // Simplified data transfer animation
    animateDataTransfer(fromId, toId) {
        const from = this.robots.get(fromId);
        const to = this.robots.get(toId);
        if (!from || !to) return;

        // Create data packet
        const packet = document.createElement('div');
        packet.className = 'data-packet';
        packet.style.setProperty('--packet-color', this.getRobotColor(fromId));
        packet.style.left = `${from.data.x}%`;
        packet.style.top = `${from.data.y}%`;

        this.container.appendChild(packet);

        // Animate to destination
        const dx = to.data.x - from.data.x;
        const dy = to.data.y - from.data.y;

        packet.animate([
            { transform: 'translate(-50%, -50%) scale(1)', opacity: 1 },
            { transform: `translate(calc(${dx}vw * 0.5 - 50%), calc(${dy}vh * 0.5 - 50%)) scale(0.5)`, opacity: 0.5 }
        ], {
            duration: 600,
            easing: 'ease-in-out'
        }).onfinish = () => packet.remove();
    }

    // Set provider label under robot
    setProvider(agentId, providerName) {
        const robot = this.robots.get(agentId);
        if (!robot) return;

        const providerEl = robot.element.querySelector('.robot-provider');
        if (providerEl) {
            providerEl.textContent = providerName;
        }
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // ============================================
    // IDLE BEHAVIOR SYSTEM - Free Robot Movement
    // ============================================

    startIdleBehavior() {
        if (!this.idleEnabled) return;

        ROBOT_AGENTS.forEach(agent => {
            this.startRobotIdle(agent.id);
        });
    }

    stopIdleBehavior() {
        this.idleIntervals.forEach((interval, id) => {
            clearInterval(interval);
        });
        this.idleIntervals.clear();
    }

    startRobotIdle(agentId) {
        const robot = this.robots.get(agentId);
        if (!robot) return;

        // Random interval between 4-10 seconds
        const interval = setInterval(() => {
            // Don't do idle actions if robot is busy
            if (robot.isWalking || this.workingRobots.has(agentId)) return;
            if (this.isProcessingQueue) return;

            // 25% chance to do an idle action
            if (Math.random() < 0.25) {
                this.performIdleAction(agentId);
            }
        }, 4000 + Math.random() * 6000);

        this.idleIntervals.set(agentId, interval);
    }

    async performIdleAction(agentId) {
        const robot = this.robots.get(agentId);
        if (!robot || robot.isWalking) return;

        const actions = ['wander', 'think', 'scan', 'look'];
        const action = actions[Math.floor(Math.random() * actions.length)];

        switch (action) {
            case 'wander':
                await this.idleWander(agentId);
                break;
            case 'think':
                this.showThinkingAnimation(agentId);
                break;
            case 'scan':
                this.showScanningAnimation(agentId);
                break;
            case 'look':
                this.showLookingAnimation(agentId);
                break;
        }
    }

    async idleWander(agentId) {
        const robot = this.robots.get(agentId);
        if (!robot || robot.isWalking) return;

        robot.isWalking = true;
        robot.element.classList.add('idle-walking');

        // Calculate a small random offset from original position
        const offsetX = (Math.random() - 0.5) * 12; // +/- 6%
        const offsetY = (Math.random() - 0.5) * 12;

        const targetX = Math.max(5, Math.min(95, robot.originalX + offsetX));
        const targetY = Math.max(5, Math.min(95, robot.originalY + offsetY));

        // Determine direction
        const direction = targetX > robot.data.x ? 'right' : 'left';
        robot.element.classList.add(`facing-${direction}`);
        robot.element.classList.add('walking');

        await this.animateWalk(robot, targetX, targetY, 1200);

        // Pause briefly at the new position
        await this.delay(800 + Math.random() * 1200);

        // Return to original position
        robot.element.classList.remove(`facing-${direction}`);
        const returnDir = robot.originalX > targetX ? 'right' : 'left';
        robot.element.classList.add(`facing-${returnDir}`);

        await this.animateWalk(robot, robot.originalX, robot.originalY, 1000);

        robot.element.classList.remove('walking', 'idle-walking', 'facing-left', 'facing-right');
        robot.isWalking = false;
    }

    showThinkingAnimation(agentId) {
        const robot = this.robots.get(agentId);
        if (!robot) return;

        robot.element.classList.add('thinking');

        // Show thought bubble with dots
        const bubble = robot.element.querySelector('.speech-bubble');
        if (bubble) {
            bubble.textContent = '...';
            robot.element.classList.add('speaking');
        }

        setTimeout(() => {
            robot.element.classList.remove('thinking', 'speaking');
        }, 2000);
    }

    showScanningAnimation(agentId) {
        const robot = this.robots.get(agentId);
        if (!robot) return;

        robot.element.classList.add('scanning');

        setTimeout(() => {
            robot.element.classList.remove('scanning');
        }, 2500);
    }

    showLookingAnimation(agentId) {
        const robot = this.robots.get(agentId);
        if (!robot) return;

        // Briefly look left then right
        robot.element.classList.add('looking');
        robot.element.classList.add('facing-left');

        setTimeout(() => {
            robot.element.classList.remove('facing-left');
            robot.element.classList.add('facing-right');
        }, 600);

        setTimeout(() => {
            robot.element.classList.remove('looking', 'facing-right');
        }, 1200);
    }

    // Set robot to "working" state (busy animation)
    setWorking(agentId, working = true) {
        const robot = this.robots.get(agentId);
        if (!robot) return;

        if (working) {
            this.workingRobots.add(agentId);
            robot.element.classList.add('working');
        } else {
            this.workingRobots.delete(agentId);
            robot.element.classList.remove('working');
        }
    }

    // Gravitate robots toward each other during collaboration
    async gravitateToward(fromId, toId, distance = 0.35) {
        const fromRobot = this.robots.get(fromId);
        const toRobot = this.robots.get(toId);

        if (!fromRobot || !toRobot) return;
        if (fromRobot.isWalking) return;

        fromRobot.isWalking = true;

        // Calculate position closer to target
        const targetX = fromRobot.originalX +
            (toRobot.originalX - fromRobot.originalX) * distance;
        const targetY = fromRobot.originalY +
            (toRobot.originalY - fromRobot.originalY) * distance;

        fromRobot.element.classList.add('walking', 'gravitating');

        const direction = targetX > fromRobot.data.x ? 'right' : 'left';
        fromRobot.element.classList.add(`facing-${direction}`);

        // Update current position
        fromRobot.data.x = targetX;
        fromRobot.data.y = targetY;

        await this.animateWalk(fromRobot, targetX, targetY, 600);

        fromRobot.element.classList.remove('walking', `facing-${direction}`);
        fromRobot.isWalking = false;
    }

    // Return robot to home position
    async returnHome(agentId) {
        const robot = this.robots.get(agentId);
        if (!robot) return;
        if (robot.isWalking) return;

        robot.isWalking = true;
        robot.element.classList.add('walking');

        const direction = robot.originalX > robot.data.x ? 'right' : 'left';
        robot.element.classList.add(`facing-${direction}`);

        // Update current position back to original
        robot.data.x = robot.originalX;
        robot.data.y = robot.originalY;

        await this.animateWalk(robot, robot.originalX, robot.originalY, 700);

        robot.element.classList.remove('walking', 'gravitating', `facing-${direction}`);
        robot.isWalking = false;
    }

    // Show collaboration between agents (multiple robots move toward each other)
    async showCollaboration(initiator, participants, topic) {
        // All participants gravitate toward the initiator
        const promises = participants.map(p => {
            if (p !== initiator) {
                return this.gravitateToward(p, initiator, 0.3);
            }
            return Promise.resolve();
        });

        await Promise.all(promises);

        // Show speech from initiator
        this.speak(initiator, topic.substring(0, 60) + '...', true);

        // Return to positions after a delay
        setTimeout(async () => {
            for (const p of participants) {
                if (p !== initiator) {
                    await this.returnHome(p);
                }
            }
        }, 3000);
    }
}

// Export for use in main app
window.RobotVisualizer = RobotVisualizer;
window.ROBOT_AGENTS = ROBOT_AGENTS;
