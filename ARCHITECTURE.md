# Wikipedia Arena - Architecture Overview

## System Architecture

```mermaid
graph TD
    GM[Game Manager] --> CR[Capability Registry]
    CR --> NA[Navigation Adapter] 
    NA --> MC[MCP Client]
    MC --> MS[MCP Server]
    
    GM --> LM[Language Models]
    LM --> GM
    
    NA --> NC[Navigation Capability]
    NC --> NA
    
    MS --> WA[Wikipedia API]
    
    subgraph "Capability-Based Core"
        CR
        NA
        NC
    end
    
    subgraph "MCP Layer"
        MC
        MS
    end
    
    subgraph "External APIs"
        WA
    end
```

## Component Flow

```mermaid
sequenceDiagram
    participant LM as Language Model
    participant GM as Game Manager
    participant CR as Capability Registry  
    participant NA as Navigation Adapter
    participant MC as MCP Client
    participant MS as MCP Server

    GM->>CR: Initialize capabilities
    CR->>NA: Discover compatible tools
    NA->>MC: List available tools
    MC->>MS: tools/list
    MS-->>MC: Tool definitions
    MC-->>NA: Available tools
    NA-->>CR: Compatible tools found
    CR-->>GM: Navigation capability ready

    loop Game Turns
        GM->>LM: Generate move (current page, tools)
        LM-->>GM: Tool call request
        GM->>CR: Get navigation capability
        CR-->>GM: Navigation capability
        GM->>NA: Navigate to page
        NA->>MC: Call tool (via adapter)
        MC->>MS: tools/call
        MS-->>MC: Page data + links
        MC-->>NA: Tool result
        NA-->>GM: Navigation result
    end
```

## Key Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Tool Agnosticism** | Adapters map any compatible tool to capabilities |
| **Schema-First** | Interface definitions drive compatibility |
| **Graceful Degradation** | Works with partial tool sets |
| **Separation of Concerns** | Game logic independent of tool implementation |
| **Composability** | Mix and match capabilities dynamically |

## File Structure

```
wiki_arena/
├── capabilities/                 # Capability interfaces
│   ├── navigation.py            # INavigationCapability + NavigationResult
│   └── __init__.py
├── adapters/                    # Tool-to-capability mapping
│   ├── base.py                  # CapabilityAdapter + ToolSignature
│   ├── navigation.py            # NavigationAdapter + NavigationCapabilityImpl
│   └── __init__.py
├── services/                    # Core services
│   ├── capability_registry.py   # CapabilityRegistry
│   └── __init__.py
├── game/                        # Game logic
│   ├── game_manager.py          # GameManager (capability-based)
│   └── __init__.py
├── mcp_client/                  # MCP communication
│   ├── client.py                # MCPClient
│   └── __init__.py
├── language_models/             # LLM providers
│   ├── language_model.py        # Base class
│   ├── anthropic_model.py       # Anthropic implementation
│   ├── openai_model.py          # OpenAI implementation
│   └── random_model.py          # Random implementation
└── data_models/                 # Data structures
    ├── game_models.py           # Game state, moves, results
    └── __init__.py

mcp_server/
└── server.py                    # Wikipedia API server

tests/                           # Comprehensive test suite
├── test_capabilities.py         # Capability interfaces
├── test_adapters.py             # Adapter functionality  
├── test_registry.py             # Registry operations
└── __init__.py
```

## Capability Registry Flow

```mermaid
graph LR
    subgraph "Registration Phase"
        A[Default Adapters] --> B[Register with Registry]
    end
    
    subgraph "Discovery Phase" 
        C[List MCP Tools] --> D[Check Compatibility]
        D --> E[Create Capability Instances]
    end
    
    subgraph "Runtime Phase"
        F[Get Capability] --> G[Use Interface Methods]
        G --> H[Adapter Routes to Tools]
    end
    
    B --> C
    E --> F
```

## Tool Compatibility Matrix

```mermaid
graph TD
    subgraph "MCP Tools"
        T1[navigate]
        T2[navigate_to_page] 
        T3[search_wikipedia]
        T4[get_page_links]
    end
    
    subgraph "Navigation Capability"
        NC[INavigationCapability]
    end
    
    subgraph "Future Capabilities"
        SC[ISearchCapability]
        CC[IComputerUseCapability]
    end
    
    T1 -.-> NC
    T2 -.-> NC
    T3 -.-> SC
    T4 -.-> NC
    
    style NC fill:#6b8b47
    style SC fill:#d68910
    style CC fill:#8b4b4b
```

## Migration Phases

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | ✅ Complete | Capability architecture implementation |
| **Phase 2** | ✅ Complete | GameManager integration |
| **Phase 3** | ✅ Complete | Legacy code removal |
| **Phase 4** | 🎯 Ready | Advanced capabilities (computer-use, search) |

## Game Manager Error Handling Flow

### Error Handling Overview

```mermaid
graph TD
    SG[start_game] --> SGE{Error?}
    SGE -->|No| PT[play_turn]
    SGE -->|Yes| SGERR[Game Status: ERROR<br/>No moves created]
    
    PT --> CE{Critical<br/>Error?}
    CE -->|Yes| CEERR[Game Status: ERROR<br/>Error message only]
    CE -->|No| MR[Get Model Response]
    
    MR --> MRE{Model<br/>Error?}
    MRE -->|Yes| MRERR[Create Error Move<br/>Game Status: LOST_INVALID_MOVE]
    MRE -->|No| VR[Validate Response]
    
    VR --> VRE{Validation<br/>Error?}
    VRE -->|Yes| VRERR[Create Error Move<br/>Game Status: LOST_INVALID_MOVE]
    VRE -->|No| NAV[Attempt Navigation]
    
    NAV --> NAVE{Navigation<br/>Error?}
    NAVE -->|Yes| NAVERR[Create Error Move<br/>Game Status: ERROR]
    NAVE -->|No| SUCCESS[Create Success Move<br/>Update Game State]
    
    SUCCESS --> WIN{Target<br/>Reached?}
    WIN -->|Yes| WINGAME[Game Status: WON]
    WIN -->|No| MAXSTEP{Max Steps<br/>Reached?}
    MAXSTEP -->|Yes| LOSEGAME[Game Status: LOST_MAX_STEPS]
    MAXSTEP -->|No| PT
    
    style SGERR fill:#8b4b4b
    style CEERR fill:#8b4b4b
    style MRERR fill:#b8860b
    style VRERR fill:#b8860b
    style NAVERR fill:#8b4b4b
    style SUCCESS fill:#6b8b47
    style WINGAME fill:#2e7d32
    style LOSEGAME fill:#d68910
```

### Error Categories and Handling

```mermaid
graph TD
    subgraph "Model Errors"
        ME1[MODEL_NO_TOOL_CALL<br/>Model didn't provide tool call]
        ME2[MODEL_INVALID_TOOL<br/>Tool doesn't exist]
        ME3[MODEL_INVALID_LINK<br/>Link not on current page]
        ME4[MODEL_GENERATION_ERROR<br/>Model threw exception]
    end
    
    subgraph "Provider Infrastructure Errors"
        PE1[PROVIDER_RATE_LIMIT<br/>API rate limiting]
        PE2[PROVIDER_TIMEOUT<br/>Request timeout]
        PE3[PROVIDER_API_ERROR<br/>HTTP 5xx errors]
    end
    
    subgraph "Application Errors"
        AE1[APP_CAPABILITY_ERROR<br/>Navigation unavailable]
        AE2[APP_NAVIGATION_ERROR<br/>Navigation failed]
        AE3[APP_UNKNOWN_ERROR<br/>Unexpected exceptions]
    end
    
    subgraph "Error Handling Strategy"
        EHS1[Create Move with Error<br/>Game Status: LOST_INVALID_MOVE]
        EHS2[Create Move with Error<br/>Game Status: ERROR]
        EHS3[No Move Created<br/>Game Status: ERROR]
    end
    
    ME1 --> EHS1
    ME2 --> EHS1
    ME3 --> EHS1
    ME4 --> EHS2
    
    PE1 --> EHS2
    PE2 --> EHS2
    PE3 --> EHS2
    
    AE1 --> EHS3
    AE2 --> EHS2
    AE3 --> EHS2
    
    style ME1 fill:#b8860b
    style ME2 fill:#b8860b
    style ME3 fill:#b8860b
    style ME4 fill:#8b4b4b
    style PE1 fill:#8b4b4b
    style PE2 fill:#8b4b4b
    style PE3 fill:#8b4b4b
    style AE1 fill:#8b4b4b
    style AE2 fill:#8b4b4b
    style AE3 fill:#8b4b4b
```

### Detailed Error Points

| **Phase** | **Error Point** | **Error Type** | **Handling** | **Game Status** | **Move Created?** |
|-----------|----------------|----------------|--------------|-----------------|-------------------|
| **start_game** | Language model init fails | APP_UNKNOWN_ERROR | Set error_message | ERROR | ❌ |
| **start_game** | Capability registry fails | APP_CAPABILITY_ERROR | Set error_message | ERROR | ❌ |
| **start_game** | Navigation capability missing | APP_CAPABILITY_ERROR | Set error_message | ERROR | ❌ |
| **start_game** | Initial page navigation fails | APP_NAVIGATION_ERROR | Set error_message | ERROR | ❌ |
| **play_turn** | No language model | - | Set error_message | ERROR | ❌ |
| **play_turn** | No navigation capability | - | Set error_message | ERROR | ❌ |
| **play_turn** | Model generation fails (rate limit) | PROVIDER_RATE_LIMIT | Create error move | ERROR | ✅ |
| **play_turn** | Model generation fails (timeout) | PROVIDER_TIMEOUT | Create error move | ERROR | ✅ |
| **play_turn** | Model generation fails (API error) | PROVIDER_API_ERROR | Create error move | ERROR | ✅ |
| **play_turn** | Model generation fails (other) | MODEL_GENERATION_ERROR | Create error move | ERROR | ✅ |
| **play_turn** | No tool call in response | MODEL_NO_TOOL_CALL | Create error move | LOST_INVALID_MOVE | ✅ |
| **play_turn** | Tool doesn't exist | MODEL_INVALID_TOOL | Create error move | LOST_INVALID_MOVE | ✅ |
| **play_turn** | Empty tool arguments | MODEL_INVALID_TOOL | Create error move | LOST_INVALID_MOVE | ✅ |
| **play_turn** | Link not on current page | MODEL_INVALID_LINK | Create error move | LOST_INVALID_MOVE | ✅ |
| **play_turn** | Navigation execution fails | APP_NAVIGATION_ERROR | Create error move | ERROR | ✅ |
| **play_turn** | Unexpected exception | APP_UNKNOWN_ERROR | Create error move | ERROR | ✅ |


### Error Metadata Examples

```json
{
  "MODEL_INVALID_LINK": {
    "requested_page": "Machine Learning",
    "current_page": "Artificial Intelligence", 
    "is_target_page": false,
    "available_links_count": 156,
    "tool_call": {
      "name": "navigate",
      "arguments": {"page": "Machine Learning"}
    }
  },
  "PROVIDER_RATE_LIMIT": {
    "exception_type": "RateLimitError",
    "step": 3,
    "has_tool_call_request": false,
    "provider": "anthropic"
  },
  "APP_NAVIGATION_ERROR": {
    "target_page": "Philosophy",
    "nav_error": "Page not found",
    "navigation_capability": "text_based"
  }
}
```

## Data Model Relationships

```mermaid
erDiagram
    GameState ||--|| GameConfig : contains
    GameState ||--o{ Move : tracks
    GameState ||--|| Page : "current page"
    
    Move ||--|| Page : "from page"
    Move ||--o| Page : "to page"
    
    NavigationResult ||--o| Page : contains
    NavigationResult ||--|| NavigationStatus : has
    
    CapabilityRegistry ||--o{ CapabilityAdapter : manages
    CapabilityAdapter ||--o{ Tool : "maps to"
```

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Test Coverage** | 29/29 tests pass | Full capability stack tested |
| **Tool Discovery** | ~100ms | Cached after initialization |
| **Page Navigation** | ~1-2s | Depends on Wikipedia API |
| **Link Extraction** | 500-2000 links | Automatic pagination |
| **Memory Usage** | Low | Stateless capability design |

## Extension Points

```mermaid
graph TD
    subgraph "Current Capabilities"
        NC[Navigation]
    end
    
    subgraph "Planned Extensions"
        SC[Search & Discovery]
        CU[Computer Use]
        AN[Analytics]
        ML[Multi-Language]
    end
    
    subgraph "Integration Layer"
        CR[Capability Registry]
        AD[Adapter System]
    end
    
    NC --> CR
    SC --> CR
    CU --> CR
    AN --> CR
    ML --> CR
    
    CR --> AD
```

## Tool Parameter Mapping

| Language Model Tool Call | Adapter Mapping | MCP Server Tool |
|--------------------------|------------------|-----------------|
| `navigate_to_page(page_title="X")` | `page_title` → `page` | `navigate(page="X")` |
| `navigate(page="X")` | Direct mapping | `navigate(page="X")` |
| `search(query="X")` | Future mapping | `search_wikipedia(query="X")` |

## Error Handling Strategy

```mermaid
graph TD
    A[Tool Call Request] --> B{Capability Available?}
    B -->|No| C[Graceful Degradation]
    B -->|Yes| D{Tool Compatible?}
    D -->|No| E[Alternative Tool Search]
    D -->|Yes| F[Execute Tool Call]
    F --> G{Tool Success?}
    G -->|No| H[NavigationResult.error]
    G -->|Yes| I[NavigationResult.success]
    
    C --> J[Game State Update]
    E --> D
    H --> J
    I --> J
```

## Testing Strategy

| Test Category | Coverage | Purpose |
|---------------|----------|---------|
| **Unit Tests** | Capabilities, Adapters | Interface compliance |
| **Integration Tests** | Registry, Tool discovery | Component interaction |
| **End-to-End Tests** | Full game flow | System validation |
| **Compatibility Tests** | Tool mapping scenarios | Graceful degradation | 