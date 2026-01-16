# AgentFarm VS Code Extension

Multi-agent AI orchestration for code tasks, directly in VS Code.

## Features

- **Run Workflow** - Execute PLAN → EXECUTE → VERIFY → REVIEW workflow
- **Plan Task** - Break down a task into executable steps
- **Review Code** - Get AI-powered code review on selected code
- **Real-time Status** - See agent status in the sidebar
- **WebSocket Events** - Live updates from the AgentFarm server

## Installation

### From VSIX (Local)

```bash
cd vscode-extension
npm install
npm run compile
vsce package  # Creates agentfarm-0.1.0.vsix
code --install-extension agentfarm-0.1.0.vsix
```

### From Source

1. Clone the repository
2. Open `vscode-extension` folder in VS Code
3. Press F5 to run in Extension Development Host

## Requirements

- AgentFarm server running (`agentfarm web`)
- Node.js 18+

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `agentfarm.serverUrl` | `http://localhost:8080` | AgentFarm server URL |
| `agentfarm.autoStart` | `false` | Auto-connect on VS Code startup |
| `agentfarm.showNotifications` | `true` | Show workflow notifications |

## Commands

| Command | Description |
|---------|-------------|
| `AgentFarm: Run Workflow` | Run full agent workflow on a task |
| `AgentFarm: Plan Task` | Create execution plan for a task |
| `AgentFarm: Review Selected Code` | Review highlighted code |
| `AgentFarm: Show Status` | Show connection status |
| `AgentFarm: Open Web UI` | Open web interface in browser |

## Sidebar Views

- **Status** - Connection status and server info
- **Agents** - Current agent states (Planner, Executor, etc.)
- **History** - Recent workflow executions

## Usage

### Run a Workflow

1. Open Command Palette (Ctrl+Shift+P)
2. Type "AgentFarm: Run Workflow"
3. Enter your task description
4. Watch progress in the notification

### Review Code

1. Select code in the editor
2. Right-click → "AgentFarm: Review Selected Code"
3. View feedback in Output panel
4. See diagnostics for any issues

## Development

```bash
# Install dependencies
npm install

# Compile TypeScript
npm run compile

# Watch mode
npm run watch

# Run linter
npm run lint

# Package extension
vsce package
```

## API Endpoints Used

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workflow` | POST | Start workflow |
| `/api/plan` | POST | Create task plan |
| `/api/review` | POST | Review code |
| `/api/status` | GET | Server status |
| `/api/agents` | GET | Agent states |
| `/api/history` | GET | Workflow history |
| `/ws` | WebSocket | Real-time events |

## Troubleshooting

### Cannot connect to server

1. Ensure AgentFarm is running: `agentfarm web`
2. Check server URL in settings
3. Verify firewall allows port 8080

### Commands not working

1. Check Output panel for errors
2. Ensure server is responding: `curl http://localhost:8080/api/status`

## License

MIT
