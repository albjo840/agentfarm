/**
 * Pixel Art Robot Sprites
 * SVG-based robots for AgentFarm visualization
 */

// Robot SVG templates - pixel art style
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
            <rect x="4" y="14" width="4" height="2" fill="#00fff2"/>
            <rect x="24" y="14" width="4" height="2" fill="#00fff2"/>
            <!-- Legs -->
            <rect x="10" y="26" width="4" height="4" fill="#00fff2"/>
            <rect x="18" y="26" width="4" height="4" fill="#00fff2"/>
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
            <rect x="12" y="8" width="3" height="2" fill="#00ccff"/>
            <rect x="17" y="8" width="3" height="2" fill="#00ccff"/>
            <!-- Thinking gears -->
            <circle cx="7" cy="6" r="3" fill="#0088ff" stroke="#00ccff" stroke-width="1">
                <animateTransform attributeName="transform" type="rotate" from="0 7 6" to="360 7 6" dur="3s" repeatCount="indefinite"/>
            </circle>
            <!-- Clipboard -->
            <rect x="20" y="18" width="8" height="10" fill="#004488"/>
            <rect x="21" y="20" width="6" height="1" fill="#00ccff"/>
            <rect x="21" y="22" width="4" height="1" fill="#00ccff"/>
            <rect x="21" y="24" width="5" height="1" fill="#00ccff"/>
            <!-- Legs -->
            <rect x="10" y="26" width="4" height="4" fill="#0066ff"/>
            <rect x="18" y="26" width="4" height="4" fill="#0066ff"/>
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
            <rect x="11" y="7" width="4" height="3" fill="#ff66ff"/>
            <rect x="17" y="7" width="4" height="3" fill="#ff66ff"/>
            <!-- Visor line -->
            <rect x="10" y="8" width="12" height="1" fill="#ff00ff" opacity="0.5"/>
            <!-- Power core -->
            <rect x="13" y="16" width="6" height="6" fill="#ff00ff">
                <animate attributeName="fill" values="#ff00ff;#ffffff;#ff00ff" dur="0.5s" repeatCount="indefinite"/>
            </rect>
            <!-- Strong arms -->
            <rect x="2" y="13" width="4" height="6" fill="#ff00ff"/>
            <rect x="26" y="13" width="4" height="6" fill="#ff00ff"/>
            <!-- Tool hand -->
            <rect x="0" y="16" width="3" height="4" fill="#ff66ff"/>
            <rect x="29" y="16" width="3" height="4" fill="#ff66ff"/>
            <!-- Legs -->
            <rect x="8" y="26" width="6" height="4" fill="#ff00ff"/>
            <rect x="18" y="26" width="6" height="4" fill="#ff00ff"/>
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
            <circle cx="13" cy="9" r="3" fill="none" stroke="#00ffaa" stroke-width="2"/>
            <rect x="15" y="11" width="3" height="1" fill="#00ffaa" transform="rotate(45 15 11)"/>
            <!-- Normal eye -->
            <rect x="18" y="8" width="2" height="2" fill="#00ffaa"/>
            <!-- Checkmark badge -->
            <rect x="18" y="18" width="8" height="8" fill="#006644"/>
            <path d="M20 22 L22 24 L26 18" stroke="#00ff88" stroke-width="2" fill="none"/>
            <!-- Scanner beam -->
            <rect x="6" y="20" width="2" height="6" fill="#00ff88" opacity="0.6">
                <animate attributeName="opacity" values="0.3;1;0.3" dur="1.5s" repeatCount="indefinite"/>
            </rect>
            <!-- Legs -->
            <rect x="10" y="26" width="4" height="4" fill="#00ff88"/>
            <rect x="18" y="26" width="4" height="4" fill="#00ff88"/>
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
            <rect x="12" y="8" width="2" height="1" fill="#ffff88"/>
            <rect x="18" y="8" width="2" height="1" fill="#ffff88"/>
            <!-- Judge's gavel -->
            <rect x="24" y="12" width="6" height="3" fill="#884400"/>
            <rect x="26" y="15" width="2" height="6" fill="#663300"/>
            <!-- Star rating -->
            <polygon points="14,18 15,20 17,20 15.5,21.5 16,24 14,22.5 12,24 12.5,21.5 11,20 13,20" fill="#ffff00"/>
            <!-- Legs -->
            <rect x="10" y="26" width="4" height="4" fill="#ffff00"/>
            <rect x="18" y="26" width="4" height="4" fill="#ffff00"/>
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
            <path d="M12 8 L13 7 L14 8 L13 10 Z" fill="#ff9999"/>
            <path d="M18 8 L19 7 L20 8 L19 10 Z" fill="#ff9999"/>
            <!-- Beret -->
            <ellipse cx="16" cy="4" rx="8" ry="2" fill="#ff4444"/>
            <circle cx="16" cy="2" r="2" fill="#ff4444"/>
            <!-- Paint palette -->
            <ellipse cx="6" cy="20" rx="5" ry="4" fill="#ffcccc"/>
            <circle cx="4" cy="19" r="1.5" fill="#ff0000"/>
            <circle cx="6" cy="18" r="1.5" fill="#00ff00"/>
            <circle cx="8" cy="19" r="1.5" fill="#0000ff"/>
            <circle cx="6" cy="21" r="1.5" fill="#ffff00"/>
            <!-- Paintbrush -->
            <rect x="24" y="16" width="2" height="8" fill="#8b4513"/>
            <rect x="23" y="14" width="4" height="3" fill="#ff6b6b"/>
            <!-- Legs -->
            <rect x="10" y="26" width="4" height="4" fill="#ff6b6b"/>
            <rect x="18" y="26" width="4" height="4" fill="#ff6b6b"/>
        </svg>
    `
};

// Robot agent definitions with positions
const ROBOT_AGENTS = [
    { id: 'orchestrator', name: 'THE ORCHESTRATOR', x: 50, y: 45, role: 'Coordinates all agents' },
    { id: 'planner', name: 'THE PLANNER', x: 20, y: 25, role: 'Creates execution plans' },
    { id: 'executor', name: 'THE EXECUTOR', x: 80, y: 25, role: 'Writes and modifies code' },
    { id: 'verifier', name: 'THE VERIFIER', x: 20, y: 70, role: 'Tests and validates' },
    { id: 'reviewer', name: 'THE REVIEWER', x: 80, y: 70, role: 'Reviews code quality' },
    { id: 'ux', name: 'THE DESIGNER', x: 50, y: 85, role: 'Creates UI/UX designs' },
];

class RobotVisualizer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.robots = new Map();
        this.activeRobot = null;
        this.speechTimeouts = new Map();
    }

    init() {
        if (!this.container) return;

        // Clear existing content
        this.container.innerHTML = '';
        this.container.classList.add('robot-arena');

        // Create SVG for connection lines
        this.createConnectionsSVG();

        // Create robot elements
        ROBOT_AGENTS.forEach(agent => {
            const robotEl = this.createRobotElement(agent);
            this.container.appendChild(robotEl);
            this.robots.set(agent.id, { element: robotEl, data: agent });
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
        robot.style.transform = 'translate(-50%, -50%)';

        robot.innerHTML = `
            <div class="speech-bubble"></div>
            <div class="robot-sprite">
                ${ROBOT_SPRITES[agent.id] || ROBOT_SPRITES.orchestrator}
            </div>
            <div class="robot-name">${agent.name}</div>
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
                <stop offset="0%" style="stop-color:#00fff2;stop-opacity:0.3"/>
                <stop offset="100%" style="stop-color:#ff00ff;stop-opacity:0.3"/>
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

        const oRect = orchestrator.element.getBoundingClientRect();
        const containerRect = this.container.getBoundingClientRect();

        const ox = oRect.left + oRect.width / 2 - containerRect.left;
        const oy = oRect.top + oRect.height / 2 - containerRect.top;

        // Draw lines to all other robots
        this.robots.forEach((robot, id) => {
            if (id === 'orchestrator') return;

            const rect = robot.element.getBoundingClientRect();
            const x = rect.left + rect.width / 2 - containerRect.left;
            const y = rect.top + rect.height / 2 - containerRect.top;

            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', ox);
            line.setAttribute('y1', oy);
            line.setAttribute('x2', x);
            line.setAttribute('y2', y);
            line.setAttribute('stroke', 'url(#connection-gradient)');
            line.setAttribute('stroke-width', '2');
            line.setAttribute('stroke-dasharray', '5,5');

            // Animate when this robot is active
            if (id === this.activeRobot) {
                line.style.stroke = this.getRobotColor(id);
                line.style.strokeWidth = '3';
                line.style.strokeOpacity = '0.8';
            }

            this.connectionsSVG.appendChild(line);
        });
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

        // Redraw connections
        this.drawConnections();
    }

    speak(agentId, message) {
        const robot = this.robots.get(agentId);
        if (!robot) return;

        // Clear any existing timeout
        if (this.speechTimeouts.has(agentId)) {
            clearTimeout(this.speechTimeouts.get(agentId));
        }

        // Set speech bubble content
        const bubble = robot.element.querySelector('.speech-bubble');
        if (bubble) {
            // Truncate long messages
            const displayMessage = message.length > 80 ? message.substring(0, 80) + '...' : message;
            bubble.textContent = displayMessage;
            robot.element.classList.add('speaking');

            // Auto-hide after delay
            const timeout = setTimeout(() => {
                robot.element.classList.remove('speaking');
            }, 4000);
            this.speechTimeouts.set(agentId, timeout);
        }
    }

    animateDataTransfer(fromId, toId) {
        const from = this.robots.get(fromId);
        const to = this.robots.get(toId);
        if (!from || !to) return;

        const fromRect = from.element.getBoundingClientRect();
        const toRect = to.element.getBoundingClientRect();
        const containerRect = this.container.getBoundingClientRect();

        const packet = document.createElement('div');
        packet.className = 'data-packet';
        packet.style.setProperty('--packet-color', this.getRobotColor(fromId));
        packet.style.left = `${fromRect.left + fromRect.width / 2 - containerRect.left}px`;
        packet.style.top = `${fromRect.top + fromRect.height / 2 - containerRect.top}px`;

        this.container.appendChild(packet);

        // Animate to destination
        const dx = toRect.left - fromRect.left;
        const dy = toRect.top - fromRect.top;

        packet.animate([
            { transform: 'translate(0, 0) scale(1)', opacity: 1 },
            { transform: `translate(${dx}px, ${dy}px) scale(0.5)`, opacity: 0.5 }
        ], {
            duration: 800,
            easing: 'ease-in-out'
        }).onfinish = () => packet.remove();
    }
}

// Export for use in main app
window.RobotVisualizer = RobotVisualizer;
window.ROBOT_AGENTS = ROBOT_AGENTS;
