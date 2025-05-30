
# main

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Game Client   │    │  Game Manager   │    │   MCP Client    │
│                 │────│                 │────│                 │
│ - UI/Interface  │    │ - Game Logic    │    │ - Tool Calls    │
│ - User Input    │    │ - State Mgmt    │    │ - Session Mgmt  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                       │
                                │                       │
                       ┌─────────────────┐    ┌─────────────────┐
                       │ Tool Handler    │    │   MCP Server    │
                       │   Registry      │    │                 │
                       │ - Tool Routing  │    │ - Wikipedia API │
                       │ - Result Parse  │    │ - Tool Impl     │
                       └─────────────────┘    └─────────────────┘
```

```mermaid
sequenceDiagram
    participant User
    participant GameManager
    participant MCPClient
    participant MCPServer
    participant LM

    User->>GameManager: Start New Game
    GameManager->>MCPClient: Get Initial Page Links
    MCPClient->>MCPServer: navigate_to_page
    MCPServer-->>MCPClient: Return Links
    MCPClient-->>GameManager: Return Links
    
    loop Until Target Reached or Error
        GameManager->>LM: Send Prompt
        LM-->>GameManager: Choose Next Page
        GameManager->>MCPClient: Get New Page Links
        MCPClient->>MCPServer: navigate_to_page
        MCPServer-->>MCPClient: Return Links
        MCPClient-->>GameManager: Return Links
    end
    GameManager-->>User: Game Complete
```

# application = client (all communication is JSON-RPC)

```mermaid
sequenceDiagram
    participant MCPServer as MCP Server
    participant UserApp as User Application (MCP Client)
    participant AbsLayer as Provider-Agnostic LLM Layer
    participant Adapter as LLM Provider Adapter
    participant LLM as Language Model

    UserApp->>+MCPServer: tools/list (Discover Tools)
    MCPServer-->>-UserApp: Tool Definitions

    UserApp->>+AbsLayer: Process Prompt (with Tool Definitions)
    AbsLayer->>+Adapter: Format Tools & Send Prompt
    Adapter->>+LLM: Prompt + Provider-Specific Tools
    LLM-->>-Adapter: Request to Call Tool (Provider-Specific Format)
    Adapter->>-AbsLayer: Standardized Tool Call Request
    AbsLayer-->>-UserApp: Standardized Tool Call Request (ToolName, Args)

    UserApp->>+MCPServer: tools/call (ToolName, Args)
    MCPServer-->>-UserApp: Tool Result

    UserApp->>+AbsLayer: Provide Tool Result
    AbsLayer->>+Adapter: Format Tool Result
    Adapter->>+LLM: Provider-Specific Tool Result
    LLM-->>-Adapter: Final Response
    Adapter-->>-AbsLayer: Final Response
    AbsLayer-->>-UserApp: Final Response
```