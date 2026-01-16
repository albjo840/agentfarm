import * as vscode from 'vscode';
import WebSocket from 'ws';

export interface WorkflowResult {
    success: boolean;
    summary?: string;
    error?: string;
    changed_files?: string[];
    total_tokens?: number;
}

export interface TaskPlan {
    task: string;
    steps: Array<{
        id: number;
        description: string;
        dependencies?: number[];
    }>;
}

export interface CodeReview {
    feedback?: string;
    issues?: Array<{
        line?: number;
        message: string;
        severity: 'error' | 'warning' | 'info';
    }>;
    approved: boolean;
}

export interface AgentStatus {
    name: string;
    status: 'idle' | 'working' | 'error';
    lastActivity?: string;
}

export interface ServerStatus {
    connected: boolean;
    serverUrl: string;
    agents?: string[];
    version?: string;
}

type EventCallback = (event: { type: string; data?: any }) => void;

export class AgentFarmClient {
    private ws: WebSocket | null = null;
    private serverUrl: string;
    private wsUrl: string;
    private outputChannel: vscode.OutputChannel;
    private eventListeners: EventCallback[] = [];
    private reconnectAttempts = 0;
    private maxReconnectAttempts = 5;

    constructor(serverUrl: string, outputChannel: vscode.OutputChannel) {
        this.serverUrl = serverUrl;
        this.wsUrl = serverUrl.replace(/^http/, 'ws') + '/ws';
        this.outputChannel = outputChannel;
    }

    async connect(): Promise<void> {
        if (this.ws?.readyState === WebSocket.OPEN) {
            return;
        }

        return new Promise((resolve, reject) => {
            try {
                this.ws = new WebSocket(this.wsUrl);

                this.ws.on('open', () => {
                    this.outputChannel.appendLine('Connected to AgentFarm server');
                    this.reconnectAttempts = 0;
                    resolve();
                });

                this.ws.on('message', (data) => {
                    try {
                        const event = JSON.parse(data.toString());
                        this.handleEvent(event);
                    } catch (e) {
                        this.outputChannel.appendLine(`Failed to parse message: ${e}`);
                    }
                });

                this.ws.on('close', () => {
                    this.outputChannel.appendLine('Disconnected from server');
                    this.ws = null;
                });

                this.ws.on('error', (error) => {
                    this.outputChannel.appendLine(`WebSocket error: ${error}`);
                    reject(error);
                });

            } catch (error) {
                reject(error);
            }
        });
    }

    disconnect(): void {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    private handleEvent(event: { type: string; data?: any }): void {
        this.outputChannel.appendLine(`Event: ${event.type}`);

        // Notify all listeners
        for (const listener of this.eventListeners) {
            listener(event);
        }
    }

    addEventListener(callback: EventCallback): void {
        this.eventListeners.push(callback);
    }

    removeEventListener(callback: EventCallback): void {
        const index = this.eventListeners.indexOf(callback);
        if (index > -1) {
            this.eventListeners.splice(index, 1);
        }
    }

    async runWorkflow(
        task: string,
        contextFiles: string[] = [],
        onEvent?: EventCallback
    ): Promise<WorkflowResult> {
        if (onEvent) {
            this.addEventListener(onEvent);
        }

        try {
            const response = await fetch(`${this.serverUrl}/api/workflow`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task,
                    context_files: contextFiles,
                }),
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            return await response.json();
        } finally {
            if (onEvent) {
                this.removeEventListener(onEvent);
            }
        }
    }

    async planTask(task: string): Promise<TaskPlan> {
        const response = await fetch(`${this.serverUrl}/api/plan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task }),
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        return await response.json();
    }

    async reviewCode(files: string[], diff?: string): Promise<CodeReview> {
        const response = await fetch(`${this.serverUrl}/api/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                changed_files: files,
                diff,
            }),
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        return await response.json();
    }

    async getStatus(): Promise<ServerStatus> {
        try {
            const response = await fetch(`${this.serverUrl}/api/status`);

            if (!response.ok) {
                return {
                    connected: false,
                    serverUrl: this.serverUrl,
                };
            }

            const data = await response.json();
            return {
                connected: true,
                serverUrl: this.serverUrl,
                agents: data.agents,
                version: data.version,
            };
        } catch {
            return {
                connected: false,
                serverUrl: this.serverUrl,
            };
        }
    }

    async getAgents(): Promise<AgentStatus[]> {
        try {
            const response = await fetch(`${this.serverUrl}/api/agents`);
            if (!response.ok) {
                return [];
            }
            return await response.json();
        } catch {
            return [];
        }
    }

    async getHistory(limit = 10): Promise<any[]> {
        try {
            const response = await fetch(`${this.serverUrl}/api/history?limit=${limit}`);
            if (!response.ok) {
                return [];
            }
            return await response.json();
        } catch {
            return [];
        }
    }
}
