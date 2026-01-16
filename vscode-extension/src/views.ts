import * as vscode from 'vscode';
import { AgentFarmClient } from './client';

// Status tree item
class StatusItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly value: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState = vscode.TreeItemCollapsibleState.None
    ) {
        super(label, collapsibleState);
        this.description = value;
    }
}

// Status provider
export class StatusProvider implements vscode.TreeDataProvider<StatusItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<StatusItem | undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    constructor(private client: AgentFarmClient) {
        // Refresh every 10 seconds
        setInterval(() => this.refresh(), 10000);
    }

    refresh(): void {
        this._onDidChangeTreeData.fire(undefined);
    }

    getTreeItem(element: StatusItem): vscode.TreeItem {
        return element;
    }

    async getChildren(): Promise<StatusItem[]> {
        const status = await this.client.getStatus();

        return [
            new StatusItem(
                'Connection',
                status.connected ? 'Connected' : 'Disconnected'
            ),
            new StatusItem('Server', status.serverUrl),
            new StatusItem('Version', status.version || 'Unknown'),
        ];
    }
}

// Agent tree item
class AgentItem extends vscode.TreeItem {
    constructor(
        public readonly name: string,
        public readonly status: string,
        public readonly lastActivity?: string
    ) {
        super(name, vscode.TreeItemCollapsibleState.None);

        this.description = status;
        this.tooltip = lastActivity ? `Last activity: ${lastActivity}` : undefined;

        // Set icon based on status
        if (status === 'working') {
            this.iconPath = new vscode.ThemeIcon('sync~spin');
        } else if (status === 'error') {
            this.iconPath = new vscode.ThemeIcon('error');
        } else {
            this.iconPath = new vscode.ThemeIcon('circle-outline');
        }
    }
}

// Agents provider
export class AgentsProvider implements vscode.TreeDataProvider<AgentItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<AgentItem | undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    constructor(private client: AgentFarmClient) {
        // Refresh every 5 seconds
        setInterval(() => this.refresh(), 5000);
    }

    refresh(): void {
        this._onDidChangeTreeData.fire(undefined);
    }

    getTreeItem(element: AgentItem): vscode.TreeItem {
        return element;
    }

    async getChildren(): Promise<AgentItem[]> {
        const agents = await this.client.getAgents();

        if (agents.length === 0) {
            // Return default agents
            return [
                new AgentItem('Planner', 'idle'),
                new AgentItem('Executor', 'idle'),
                new AgentItem('Verifier', 'idle'),
                new AgentItem('Reviewer', 'idle'),
                new AgentItem('UX Designer', 'idle'),
            ];
        }

        return agents.map(
            (a) => new AgentItem(a.name, a.status, a.lastActivity)
        );
    }
}

// History tree item
class HistoryItem extends vscode.TreeItem {
    constructor(
        public readonly task: string,
        public readonly timestamp: string,
        public readonly success: boolean
    ) {
        super(task, vscode.TreeItemCollapsibleState.None);

        this.description = timestamp;
        this.iconPath = new vscode.ThemeIcon(
            success ? 'check' : 'x'
        );
    }
}

// History provider
export class HistoryProvider implements vscode.TreeDataProvider<HistoryItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<HistoryItem | undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    constructor(private client: AgentFarmClient) {}

    refresh(): void {
        this._onDidChangeTreeData.fire(undefined);
    }

    getTreeItem(element: HistoryItem): vscode.TreeItem {
        return element;
    }

    async getChildren(): Promise<HistoryItem[]> {
        const history = await this.client.getHistory(10);

        return history.map(
            (item) =>
                new HistoryItem(
                    item.task || 'Unknown task',
                    item.timestamp || '',
                    item.success ?? false
                )
        );
    }
}
