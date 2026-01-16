import * as vscode from 'vscode';
import { AgentFarmClient } from './client';
import { StatusProvider, AgentsProvider, HistoryProvider } from './views';

let client: AgentFarmClient;
let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext) {
    outputChannel = vscode.window.createOutputChannel('AgentFarm');
    outputChannel.appendLine('AgentFarm extension activated');

    // Get configuration
    const config = vscode.workspace.getConfiguration('agentfarm');
    const serverUrl = config.get<string>('serverUrl', 'http://localhost:8080');

    // Initialize client
    client = new AgentFarmClient(serverUrl, outputChannel);

    // Register tree data providers
    const statusProvider = new StatusProvider(client);
    const agentsProvider = new AgentsProvider(client);
    const historyProvider = new HistoryProvider(client);

    vscode.window.registerTreeDataProvider('agentfarm.status', statusProvider);
    vscode.window.registerTreeDataProvider('agentfarm.agents', agentsProvider);
    vscode.window.registerTreeDataProvider('agentfarm.history', historyProvider);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('agentfarm.runWorkflow', runWorkflow),
        vscode.commands.registerCommand('agentfarm.planTask', planTask),
        vscode.commands.registerCommand('agentfarm.reviewCode', reviewCode),
        vscode.commands.registerCommand('agentfarm.showStatus', showStatus),
        vscode.commands.registerCommand('agentfarm.openWebUI', openWebUI),
    );

    // Auto-start if configured
    if (config.get<boolean>('autoStart', false)) {
        client.connect();
    }

    outputChannel.appendLine(`Server URL: ${serverUrl}`);
}

export function deactivate() {
    if (client) {
        client.disconnect();
    }
}

async function runWorkflow() {
    const task = await vscode.window.showInputBox({
        prompt: 'Enter task description',
        placeHolder: 'e.g., Add unit tests for utils.py',
    });

    if (!task) {
        return;
    }

    // Get current file if any
    const editor = vscode.window.activeTextEditor;
    const contextFiles = editor ? [editor.document.fileName] : [];

    try {
        await client.connect();

        vscode.window.withProgress(
            {
                location: vscode.ProgressLocation.Notification,
                title: 'AgentFarm',
                cancellable: true,
            },
            async (progress, token) => {
                progress.report({ message: 'Starting workflow...' });

                const result = await client.runWorkflow(task, contextFiles, (event) => {
                    // Update progress based on events
                    if (event.type === 'step_start') {
                        progress.report({ message: event.data?.step_name || 'Working...' });
                    }
                });

                if (result.success) {
                    vscode.window.showInformationMessage(
                        `Workflow completed! ${result.summary || ''}`
                    );
                } else {
                    vscode.window.showErrorMessage(
                        `Workflow failed: ${result.error || 'Unknown error'}`
                    );
                }

                return result;
            }
        );
    } catch (error) {
        vscode.window.showErrorMessage(`AgentFarm error: ${error}`);
    }
}

async function planTask() {
    const task = await vscode.window.showInputBox({
        prompt: 'Enter task to plan',
        placeHolder: 'e.g., Implement user authentication',
    });

    if (!task) {
        return;
    }

    try {
        await client.connect();
        const plan = await client.planTask(task);

        // Show plan in output channel
        outputChannel.clear();
        outputChannel.appendLine('=== Task Plan ===');
        outputChannel.appendLine(`Task: ${task}`);
        outputChannel.appendLine('');
        outputChannel.appendLine('Steps:');

        for (const step of plan.steps || []) {
            outputChannel.appendLine(`  ${step.id}. ${step.description}`);
            if (step.dependencies?.length) {
                outputChannel.appendLine(`     Depends on: ${step.dependencies.join(', ')}`);
            }
        }

        outputChannel.show();
    } catch (error) {
        vscode.window.showErrorMessage(`Failed to create plan: ${error}`);
    }
}

async function reviewCode() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage('No active editor');
        return;
    }

    const selection = editor.selection;
    const code = editor.document.getText(selection);

    if (!code) {
        vscode.window.showWarningMessage('No code selected');
        return;
    }

    try {
        await client.connect();

        vscode.window.withProgress(
            {
                location: vscode.ProgressLocation.Notification,
                title: 'Reviewing code...',
                cancellable: false,
            },
            async () => {
                const review = await client.reviewCode(
                    [editor.document.fileName],
                    code
                );

                // Show review in output channel
                outputChannel.clear();
                outputChannel.appendLine('=== Code Review ===');
                outputChannel.appendLine(`File: ${editor.document.fileName}`);
                outputChannel.appendLine('');
                outputChannel.appendLine(review.feedback || 'No feedback');
                outputChannel.show();

                // Show diagnostics if any issues found
                if (review.issues?.length) {
                    const diagnostics: vscode.Diagnostic[] = review.issues.map(
                        (issue: any) => {
                            const range = issue.line
                                ? new vscode.Range(issue.line - 1, 0, issue.line - 1, 100)
                                : selection;

                            return new vscode.Diagnostic(
                                range,
                                issue.message,
                                issue.severity === 'error'
                                    ? vscode.DiagnosticSeverity.Error
                                    : vscode.DiagnosticSeverity.Warning
                            );
                        }
                    );

                    const collection = vscode.languages.createDiagnosticCollection('agentfarm');
                    collection.set(editor.document.uri, diagnostics);
                }

                return review;
            }
        );
    } catch (error) {
        vscode.window.showErrorMessage(`Review failed: ${error}`);
    }
}

function showStatus() {
    outputChannel.show();
    client.getStatus().then((status) => {
        outputChannel.appendLine('=== AgentFarm Status ===');
        outputChannel.appendLine(`Connected: ${status.connected}`);
        outputChannel.appendLine(`Server: ${status.serverUrl}`);
        outputChannel.appendLine(`Agents: ${status.agents?.join(', ') || 'None'}`);
    });
}

function openWebUI() {
    const config = vscode.workspace.getConfiguration('agentfarm');
    const serverUrl = config.get<string>('serverUrl', 'http://localhost:8080');
    vscode.env.openExternal(vscode.Uri.parse(serverUrl));
}
