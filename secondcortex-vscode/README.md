# SecondCortex

**Your AI-Powered Second Brain for Development Context**

SecondCortex is a VS Code extension designed to capture and resurrect your development state. It tracks your IDE activity, enforces a Semantic Firewall to protect sensitive data, and allows you to "resurrect" complex workspace setups with a single command.

## 🚀 Key Features

- **Workspace Resurrection**: Automatically restores your Git branch, stashes, open file tabs, and terminal state.
- **Intelligent Snapshotting**: Captures granular context of your work session, including open files and terminal commands.
- **Semantic Firewall**: Automatically scrubs secrets and sensitive data before context leaves your machine.
- **CLI & Chat Integration**: Trigger resurrection via the `/resurrect` chat command or the `cortex resurrect` terminal CLI.

## 🛠️ Getting Started

1. **Install** the extension from the VS Code Marketplace.
2. **Log In** via the SecondCortex sidebar icon in the Activity Bar.
3. **Capture**: Work naturally. SecondCortex captures snapshots in the background.
4. **Resurrect**: 
   - Type `/resurrect latest` in the SecondCortex Chat.
   - Or run `cortex resurrect latest` in your terminal.

## 🔒 Privacy & Security

SecondCortex is designed with a "Privacy First" approach. Our **Semantic Firewall** ensures that API keys, passwords, and other PII are redacted locally before any data is sent to the backend.

## 📖 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
