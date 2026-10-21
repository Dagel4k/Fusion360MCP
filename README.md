# Fusion 360 MCP Server

[![GitHub license](https://img.shields.io/github/license/Dagel4k/Fusion360MCP)](https://github.com/Dagel4k/Fusion360MCP/blob/main/LICENSE)
[![MCP](https://img.shields.io/badge/Protocol-MCP-blue)](https://modelcontextprotocol.io)

This repository contains a high-performance Model Context Protocol (MCP) server for Autodesk Fusion 360. It enables AI assistants like Claude to interact directly with Fusion 360, allowing for AI-driven CAD modeling, design inspection, and automation.

## Overview

The server runs as a background thread within a Fusion 360 add-in, exposing the Fusion 360 API through the MCP protocol. It supports two communication modes:
1. HTTP SSE: Standard MCP protocol streaming for real-time interaction.
2. File-based Bridge: A robust fallback mechanism for environments with restricted network access.

## Key Features

- Full Sketching Control: Create planes, draw geometry, add dimensions, and apply constraints.
- 3D Modeling Tools: Extrude, revolve, sweep, loft, fillet, chamfer, and shell.
- Parametric Design: Create and modify user parameters dynamically.
- Assembly Management: Create components, move bodies, and manage design hierarchy.
- Appearance & Materials: Search and apply physical materials and visual appearances.
- Inspection: Retrieve detailed information about bodies, faces, edges, and design structure.
- Export & Visualization: Export STL/STEP files, take screenshots, and control viewport camera.
- Arbitrary Scripting: Execute custom Python scripts directly within the Fusion 360 context.

## Requirements

- Autodesk Fusion 360
- Python 3.9+ (Must be installed in Fusion 360's internal environment)
- MCP Python SDK: `pip install "mcp[cli]"`
- Uvicorn: `pip install uvicorn`

## Installation

### 1. Install Dependencies in Fusion 360
Fusion 360 uses its own isolated Python environment. You MUST install the required packages there.

**Recommended Approach:**
Run the included installer script with your system Python:
```bash
python install_mcp_for_fusion.py
```
This script automatically detects your Fusion 360 installations and injects the necessary packages.

### 2. Install the Add-in
1. Open Fusion 360.
2. Go to Design -> Utilities -> Add-Ins -> Scripts and Add-Ins.
3. Click the Add-Ins tab and click the + (plus) button.
4. Select the MCPserve folder from this repository.
5. Select MCPserve in the list and click Run.
6. A new button "MCP Server" will appear in your Add-Ins panel. Click it to start the server.

## Using with Claude Desktop

To use Fusion 360 as a tool within Claude, add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fusion360": {
      "command": "python",
      "args": [
        "C:/path/to/Fusion360MCP/client.py",
        "--use-sdk"
      ],
      "env": {
        "PYTHONPATH": "C:/path/to/Fusion360MCP"
      }
    }
  }
}
```

## Available Tools

The server exposes a comprehensive suite of tools categorized as follows:

### Sketching
| Tool | Description |
| --- | --- |
| `create_new_sketch` | Creates a sketch on XY, XZ, or YZ planes. |
| `draw_rectangle` | Draws a center-point rectangle with specified dimensions. |
| `draw_circle` | Draws a circle at a specific coordinate. |
| `draw_line` / `draw_arc` | Precise geometric primitive creation. |
| `add_sketch_dimension` | Adds linear dimensions to sketch entities. |
| `add_sketch_constraint` | Applies Parallel, Perpendicular, Tangent, etc. |

### 3D Operations
| Tool | Description |
| --- | --- |
| `extrude` | Standard extrusion (NewBody, Join, Cut, Intersect). |
| `revolve` | Revolve a profile around an axis. |
| `loft_profiles` | Create complex transitions between multiple sketches. |
| `fillet_edges` / `chamfer_edges` | Apply edge treatments by index. |
| `shell_body` | Hollow out a body with specific face removal. |

### Management & Utility
| Tool | Description |
| --- | --- |
| `create_parameter` | Define parametric values for your design. |
| `create_component` | Organize your design with new components. |
| `apply_appearance` | Apply visual styles (e.g., "Aluminum - Polished"). |
| `export_stl` | Export specific bodies for 3D printing. |
| `run_python_script` | Full API access for advanced users. |

## Resources

AI agents can query the following resources:
- `fusion://active-document-info`: Basic metadata of the current file.
- `fusion://design-structure`: Full component/body/sketch hierarchy.
- `fusion://parameters`: List of all user and model parameters.
- `fusion://bodies-info`: Mass properties, volume, and bounding boxes.
- `fusion://sketches-info`: Detailed profile and curve data.

## Testing

A standalone client is provided to verify connectivity:
```bash
# Test the bridge and message box
python client.py --test-connection --test-message-box --message "Hello from CLI!"

# List all tools as seen by the MCP client
python client.py --list-tools
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Model Context Protocol by Anthropic.
- Autodesk Fusion 360 API Team.
