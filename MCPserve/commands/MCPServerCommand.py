#!/usr/bin/env python3

import adsk.core
import adsk.fusion
import os
import sys
import traceback
import threading
import time
import json
import asyncio
from pathlib import Path



# Global variables
app = adsk.core.Application.get()
ui = app.userInterface
server_thread = None
server_running = False
server_instance = None
message_command_handlers = []  # Store command handlers to prevent garbage collection

# Initialize the global handlers list
handlers = []

# Append site-packages from the Python executable path to ensure installed packages are found
def add_fusion_site_packages():
    # Get the production folder where Fusion360.exe lives
    executable_path = sys.executable
    executable_dir = os.path.dirname(executable_path)
    
    # Common Fusion 360 site-packages locations relative to the production folder
    # Many versions use production/[hash]/Python/Lib/site-packages
    paths_to_check = [
        os.path.join(executable_dir, "Python", "Lib", "site-packages"),
        os.path.join(executable_dir, "Python", "lib", "site-packages"),
        os.path.join(executable_dir, "Lib", "site-packages"),
        # Sometimes there's a versioned folder inside Python
        os.path.join(executable_dir, "Python", "python3.11", "site-packages"),
        os.path.join(executable_dir, "Python", "python3.10", "site-packages"),
        os.path.join(executable_dir, "Python", "python3.9", "site-packages"),
        os.path.join(executable_dir, "Python", "python3.8", "site-packages"),
        os.path.join(executable_dir, "Python", "python3.7", "site-packages"),
    ]
    
    debug_msg = f"Checking for site-packages in {executable_dir}:\n"
    for p in paths_to_check:
        abs_p = os.path.abspath(p)
        exists = os.path.exists(abs_p)
        debug_msg += f" - {abs_p} (Exists: {exists})\n"
        if exists and abs_p not in sys.path:
            sys.path.append(abs_p)
            print(f"Added to sys.path: {abs_p}")
            
    # Also check the workspace directory (repo root)
    workspace_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    debug_msg += f"Workspace path: {workspace_path}\n"
    
    return debug_msg

base_debug_msg = add_fusion_site_packages()
site_packages_roaming = os.path.join(os.getenv('APPDATA'), 'Python', f'Python{sys.version_info.major}{sys.version_info.minor}', 'site-packages')
if os.path.exists(site_packages_roaming) and site_packages_roaming not in sys.path:
    sys.path.append(site_packages_roaming)

# Function to check if MCP package is installed
def check_mcp_installed():
    missing_packages = []
    error_msgs = []
    
    global base_debug_msg
    current_debug = base_debug_msg + f"\nCurrent sys.path:\n" + "\n".join([f" - {p}" for p in sys.path])
    
    try:
        import mcp
        print(f"Found MCP package at: {mcp.__file__}")
    except Exception as e:
        print(f"Error importing MCP package: {str(e)}")
        missing_packages.append("mcp[cli]")
        error_msgs.append(f"mcp error: {str(e)}\n{traceback.format_exc()}")
    
    try:
        import uvicorn
        print(f"Found uvicorn package at: {uvicorn.__file__}")
    except Exception as e:
        print(f"Error importing uvicorn package: {str(e)}")
        missing_packages.append("uvicorn")
        error_msgs.append(f"uvicorn error: {str(e)}\n{traceback.format_exc()}")
    
    if missing_packages:
        print(f"Missing required packages: {', '.join(missing_packages)}")
        # Append debug info to the first error msg
        error_msgs.insert(0, f"DEBUG INFO:\n{current_debug}\n---")
        return False, "\n".join(error_msgs)
    
    return True, ""
    
    return True, ""

# Function to run MCP server
def run_mcp_server():
    try:
        # Import required MCP modules
        import mcp
        from mcp.server.fastmcp import FastMCP
        import uvicorn
        import threading
        
        # Also, directly test showing a message box when the server starts
        def test_direct_message():
            try:
                test_message = "MCP Server startup test message"
                mcp_comm_dir = Path(__file__).parent.parent.parent / 'mcp_comm'
                mcp_comm_dir.mkdir(exist_ok=True)
                debug_path = str(mcp_comm_dir / 'startup_test_message.txt')
                
                with open(debug_path, "a") as f:
                    f.write(f"Trying command-based test message at server startup: {time.ctime()}\n")
                
                # Try to show the message box using command-based approach
                create_message_box_command(test_message)
                
                with open(debug_path, "a") as f:
                    f.write(f"Command-based test message triggered at {time.ctime()}\n")
            except Exception as e:
                with open(debug_path, "a") as f:
                    f.write(f"Command-based test message failed: {str(e)} at {time.ctime()}\n")
        
        # Removed dangerous threading.Timer that called UI from background thread
        pass
        
        # Create workspace path and diagnostic log
        workspace_path = str(Path(__file__).parent.parent.parent)
        workspace_comm_dir = os.path.join(workspace_path, "mcp_comm")
        os.makedirs(workspace_comm_dir, exist_ok=True)
        
        # Write diagnostic info without relying on __version__
        diagnostic_log = os.path.join(workspace_comm_dir, "mcp_server_diagnostics.log")
        with open(diagnostic_log, "w") as f:
            f.write(f"MCP Server Diagnostics - {time.ctime()}\n\n")
            f.write(f"Server URL: http://127.0.0.1:3000/sse\n")
            f.write(f"Workspace directory: {workspace_path}\n")
            f.write(f"Communication directory: {workspace_comm_dir}\n\n")
            f.write(f"Python version: {sys.version}\n\n")
            
            # Get MCP version safely if available
            try:
                mcp_version = getattr(mcp, "__version__", "Unknown")
                f.write(f"MCP Version: {mcp_version}\n\n")
            except:
                f.write("MCP Version: Unable to determine\n\n")
            
            f.write(f"Registered Resources:\n  (Method available_resources() not available in this MCP SDK version)\n\n")
            f.write(f"Registered Tools:\n  (Method available_tools() not available in this MCP SDK version)\n\n")
            f.write(f"Registered Prompts:\n  (Method available_prompts() not available in this MCP SDK version)\n\n")
            f.write(f"Environment:\n  Python version: {sys.version}\n  MCP SDK available: True\n\n")
        
        print("Creating FastMCP server instance...")
        # Create the MCP server
        fusion_mcp = FastMCP("Fusion 360 MCP Server")
        
        # Write more diagnostics about the FastMCP object
        with open(diagnostic_log, "a") as f:
            f.write(f"FastMCP Object Attributes:\n")
            for attr in dir(fusion_mcp):
                if not attr.startswith('_'):
                    f.write(f"  - {attr}\n")
            f.write("\n")
        
        print("Registering resources...")
        # Define resources - Note: All resource URIs must have a scheme
        @fusion_mcp.resource("fusion://active-document-info")
        def get_active_document_info():
            """Get information about the active document in Fusion 360."""
            try:
                doc = app.activeDocument
                if doc:
                    path = "Unsaved"
                    try:
                        if hasattr(doc, 'dataFile') and doc.dataFile:
                            path = doc.dataFile.name
                    except:
                        pass
                        
                    return {
                        "name": doc.name,
                        "path": path,
                        "type": str(doc.documentType)
                    }
                else:
                    return {"error": "No active document"}
            except Exception as e:
                return {"error": str(e) + "\n" + traceback.format_exc()}
        
        @fusion_mcp.resource("fusion://design-structure")
        def get_design_structure():
            """Get the structure of the active design in Fusion 360."""
            try:
                doc = app.activeDocument
                if not doc:
                    return {"error": "No active document"}
                
                if str(doc.documentType) != "FusionDesignDocumentType":
                    return {"error": "Not a Fusion design document"}
                
                design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
                if not design:
                    return {"error": "No design in document"}
                
                root_comp = design.rootComponent
                
                def get_component_data(component):
                    data = {
                        "name": component.name,
                        "bodies": [body.name for body in component.bRepBodies],
                        "sketches": [sketch.name for sketch in component.sketches],
                        "occurrences": []
                    }
                    
                    for occurrence in component.occurrences:
                        data["occurrences"].append({
                            "name": occurrence.name,
                            "component": occurrence.component.name
                        })
                    
                    return data
                
                return {
                    "design_name": design.name,
                    "root_component": get_component_data(root_comp)
                }
            except Exception as e:
                return {"error": str(e) + "\n" + traceback.format_exc()}
        
        @fusion_mcp.resource("fusion://parameters")
        def get_parameters():
            """Get the parameters of the active design in Fusion 360."""
            try:
                doc = app.activeDocument
                if not doc:
                    return {"error": "No active document"}
                
                if str(doc.documentType) != "FusionDesignDocumentType":
                    return {"error": "Not a Fusion design document"}
                
                design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
                if not design:
                    return {"error": "No design in document"}
                
                params = []
                for param in design.allParameters:
                    params.append({
                        "name": param.name,
                        "value": param.value,
                        "expression": param.expression,
                        "unit": param.unit,
                        "comment": param.comment
                    })
                
                return {"parameters": params}
            except Exception as e:
                return {"error": str(e) + "\n" + traceback.format_exc()}
        
        @fusion_mcp.resource("fusion://bodies-info")
        def get_bodies_info_resource():
            """Get all bodies with volume, bounding box, face and edge counts."""
            try:
                design = adsk.fusion.Design.cast(app.activeProduct)
                if not design:
                    return {"error": "No active design"}
                root = design.rootComponent
                bodies = []
                for i in range(root.bRepBodies.count):
                    body = root.bRepBodies.item(i)
                    bb = body.boundingBox
                    entry = {
                        "index": i, "name": body.name,
                        "is_solid": body.isSolid,
                        "face_count": body.faces.count,
                        "edge_count": body.edges.count,
                    }
                    if body.isSolid:
                        try:
                            entry["volume_cm3"] = round(body.physicalProperties.volume, 4)
                        except Exception:
                            pass
                    if bb:
                        entry["bbox_mm"] = {
                            "min": [round(bb.minPoint.x * 10, 2), round(bb.minPoint.y * 10, 2), round(bb.minPoint.z * 10, 2)],
                            "max": [round(bb.maxPoint.x * 10, 2), round(bb.maxPoint.y * 10, 2), round(bb.maxPoint.z * 10, 2)]
                        }
                    bodies.append(entry)
                return {"bodies": bodies, "total": root.bRepBodies.count}
            except Exception as e:
                return {"error": str(e)}

        @fusion_mcp.resource("fusion://feature-tree")
        def get_feature_tree():
            """Get the design timeline with feature names and types."""
            try:
                design = adsk.fusion.Design.cast(app.activeProduct)
                if not design:
                    return {"error": "No active design"}
                timeline = design.timeline
                features = []
                for i in range(timeline.count):
                    item = timeline.item(i)
                    features.append({
                        "index": i,
                        "name": item.name,
                        "type": item.entity.objectType.split("::")[-1] if item.entity else "Unknown",
                        "is_suppressed": item.isSuppressed,
                    })
                return {"features": features, "total": timeline.count}
            except Exception as e:
                return {"error": str(e)}

        @fusion_mcp.resource("fusion://sketches-info")
        def get_sketches_info_resource():
            """Get all sketches with profile count and curve count."""
            try:
                design = adsk.fusion.Design.cast(app.activeProduct)
                if not design:
                    return {"error": "No active design"}
                root = design.rootComponent
                sketches = []
                for i in range(root.sketches.count):
                    sk = root.sketches.item(i)
                    sketches.append({
                        "index": i, "name": sk.name,
                        "profile_count": sk.profiles.count,
                        "curve_count": sk.sketchCurves.count,
                        "is_visible": sk.isVisible,
                    })
                return {"sketches": sketches, "total": root.sketches.count}
            except Exception as e:
                return {"error": str(e)}

        print("Registering tools...")
        # Define tools
        @fusion_mcp.tool()
        def message_box(message: str) -> str:
            """Display a message box in Fusion 360."""
            try:
                # Try to show a test message directly for debugging
                mcp_comm_dir = Path(__file__).parent.parent.parent / 'mcp_comm'
                mcp_comm_dir.mkdir(exist_ok=True)
                debug_path = str(mcp_comm_dir / 'message_tool_debug.txt')
                with open(debug_path, "a") as f:
                    f.write(f"Message box tool called with: {message} at {time.ctime()}\n")
                
                # Try to show directly
                success = show_message_box(message)
                
                # Log result
                with open(debug_path, "a") as f:
                    f.write(f"Direct show result: {success} at {time.ctime()}\n")
                
                return "Message displayed successfully (queued if not shown immediately)"
            except Exception as e:
                return f"Error displaying message: {str(e)}"
        
        @fusion_mcp.tool()
        def create_new_sketch(plane_name: str) -> str:
            """Create a new sketch on the specified plane."""
            try:
                doc = app.activeDocument
                if not doc:
                    return "No active document"
                
                # Check for design product
                design_product = doc.products.itemByProductType('DesignProductType')
                if not design_product:
                    return "Active document is not a design document"
                
                # Cast to Design type
                design = adsk.fusion.Design.cast(design_product)
                if not design:
                    return "Failed to get design from document"
                
                root_comp = design.rootComponent
                
                # Find the plane
                sketch_plane = None
                
                # Check if the plane_name is a standard plane (XY, YZ, XZ)
                if plane_name.upper() == "XY":
                    sketch_plane = root_comp.xYConstructionPlane
                elif plane_name.upper() == "YZ":
                    sketch_plane = root_comp.yZConstructionPlane
                elif plane_name.upper() == "XZ":
                    sketch_plane = root_comp.xZConstructionPlane
                else:
                    # Try to find a construction plane with the given name
                    construction_planes = root_comp.constructionPlanes
                    for i in range(construction_planes.count):
                        plane = construction_planes.item(i)
                        if plane.name == plane_name:
                            sketch_plane = plane
                            break
                
                if not sketch_plane:
                    return f"Could not find plane: {plane_name}"
                
                # Create the sketch
                sketches = root_comp.sketches
                sketch = sketches.add(sketch_plane)
                return f"Sketch created successfully: {sketch.name}"
            except Exception as e:
                error_msg = f"Error creating sketch: {str(e)}"
                print(error_msg)
                print(traceback.format_exc())
                return error_msg

        @fusion_mcp.tool()
        def create_sketch_on_offset_plane(base_plane: str, offset_mm: float) -> str:
            """Create a sketch on a construction plane offset from XY, XZ, or YZ."""
            script = f"""
root = design.rootComponent
planes = root.constructionPlanes
planeInput = planes.createInput()
offset = adsk.core.ValueInput.createByReal({offset_mm/10})
plane_map = {{"XY": root.xYConstructionPlane, "YZ": root.yZConstructionPlane, "XZ": root.xZConstructionPlane}}
base = plane_map.get({repr(base_plane.upper())}, root.xYConstructionPlane)
planeInput.setByOffset(base, offset)
plane = planes.add(planeInput)
sketch = root.sketches.add(plane)
sketch.name = f"Sketch_Offset_{int(time.time()) % 10000}"
__result__["data"] = sketch.name
"""
            r = exec_script_with_result(script)
            return f"Sketch created on offset plane: {r['data']}" if r["status"] == "ok" else f"Error: {r['error']}"
        
        @fusion_mcp.tool()
        def create_parameter(name: str, expression: str, unit: str, comment: str = "") -> str:
            """Create a new parameter in the active design."""
            try:
                doc = app.activeDocument
                if not doc:
                    return "No active document"
                
                # Check for design product
                design_product = doc.products.itemByProductType('DesignProductType')
                if not design_product:
                    return "Active document is not a design document"
                
                # Cast to Design type
                design = adsk.fusion.Design.cast(design_product)
                if not design:
                    return "Failed to get design from document"
                
                # Create the parameter
                try:
                    param = design.userParameters.add(name, adsk.core.ValueInput.createByString(expression), unit, comment)
                    return f"Parameter created successfully: {param.name} = {param.expression}"
                except Exception as e:
                    # Check if parameter already exists
                    existing_param = design.userParameters.itemByName(name)
                    if existing_param:
                        # Update the existing parameter
                        existing_param.expression = expression
                        existing_param.unit = unit
                        if comment:
                            existing_param.comment = comment
                        return f"Parameter updated: {existing_param.name} = {existing_param.expression}"
                    else:
                        raise e
            except Exception as e:
                error_msg = f"Error creating parameter: {str(e)}"
                print(error_msg)
                print(traceback.format_exc())
                return error_msg

        @fusion_mcp.tool()
        def run_python_script(script: str) -> str:
            """Execute arbitrary Python in Fusion 360. Globals available: adsk, app, ui, design.
            Set __result__["data"] = <value> to return JSON-serializable data."""
            r = exec_script_with_result(script)
            if r["status"] == "error":
                return f"Error: {r['error']}\n\nTraceback:\n{r.get('traceback', '')}"
            data = r.get("data")
            if data is None:
                return "Script executed successfully"
            if isinstance(data, (dict, list)):
                return json.dumps(data, indent=2)
            return str(data)

        # ── Sketch tools ──────────────────────────────────────────────────────

        @fusion_mcp.tool()
        def draw_line(sketch_name: str, start_pt: list, end_pt: list) -> str:
            """Draw a line in a sketch. sketch_name or 'last'. Points are [x,y] or [x,y,z] in mm."""
            script = f"""
root = design.rootComponent
sk = root.sketches.itemByName({repr(sketch_name)}) if {repr(sketch_name)} != 'last' else root.sketches.item(root.sketches.count - 1)
if not sk: raise ValueError(f"Sketch not found: {repr(sketch_name)}")
s = adsk.core.Point3D.create({start_pt[0]/10}, {start_pt[1]/10}, {start_pt[2]/10 if len(start_pt) > 2 else 0})
e = adsk.core.Point3D.create({end_pt[0]/10}, {end_pt[1]/10}, {end_pt[2]/10 if len(end_pt) > 2 else 0})
sk.sketchCurves.sketchLines.addByTwoPoints(s, e)
__result__["data"] = f"Line drawn in {{sk.name}}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def draw_rectangle(sketch_name: str, center_pt: list, width_mm: float, height_mm: float) -> str:
            """Draw a center-point rectangle in a sketch. center_pt is [x,y] in mm."""
            script = f"""
root = design.rootComponent
sk = root.sketches.itemByName({repr(sketch_name)}) if {repr(sketch_name)} != 'last' else root.sketches.item(root.sketches.count - 1)
if not sk: raise ValueError(f"Sketch not found")
c = adsk.core.Point3D.create({center_pt[0]/10}, {center_pt[1]/10}, 0)
corner = adsk.core.Point3D.create({center_pt[0]/10 + width_mm/20}, {center_pt[1]/10 + height_mm/20}, 0)
sk.sketchCurves.sketchLines.addCenterPointRectangle(c, corner)
__result__["data"] = f"Rectangle {width_mm}x{height_mm} mm in {{sk.name}}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def draw_circle(sketch_name: str, center_pt: list, radius_mm: float) -> str:
            """Draw a circle in a sketch. center_pt is [x,y] in mm."""
            script = f"""
root = design.rootComponent
sk = root.sketches.itemByName({repr(sketch_name)}) if {repr(sketch_name)} != 'last' else root.sketches.item(root.sketches.count - 1)
if not sk: raise ValueError(f"Sketch not found")
c = adsk.core.Point3D.create({center_pt[0]/10}, {center_pt[1]/10}, 0)
sk.sketchCurves.sketchCircles.addByCenterRadius(c, {radius_mm/10})
__result__["data"] = f"Circle r={radius_mm} mm in {{sk.name}}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def draw_arc(sketch_name: str, center_pt: list, radius_mm: float, start_angle_deg: float, sweep_angle_deg: float) -> str:
            """Draw an arc. center_pt [x,y] mm. start_angle and sweep_angle in degrees."""
            script = f"""
import math
root = design.rootComponent
sk = root.sketches.itemByName({repr(sketch_name)}) if {repr(sketch_name)} != 'last' else root.sketches.item(root.sketches.count - 1)
if not sk: raise ValueError(f"Sketch not found")
c = adsk.core.Point3D.create({center_pt[0]/10}, {center_pt[1]/10}, 0)
r = {radius_mm/10}
start_rad = math.radians({start_angle_deg})
start_pt = adsk.core.Point3D.create(c.x + r*math.cos(start_rad), c.y + r*math.sin(start_rad), 0)
sk.sketchCurves.sketchArcs.addByCenterStartSweep(c, start_pt, math.radians({sweep_angle_deg}))
__result__["data"] = f"Arc in {{sk.name}}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def add_sketch_dimension(sketch_name: str, entity_idx: int, value_mm: float, orientation: str = "Aligned") -> str:
            """Add a linear dimension to a sketch curve. orientation: Horizontal, Vertical, Aligned."""
            orient_map = {"Horizontal": "HorizontalDimensionOrientation",
                          "Vertical": "VerticalDimensionOrientation",
                          "Aligned": "AlignedDimensionOrientation"}
            orient = orient_map.get(orientation, "AlignedDimensionOrientation")
            script = f"""
root = design.rootComponent
sk = root.sketches.itemByName({repr(sketch_name)}) if {repr(sketch_name)} != 'last' else root.sketches.item(root.sketches.count - 1)
if not sk: raise ValueError(f"Sketch not found")
entity = sk.sketchCurves.item({entity_idx})
dim = sk.sketchDimensions.addDistanceDimension(
    entity.startSketchPoint, entity.endSketchPoint,
    adsk.fusion.DimensionOrientations.{orient},
    adsk.core.Point3D.create(0, 0, 0)
)
dim.parameter.expression = "{value_mm} mm"
__result__["data"] = f"Dimension {value_mm} mm added"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def add_sketch_constraint(sketch_name: str, constraint_type: str, entity1_idx: int, entity2_idx: int = -1) -> str:
            """Add a geometric constraint. Types: Horizontal, Vertical, Parallel, Perpendicular, Equal, Tangent, Fixed."""
            script = f"""
root = design.rootComponent
sk = root.sketches.itemByName({repr(sketch_name)}) if {repr(sketch_name)} != 'last' else root.sketches.item(root.sketches.count - 1)
if not sk: raise ValueError(f"Sketch not found")
e1 = sk.sketchCurves.item({entity1_idx})
e2 = sk.sketchCurves.item({entity2_idx}) if {entity2_idx} >= 0 else None
c = sk.geometricConstraints
ct = {repr(constraint_type)}
if ct == "Horizontal": c.addHorizontal(e1)
elif ct == "Vertical": c.addVertical(e1)
elif ct == "Parallel": c.addParallel(e1, e2)
elif ct == "Perpendicular": c.addPerpendicular(e1, e2)
elif ct == "Equal": c.addEqual(e1, e2)
elif ct == "Tangent": c.addTangent(e1, e2)
elif ct == "Fixed": c.addFixed(e1)
else: raise ValueError(f"Unknown constraint: {{ct}}")
__result__["data"] = f"{{ct}} constraint added"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def get_sketch_profiles_info(sketch_name: str) -> str:
            """Get profile and curve counts for a sketch. Use before extrude/revolve."""
            script = f"""
root = design.rootComponent
sk = root.sketches.itemByName({repr(sketch_name)}) if {repr(sketch_name)} != 'last' else root.sketches.item(root.sketches.count - 1)
if not sk: raise ValueError(f"Sketch not found")
__result__["data"] = {{"sketch": sk.name, "profiles": sk.profiles.count, "curves": sk.sketchCurves.count}}
"""
            r = exec_script_with_result(script)
            if r["status"] == "error":
                return f"Error: {r['error']}"
            return json.dumps(r.get("data", {}), indent=2)

        # ── 3D Operations ─────────────────────────────────────────────────────

        @fusion_mcp.tool()
        def extrude(sketch_name: str, profile_idx: int, distance_mm: float, operation: str = "NewBody") -> str:
            """Extrude a sketch profile. operation: NewBody, Join, Cut, Intersect."""
            op_map = {"NewBody": "NewBodyFeatureOperation", "Join": "JoinFeatureOperation",
                      "Cut": "CutFeatureOperation", "Intersect": "IntersectFeatureOperation"}
            op = op_map.get(operation, "NewBodyFeatureOperation")
            script = f"""
root = design.rootComponent
sk = root.sketches.itemByName({repr(sketch_name)}) if {repr(sketch_name)} != 'last' else root.sketches.item(root.sketches.count - 1)
if not sk: raise ValueError(f"Sketch not found")
if sk.profiles.count == 0: raise ValueError(f"Sketch has no closed profiles")
prof = sk.profiles.item({profile_idx})
ext_input = root.features.extrudeFeatures.createInput(prof, adsk.fusion.FeatureOperations.{op})
ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal({distance_mm/10}))
feat = root.features.extrudeFeatures.add(ext_input)
body_name = feat.bodies.item(0).name if feat.bodies.count > 0 else "none"
__result__["data"] = f"Extruded '{{body_name}}', {distance_mm} mm, op={operation}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def revolve(sketch_name: str, profile_idx: int, axis: str = "Z", angle_deg: float = 360.0, operation: str = "NewBody") -> str:
            """Revolve a profile around a construction axis. axis: X, Y, Z. operation: NewBody, Join, Cut, Intersect."""
            op_map = {"NewBody": "NewBodyFeatureOperation", "Join": "JoinFeatureOperation",
                      "Cut": "CutFeatureOperation", "Intersect": "IntersectFeatureOperation"}
            op = op_map.get(operation, "NewBodyFeatureOperation")
            script = f"""
import math
root = design.rootComponent
sk = root.sketches.itemByName({repr(sketch_name)}) if {repr(sketch_name)} != 'last' else root.sketches.item(root.sketches.count - 1)
if not sk: raise ValueError(f"Sketch not found")
prof = sk.profiles.item({profile_idx})
axis_map = {{"X": root.xConstructionAxis, "Y": root.yConstructionAxis, "Z": root.zConstructionAxis}}
rev_axis = axis_map.get({repr(axis)}, root.zConstructionAxis)
rev_input = root.features.revolveFeatures.createInput(prof, rev_axis, adsk.fusion.FeatureOperations.{op})
rev_input.setAngleExtent(False, adsk.core.ValueInput.createByReal(math.radians({angle_deg})))
feat = root.features.revolveFeatures.add(rev_input)
body_name = feat.bodies.item(0).name if feat.bodies.count > 0 else "none"
__result__["data"] = f"Revolved '{{body_name}}', {angle_deg}° around {axis}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def shell_body(body_name: str, face_indices: list, thickness_mm: float) -> str:
            """Shell a body. face_indices: faces to remove (open). Use get_faces_info first."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body '{repr(body_name)}' not found")
faces = adsk.core.ObjectCollection.create()
for i in {repr(face_indices)}:
    idx = i[0] if isinstance(i, list) else i
    faces.add(body.faces.item(int(idx)))
sh_input = root.features.shellFeatures.createInput(faces, False)
sh_input.insideThickness = adsk.core.ValueInput.createByReal({thickness_mm/10})
root.features.shellFeatures.add(sh_input)
__result__["data"] = f"Shell {thickness_mm} mm applied to '{{body.name}}'"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def fillet_edges(body_name: str, edge_indices: list, radius_mm: float) -> str:
            """Fillet edges of a body. Use get_edges_info to find edge indices."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
ec = adsk.core.ObjectCollection.create()
for i in {repr(edge_indices)}:
    idx = i[0] if isinstance(i, list) else i
    ec.add(body.edges.item(int(idx)))
fi = root.features.filletFeatures.createInput()
fi.addConstantRadiusEdgeSet(ec, adsk.core.ValueInput.createByReal({radius_mm/10}), True)
root.features.filletFeatures.add(fi)
__result__["data"] = f"Fillet applied"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def chamfer_edges(body_name: str, edge_indices: list, distance_mm: float) -> str:
            """Chamfer edges of a body."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
ec = adsk.core.ObjectCollection.create()
for i in {repr(edge_indices)}:
    idx = i[0] if isinstance(i, list) else i
    ec.add(body.edges.item(int(idx)))
ci = root.features.chamferFeatures.createInput(ec, True)
ci.setToEqualDistance(adsk.core.ValueInput.createByReal({distance_mm/10}))
root.features.chamferFeatures.add(ci)
__result__["data"] = f"Chamfer {distance_mm} mm applied"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def mirror_body(body_name: str, plane_name: str = "XY") -> str:
            """Mirror a body across a plane. plane_name: XY, YZ, XZ."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
plane_map = {{"XY": root.xYConstructionPlane, "YZ": root.yZConstructionPlane, "XZ": root.xZConstructionPlane}}
plane = plane_map.get({repr(plane_name)}, root.xYConstructionPlane)
ents = adsk.core.ObjectCollection.create()
ents.add(body)
root.features.mirrorFeatures.add(root.features.mirrorFeatures.createInput(ents, plane))
__result__["data"] = f"'{{body.name}}' mirrored across {plane_name}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def circular_pattern_body(body_name: str, count: int, total_angle_deg: float = 360.0, axis: str = "Z") -> str:
            """Circular pattern of a body. axis: X, Y, Z."""
            script = f"""
import math
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
axis_map = {{"X": root.xConstructionAxis, "Y": root.yConstructionAxis, "Z": root.zConstructionAxis}}
pat_axis = axis_map.get({repr(axis)}, root.zConstructionAxis)
ents = adsk.core.ObjectCollection.create()
ents.add(body)
pi = root.features.circularPatternFeatures.createInput(ents, pat_axis)
pi.quantity = adsk.core.ValueInput.createByReal({count})
pi.totalAngle = adsk.core.ValueInput.createByReal(math.radians({total_angle_deg}))
pi.isSymmetric = False
root.features.circularPatternFeatures.add(pi)
__result__["data"] = f"Circular pattern: {count} instances, {total_angle_deg}°"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"


        @fusion_mcp.tool()
        def rectangular_pattern_body(body_name: str, count_x: int, spacing_x_mm: float, count_y: int, spacing_y_mm: float) -> str:
            """Rectangular pattern of a body along X and Y axes."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
ents = adsk.core.ObjectCollection.create()
ents.add(body)
pi = root.features.rectangularPatternFeatures.createInput(
    ents, root.xConstructionAxis,
    adsk.core.ValueInput.createByReal({count_x}),
    adsk.core.ValueInput.createByReal({spacing_x_mm/10}),
    adsk.fusion.PatternDistanceType.SpacingPatternDistanceType)
pi.directionTwoEntity = root.yConstructionAxis
pi.quantityTwo = adsk.core.ValueInput.createByReal({count_y})
pi.distanceTwo = adsk.core.ValueInput.createByReal({spacing_y_mm/10})
root.features.rectangularPatternFeatures.add(pi)
__result__["data"] = f"Rectangular pattern: {count_x}x{count_y}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def rectangular_pattern_body_1d(body_name: str, axis: str, count: int, spacing_mm: float) -> str:
            """Rectangular pattern of a body along one axis (X, Y, or Z)."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
axis_map = {{"X": root.xConstructionAxis, "Y": root.yConstructionAxis, "Z": root.zConstructionAxis}}
pat_axis = axis_map.get({repr(axis.upper())}, root.zConstructionAxis)
ents = adsk.core.ObjectCollection.create()
ents.add(body)
pi = root.features.rectangularPatternFeatures.createInput(
    ents, pat_axis,
    adsk.core.ValueInput.createByReal({count}),
    adsk.core.ValueInput.createByReal({spacing_mm/10}),
    adsk.fusion.PatternDistanceType.SpacingPatternDistanceType)
root.features.rectangularPatternFeatures.add(pi)
__result__["data"] = f"1D Pattern: {{count}} instances along {{axis}}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"


        @fusion_mcp.tool()
        def boolean_combine(target_body_name: str, tool_body_name: str, operation: str = "Join") -> str:
            """Boolean between two bodies. operation: Join, Cut, Intersect."""
            op_map = {"Join": "JoinFeatureOperation", "Cut": "CutFeatureOperation",
                      "Intersect": "IntersectFeatureOperation"}
            op = op_map.get(operation, "JoinFeatureOperation")
            script = f"""
root = design.rootComponent
target = root.bRepBodies.itemByName({repr(target_body_name)})
tool_b = root.bRepBodies.itemByName({repr(tool_body_name)})
if not target: raise ValueError(f"Target body not found")
if not tool_b: raise ValueError(f"Tool body not found")
tools = adsk.core.ObjectCollection.create()
tools.add(tool_b)
ci = root.features.combineFeatures.createInput(target, tools)
ci.operation = adsk.fusion.FeatureOperations.{op}
ci.isKeepToolBodies = False
root.features.combineFeatures.add(ci)
__result__["data"] = f"{operation} completed"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def boolean_bodies(target_body_name: str, tool_body_name: str, operation: str = "Join") -> str:
            """Boolean operation between two bodies. operation: Join, Cut, Intersect."""
            return boolean_combine(target_body_name, tool_body_name, operation)

        @fusion_mcp.tool()
        def sweep_profile(profile_sketch_name: str, profile_idx: int, path_sketch_name: str, path_curve_idx: int, operation: str = "NewBody") -> str:
            """Sweep a profile along a path curve from another sketch."""
            op_map = {"NewBody": "NewBodyFeatureOperation", "Join": "JoinFeatureOperation",
                      "Cut": "CutFeatureOperation"}
            op = op_map.get(operation, "NewBodyFeatureOperation")
            script = f"""
root = design.rootComponent
prof_sk = root.sketches.itemByName({repr(profile_sketch_name)})
path_sk = root.sketches.itemByName({repr(path_sketch_name)})
if not prof_sk: raise ValueError(f"Profile sketch not found")
if not path_sk: raise ValueError(f"Path sketch not found")
prof = prof_sk.profiles.item({profile_idx})
path = root.features.createPath(path_sk.sketchCurves.item({path_curve_idx}))
si = root.features.sweepFeatures.createInput(prof, path, adsk.fusion.FeatureOperations.{op})
root.features.sweepFeatures.add(si)
__result__["data"] = "Sweep completed"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def loft_profiles(sketch_profile_pairs: list) -> str:
            """Loft between profiles. sketch_profile_pairs: [[sketch_name, profile_idx], ...]"""
            script = f"""
root = design.rootComponent
li = root.features.loftFeatures.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
for sk_name, prof_idx in {sketch_profile_pairs}:
    sk = root.sketches.itemByName(sk_name)
    if not sk: raise ValueError(f"Sketch '{{sk_name}}' not found")
    li.loftSections.add(sk.profiles.item(prof_idx))
root.features.loftFeatures.add(li)
__result__["data"] = f"Loft with {len(sketch_profile_pairs)} sections completed"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        # ── Assembly ──────────────────────────────────────────────────────────

        @fusion_mcp.tool()
        def create_component(name: str) -> str:
            """Create a new empty component in the root component."""
            script = f"""
root = design.rootComponent
occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
occ.component.name = {repr(name)}
__result__["data"] = f"Component '{{occ.component.name}}' created"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def move_component(occurrence_name: str, x_mm: float, y_mm: float, z_mm: float) -> str:
            """Translate a component occurrence by x,y,z in mm."""
            script = f"""
root = design.rootComponent
occ = None
for i in range(root.occurrences.count):
    o = root.occurrences.item(i)
    if o.name == {repr(occurrence_name)} or o.component.name == {repr(occurrence_name)}:
        occ = o; break
if not occ: raise ValueError(f"Occurrence not found: {repr(occurrence_name)}")
t = occ.transform
t.translation = adsk.core.Vector3D.create({x_mm/10}, {y_mm/10}, {z_mm/10})
occ.transform = t
__result__["data"] = f"Moved ({x_mm}, {y_mm}, {z_mm}) mm"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def move_body(body_name: str, x_mm: float, y_mm: float, z_mm: float) -> str:
            """Translate a body by x,y,z offset in mm."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found: {repr(body_name)}")
ents = adsk.core.ObjectCollection.create()
ents.add(body)
transform = adsk.core.Matrix3D.create()
transform.translation = adsk.core.Vector3D.create({x_mm/10}, {y_mm/10}, {z_mm/10})
moveFeats = root.features.moveFeatures
moveInput = moveFeats.createInput(ents, transform)
moveFeats.add(moveInput)
__result__["data"] = f"Moved body '{{body_name}}' by ({{x_mm}}, {{y_mm}}, {{z_mm}}) mm"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def rename_body(old_name: str, new_name: str) -> str:
            """Rename a body in the root component."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(old_name)})
if not body: raise ValueError(f"Body not found")
body.name = {repr(new_name)}
__result__["data"] = f"Body '{{old_name}}' renamed to '{{new_name}}'"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def move_body(body_name: str, x_mm: float, y_mm: float, z_mm: float) -> str:
            """Translate a body by x,y,z offset in mm."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found: {repr(body_name)}")
ents = adsk.core.ObjectCollection.create()
ents.add(body)
transform = adsk.core.Matrix3D.create()
transform.translation = adsk.core.Vector3D.create({x_mm/10}, {y_mm/10}, {z_mm/10})
moveFeats = root.features.moveFeatures
moveInput = moveFeats.createInput(ents, transform)
moveFeats.add(moveInput)
__result__["data"] = f"Moved body '{{body_name}}' by ({{x_mm}}, {{y_mm}}, {{z_mm}}) mm"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def copy_body(body_name: str) -> str:
            """Copy a body in the root component."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
new_body = body.copyToComponent(root)
__result__["data"] = f"Body '{{body.name}}' copied as '{{new_body.name}}'"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def copy_component(occurrence_name: str) -> str:
            """Copy a component occurrence."""
            script = f"""
root = design.rootComponent
occ = None
for i in range(root.occurrences.count):
    o = root.occurrences.item(i)
    if o.name == {repr(occurrence_name)} or o.component.name == {repr(occurrence_name)}:
        occ = o; break
if not occ: raise ValueError(f"Occurrence not found")
root.occurrences.addExistingComponent(occ.component, adsk.core.Matrix3D.create())
__result__["data"] = f"'{{occ.component.name}}' copied"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        # ── Information tools ─────────────────────────────────────────────────

        @fusion_mcp.tool()
        def get_bodies_info() -> str:
            """Get all bodies with name, volume, bounding box, face and edge counts."""
            script = """
root = design.rootComponent
result_data = []
for i in range(root.bRepBodies.count):
    body = root.bRepBodies.item(i)
    bb = body.boundingBox
    entry = {"index": i, "name": body.name, "is_solid": body.isSolid,
             "faces": body.faces.count, "edges": body.edges.count}
    if body.isSolid:
        try: entry["volume_cm3"] = round(body.physicalProperties.volume, 4)
        except: pass
    if bb:
        entry["bbox_mm"] = {
            "min": [round(bb.minPoint.x*10, 2), round(bb.minPoint.y*10, 2), round(bb.minPoint.z*10, 2)],
            "max": [round(bb.maxPoint.x*10, 2), round(bb.maxPoint.y*10, 2), round(bb.maxPoint.z*10, 2)]
        }
    result_data.append(entry)
__result__["data"] = result_data
"""
            r = exec_script_with_result(script)
            if r["status"] == "error":
                return f"Error: {r['error']}"
            return json.dumps(r.get("data", []), indent=2)

        @fusion_mcp.tool()
        def get_faces_info(body_name: str) -> str:
            """Get face indices, types and areas for a body. Use before shell operations."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
data = []
for i in range(body.faces.count):
    face = body.faces.item(i)
    data.append({{"index": i, "type": type(face.geometry).__name__, "area_cm2": round(face.area, 4)}})
__result__["data"] = data
"""
            r = exec_script_with_result(script)
            if r["status"] == "error":
                return f"Error: {r['error']}"
            return json.dumps(r.get("data", []), indent=2)

        @fusion_mcp.tool()
        def get_edges_info(body_name: str) -> str:
            """Get edge indices and lengths for a body. Use before fillet/chamfer."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
data = [{{"index": i, "length_mm": round(body.edges.item(i).length*10, 3)}} for i in range(body.edges.count)]
__result__["data"] = data
"""
            r = exec_script_with_result(script)
            if r["status"] == "error":
                return f"Error: {r['error']}"
            return json.dumps(r.get("data", []), indent=2)

        # ── Materials & Appearance ────────────────────────────────────────────

        @fusion_mcp.tool()
        def apply_appearance(body_name: str, appearance_name: str) -> str:
            """Apply a visual appearance to a body. E.g.: 'Aluminum', 'Steel - Satin'."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
# Support direct names or partial match in libraries
def find_lib(name_part):
    for l in app.materialLibraries:
        if name_part.lower() in l.name.lower(): return l
    return None
lib = find_lib('Appearance') or find_lib('Material')
if not lib: raise ValueError("Material/Appearance library not found")
appr = lib.appearances.itemByName({repr(appearance_name)})
if not appr: raise ValueError(f"Appearance '{repr(appearance_name)}' not found in {{lib.name}}")
body.appearance = appr
__result__["data"] = f"Appearance '{{appr.name}}' applied from '{{lib.name}}'"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def apply_physical_material(body_name: str, material_name: str) -> str:
            """Apply a physical material to a body. E.g.: 'Aluminum 6061', 'Steel'."""
            script = f"""
root = design.rootComponent
body = root.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
def find_lib(name_part):
    for l in app.materialLibraries:
        if name_part.lower() in l.name.lower(): return l
    return None
lib = find_lib('Material') or find_lib('Fusion 360')
if not lib: raise ValueError("Material library not found")
mat = lib.materials.itemByName({repr(material_name)})
if not mat: raise ValueError(f"Material '{repr(material_name)}' not found in {{lib.name}}")
body.material = mat
__result__["data"] = f"Material '{{mat.name}}' applied from '{{lib.name}}'"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def list_available_appearances() -> str:
            """List all available appearances in the Fusion 360 library."""
            script = """
def find_lib(name_part):
    for l in app.materialLibraries:
        if name_part.lower() in l.name.lower(): return l
    return None
lib = find_lib('Appearance') or find_lib('Material')
if not lib: raise ValueError("Appearance library not found")
names = [a.name for a in lib.appearances]
__result__["data"] = sorted(names)
"""
            r = exec_script_with_result(script)
            if r["status"] == "error": return f"Error: {r['error']}"
            return json.dumps(r.get("data", []), indent=2)

        @fusion_mcp.tool()
        def list_available_materials() -> str:
            """List all available physical materials in the Fusion 360 library."""
            script = """
def find_lib(name_part):
    for l in app.materialLibraries:
        if name_part.lower() in l.name.lower(): return l
    return None
lib = find_lib('Material') or find_lib('Fusion 360')
if not lib: raise ValueError("Material library not found")
names = [m.name for m in lib.materials]
__result__["data"] = sorted(names)
"""
            r = exec_script_with_result(script)
            if r["status"] == "error": return f"Error: {r['error']}"
            return json.dumps(r.get("data", []), indent=2)

        # ── Export ────────────────────────────────────────────────────────────

        @fusion_mcp.tool()
        def export_stl(body_name: str, filename: str) -> str:
            """Export a body as STL to the Desktop."""
            script = f"""
import os
body = design.rootComponent.bRepBodies.itemByName({repr(body_name)})
if not body: raise ValueError(f"Body not found")
path = os.path.join(os.path.expanduser("~"), "Desktop", {repr(filename)})
if not path.lower().endswith(".stl"): path += ".stl"
opts = design.exportManager.createSTLExportOptions(body, path)
opts.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementMedium
design.exportManager.execute(opts)
__result__["data"] = f"STL saved: {{path}}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def export_step(filename: str) -> str:
            """Export the entire design as STEP to the Desktop."""
            script = f"""
import os
path = os.path.join(os.path.expanduser("~"), "Desktop", {repr(filename)})
if not path.lower().endswith((".step", ".stp")): path += ".step"
opts = design.exportManager.createSTEPExportOptions(path)
design.exportManager.execute(opts)
__result__["data"] = f"STEP saved: {{path}}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        # ── View ──────────────────────────────────────────────────────────────

        @fusion_mcp.tool()
        def set_view(view_type: str) -> str:
            """Set viewport orientation. view_type: Top, Bottom, Left, Right, Front, Back, Iso."""
            orient_map = {"Top": "TopViewType", "Bottom": "BottomViewType", "Left": "LeftViewType",
                          "Right": "RightViewType", "Front": "FrontViewType",
                          "Back": "BackViewType", "Iso": "IsoViewType"}
            orient = orient_map.get(view_type, "IsoViewType")
            script = f"""
vp = app.activeViewport
cam = vp.camera
cam.viewOrientation = adsk.core.ViewOrientations.{orient}
cam.isSmoothTransition = True
vp.camera = cam
__result__["data"] = f"View set to {view_type}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def fit_to_screen() -> str:
            """Fit the design to the viewport."""
            script = """
app.activeViewport.fit()
__result__["data"] = "Fitted to screen"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        @fusion_mcp.tool()
        def take_screenshot(filename: str = "fusion_capture.png") -> str:
            """Save a screenshot of the viewport to the Desktop."""
            script = f"""
import os
path = os.path.join(os.path.expanduser("~"), "Desktop", {repr(filename)})
app.activeViewport.saveAsImageFile(path, 0, 0)
__result__["data"] = f"Screenshot saved: {{path}}"
"""
            r = exec_script_with_result(script)
            return r.get("data", "OK") if r["status"] == "ok" else f"Error: {r['error']}"

        print("Registering prompts...")
        # Define prompts
        @fusion_mcp.prompt()
        def create_sketch_prompt(description: str) -> dict:
            """Create a prompt for creating a sketch based on a description."""
            return {
                "messages": [
                    {
                        "role": "system",
                        "content": """You are an expert in Fusion 360 CAD modeling. Your task is to help the user create sketches based on their descriptions.
                        
Be very specific about what planes to use and what sketch entities to create.
"""
                    },
                    {
                        "role": "user",
                        "content": f"I want to create a sketch with these requirements: {description}\n\nPlease provide step-by-step instructions for creating this sketch in Fusion 360."
                    }
                ]
            }
        
        @fusion_mcp.prompt()
        def parameter_setup_prompt(description: str) -> dict:
            """Create a prompt for setting up parameters based on a description."""
            return {
                "messages": [
                    {
                        "role": "system",
                        "content": """You are an expert in Fusion 360 parametric design. Your task is to help the user set up parameters for their design.

Suggest appropriate parameters, their values, units, and purposes based on the user's description.
"""
                    },
                    {
                        "role": "user",
                        "content": f"I want to set up parameters for: {description}\n\nWhat parameters should I create, and what values, units, and comments should they have?"
                    }
                ]
            }
        
        # Set up file-based communication
        print("Setting up file-based communication...")
        
        # Paths for the add-in and workspace directories
        addon_path = os.path.dirname(os.path.dirname(__file__))
        addon_comm_dir = os.path.join(addon_path, "mcp_comm")
        os.makedirs(addon_comm_dir, exist_ok=True)
        
        # Workspace path (the fusion-mcp-server repository)
        workspace_path = str(Path(__file__).parent.parent.parent)
        workspace_comm_dir = Path(workspace_path) / "mcp_comm"
        if os.path.exists(workspace_path):
            os.makedirs(str(workspace_comm_dir), exist_ok=True)
        
        # Create a list of communication directories to monitor
        comm_dirs = [
            addon_comm_dir,
            str(workspace_comm_dir)
        ]
        
        # Create desktop path for ready file
        ready_file_desktop = os.path.expanduser("~/Desktop/mcp_server_ready.txt")
        
        # Create server info file
        server_info_file = os.path.join(workspace_comm_dir, "mcp_server_info.txt")
        with open(server_info_file, "w") as f:
            f.write(f"MCP Server started at {time.ctime()}\n")
            f.write(f"Python version: {sys.version}\n")
        
        # Create server status file with JSON structure
        server_status_file = os.path.join(workspace_comm_dir, "server_status.json")
        with open(server_status_file, "w") as f:
            status_data = {
                "status": "running",
                "started_at": time.ctime(),
                "server_url": "http://127.0.0.1:3000/sse",
                "fusion_version": "3.0", # Hardcoded or pass from main thread
                "available_resources": [
                    "fusion://active-document-info",
                    "fusion://design-structure",
                    "fusion://parameters"
                ],
                "available_tools": [
                    "message_box", "create_new_sketch", "create_sketch_on_offset_plane",
                    "draw_line", "draw_rectangle", "draw_circle", "extrude", "move_body",
                    "boolean_bodies", "rectangular_pattern_body", "rectangular_pattern_body_1d",
                    "shell_body", "fillet_edges", "apply_appearance", "take_screenshot",
                    "export_step", "set_view", "rename_body"
                ],
                "available_prompts": [
                    "create_sketch_prompt",
                    "parameter_setup_prompt"
                ]
            }
            json.dump(status_data, f, indent=2)
        
        # Create all ready file paths
        ready_files = [
            ready_file_desktop,
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_server_ready.txt"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "mcp_server_ready.txt"),
            os.path.join(workspace_path, "mcp_server_ready.txt"),
            str(workspace_comm_dir / "mcp_server_ready.txt")
        ]
        
        # Create all ready files
        for ready_file in ready_files:
            try:
                os.makedirs(os.path.dirname(ready_file), exist_ok=True)
                with open(ready_file, "w") as f:
                    f.write(f"MCP Server Ready - {time.ctime()}")
                print(f"Created ready file: {ready_file}")
            except Exception as e:
                print(f"Error creating ready file at {ready_file}: {str(e)}")
        
        # Run the FastMCP server
        print("Starting MCP server using FastMCP with uvicorn")
        
        # Get the Starlette app from the sse_app method
        sse_app = fusion_mcp.sse_app()
        
        # Port and host for the server
        host = "127.0.0.1"
        port = 3000  # Default port for SSE
        
        # Create a Config instance for uvicorn
        config = uvicorn.Config(
            sse_app,
            host=host,
            port=port,
            log_level="info"
        )
        
        # Create server instance
        global server_instance
        server_instance = uvicorn.Server(config)
        
        # Run the server directly in the current background thread
        try:
            # Create initialization log
            init_log_file = os.path.join(workspace_comm_dir, "mcp_server_init.log")
            with open(init_log_file, "w") as f:
                f.write(f"Starting uvicorn server at {time.ctime()}\n")
                f.write(f"Host: {host}, Port: {port}\n")
            
            # Run the server (this is blocking in this background thread)
            print(f"MCP server starting at http://{host}:{port}/sse")
            server_instance.run()
        except Exception as e:
            error_msg = f"Error in uvicorn server: {str(e)}"
            print(error_msg)
            
            # Write error to file
            error_file = os.path.join(workspace_comm_dir, "mcp_server_uvicorn_error.txt")
            with open(error_file, "w") as f:
                f.write(error_msg + "\n")
                f.write(traceback.format_exc())
        
        # Monitoring for command files in a separate thread - DISABLED for thread safety
        # def file_monitor_thread():
        # ... (skipping entire block)

            try:
                print("Starting file monitor thread...")
                
                # Create a file to track thread status
                monitor_file = os.path.join(workspace_comm_dir, "file_monitor_status.txt")
                with open(monitor_file, "w") as f:
                    f.write(f"File monitor thread started at {time.ctime()}\n")
                
                while server_running:
                    # Check each communication directory for command files
                    for comm_dir in comm_dirs:
                        try:
                            # Create directory if it doesn't exist
                            os.makedirs(comm_dir, exist_ok=True)
                            
                            # Check for message box files
                            message_file = os.path.join(comm_dir, "message_box.txt")
                            if os.path.exists(message_file):
                                try:
                                    # Create debug logs for every step
                                    debug_file = os.path.join(workspace_comm_dir, "message_box_processing.txt")
                                    with open(debug_file, "a") as f:
                                        f.write(f"\n--- Found message_box.txt at {time.ctime()} ---\n")
                                    
                                    # Read the message
                                    with open(message_file, "r") as f:
                                        message = f.read().strip()
                                    
                                    # Log the message content
                                    with open(debug_file, "a") as f:
                                        f.write(f"Message content: {message}\n")
                                    
                                    # Queue the message for display
                                    print(f"Displaying message box: {message}")
                                    
                                    # Log that we queued the message
                                    with open(debug_file, "a") as f:
                                        f.write(f"Message being processed via command approach\n")
                                    
                                    # Try to display the message directly as well
                                    try:
                                        # Use command-based approach for the most reliable display
                                        create_message_box_command(message)
                                        with open(debug_file, "a") as f:
                                            f.write(f"Command-based display triggered\n")
                                    except Exception as e:
                                        with open(debug_file, "a") as f:
                                            f.write(f"Command-based display attempt failed: {str(e)}\n")
                                    
                                    # Rename the file to avoid processing it again
                                    processed_file = os.path.join(comm_dir, f"processed_message_{int(time.time())}.txt")
                                    with open(debug_file, "a") as f:
                                        f.write(f"Renaming file to: {processed_file}\n")
                                    
                                    os.rename(message_file, processed_file)
                                    
                                    with open(debug_file, "a") as f:
                                        f.write(f"File renamed successfully\n")
                                        
                                except Exception as e:
                                    print(f"Error processing message file {message_file}: {str(e)}")
                                    
                                    # Log the error
                                    try:
                                        with open(debug_file, "a") as f:
                                            f.write(f"ERROR processing message file: {str(e)}\n")
                                            f.write(traceback.format_exc())
                                    except:
                                        pass
                            
                            # Check for command files
                            for file in os.listdir(comm_dir):
                                if file.startswith("command_") and file.endswith(".json"):
                                    command_file = os.path.join(comm_dir, file)
                                    try:
                                        # Extract the command ID from the filename
                                        command_id = file.split("_")[1].split(".")[0]
                                        
                                        # Check if we've already processed this command
                                        processed_file = os.path.join(comm_dir, f"processed_command_{command_id}.json")
                                        response_file = os.path.join(comm_dir, f"response_{command_id}.json")
                                        
                                        if os.path.exists(processed_file) or os.path.exists(response_file):
                                            continue  # Skip if already processed
                                        
                                        print(f"Processing command file: {command_file}")
                                        
                                        # Read command data
                                        try:
                                            with open(command_file, "r") as f:
                                                command_data = json.load(f)
                                            
                                            command = command_data.get("command")
                                            params = command_data.get("params", {})
                                            
                                            print(f"Processing command {command_id}: {command} with params {params}")
                                            
                                            result = None
                                            
                                            # Handle the command
                                            if command == "list_resources":
                                                # Get available resources
                                                resources = [
                                                    "fusion://active-document-info",
                                                    "fusion://design-structure",
                                                    "fusion://parameters"
                                                ]
                                                result = resources
                                            elif command == "list_tools":
                                                # Get available tools
                                                tools = [
                                                    {"name": "message_box", "description": "Display a message box in Fusion 360"},
                                                    {"name": "create_new_sketch", "description": "Create a new sketch on the specified plane"},
                                                    {"name": "create_parameter", "description": "Create a new parameter in the active design"}
                                                ]
                                                result = tools
                                            elif command == "list_prompts":
                                                # Get available prompts
                                                prompts = [
                                                    {"name": "create_sketch_prompt", "description": "Create a prompt for creating a sketch based on a description"},
                                                    {"name": "parameter_setup_prompt", "description": "Create a prompt for setting up parameters based on a description"}
                                                ]
                                                result = prompts
                                            elif command == "message_box":
                                                # Display a message box
                                                message = params.get("message", "")
                                                
                                                # Create debug log
                                                debug_file = os.path.join(workspace_comm_dir, "command_message_debug.txt")
                                                with open(debug_file, "a") as f:
                                                    f.write(f"Processing message_box command with: {message} at {time.ctime()}\n")
                                                
                                                # Use command-based approach for message display
                                                try:
                                                    create_message_box_command(message)
                                                    with open(debug_file, "a") as f:
                                                        f.write(f"Command-based display triggered at {time.ctime()}\n")
                                                except Exception as e:
                                                    with open(debug_file, "a") as f:
                                                        f.write(f"Command-based display attempt failed: {str(e)}\n")
                                                
                                                result = "Message processed successfully"
                                            elif command == "create_new_sketch":
                                                # Create a new sketch
                                                result = create_new_sketch(params.get("plane_name", "XY"))
                                            elif command == "create_parameter":
                                                # Create a new parameter
                                                result = create_parameter(
                                                    params.get("name", f"Param_{int(time.time()) % 10000}"),
                                                    params.get("expression", "10"),
                                                    params.get("unit", "mm"),
                                                    params.get("comment", "")
                                                )
                                            elif command == "read_resource":
                                                # Read a resource
                                                uri = params.get("uri", "")
                                                if uri == "fusion://active-document-info":
                                                    try:
                                                        doc = app.activeDocument
                                                        if doc:
                                                            result = {
                                                                "name": doc.name,
                                                                "path": doc.dataFile.name if doc.dataFile else "Unsaved",
                                                                "type": "FusionDesignDocumentType" if doc.products.itemByProductType('DesignProductType') else "Unknown"
                                                            }
                                                        else:
                                                            result = {"error": "No active document"}
                                                    except Exception as e:
                                                        result = {"error": str(e)}
                                                elif uri == "fusion://design-structure":
                                                    try:
                                                        doc = app.activeDocument
                                                        if not doc:
                                                            result = {"error": "No active document"}
                                                        else:
                                                            design = doc.products.itemByProductType('DesignProductType')
                                                            if not design:
                                                                result = {"error": "No design in document"}
                                                            else:
                                                                # Convert to adsk.fusion.Design type
                                                                fusion_design = adsk.fusion.Design.cast(design)
                                                                root_comp = fusion_design.rootComponent
                                                                
                                                                # Simplified response with just basic info
                                                                result = {
                                                                    "design_name": fusion_design.name,
                                                                    "root_component": {
                                                                        "name": root_comp.name,
                                                                        "bodies_count": root_comp.bRepBodies.count,
                                                                        "sketches_count": root_comp.sketches.count,
                                                                        "occurrences_count": root_comp.occurrences.count
                                                                    }
                                                                }
                                                    except Exception as e:
                                                        result = {"error": str(e)}
                                                elif uri == "fusion://parameters":
                                                    try:
                                                        doc = app.activeDocument
                                                        if not doc:
                                                            result = {"error": "No active document"}
                                                        else:
                                                            design = doc.products.itemByProductType('DesignProductType')
                                                            if not design:
                                                                result = {"error": "No design in document"}
                                                            else:
                                                                # Convert to adsk.fusion.Design type
                                                                fusion_design = adsk.fusion.Design.cast(design)
                                                                
                                                                params = []
                                                                if fusion_design.allParameters:
                                                                    for param in fusion_design.allParameters:
                                                                        params.append({
                                                                            "name": param.name,
                                                                            "value": param.value,
                                                                            "expression": param.expression,
                                                                            "unit": param.unit,
                                                                            "comment": param.comment
                                                                        })
                                                                
                                                                result = {"parameters": params}
                                                    except Exception as e:
                                                        result = {"error": str(e)}
                                                else:
                                                    result = {"error": f"Unknown resource URI: {uri}"}
                                            elif command == "get_prompt":
                                                # Get a prompt
                                                prompt_name = params.get("name", "")
                                                prompt_args = params.get("args", {})
                                                
                                                if prompt_name == "create_sketch_prompt":
                                                    description = prompt_args.get("description", "Default sketch")
                                                    result = {
                                                        "messages": [
                                                            {
                                                                "role": "system",
                                                                "content": "You are an expert in Fusion 360 CAD modeling. Your task is to help the user create sketches based on their descriptions.\n\nBe very specific about what planes to use and what sketch entities to create."
                                                            },
                                                            {
                                                                "role": "user",
                                                                "content": f"I want to create a sketch with these requirements: {description}\n\nPlease provide step-by-step instructions for creating this sketch in Fusion 360."
                                                            }
                                                        ]
                                                    }
                                                elif prompt_name == "parameter_setup_prompt":
                                                    description = prompt_args.get("description", "Default parameters")
                                                    result = {
                                                        "messages": [
                                                            {
                                                                "role": "system",
                                                                "content": "You are an expert in Fusion 360 parametric design. Your task is to help the user set up parameters for their design.\n\nSuggest appropriate parameters, their values, units, and purposes based on the user's description."
                                                            },
                                                            {
                                                                "role": "user",
                                                                "content": f"I want to set up parameters for: {description}\n\nWhat parameters should I create, and what values, units, and comments should they have?"
                                                            }
                                                        ]
                                                    }
                                                else:
                                                    result = {"error": f"Unknown prompt: {prompt_name}"}
                                            else:
                                                result = f"Unknown command: {command}"
                                            
                                            # Write the response
                                            with open(response_file, "w") as f:
                                                json.dump({"result": result}, f, indent=2)
                                            
                                            # Rename the command file to avoid processing it again
                                            os.rename(command_file, processed_file)
                                        except json.JSONDecodeError as e:
                                            # Handle JSON parsing error
                                            print(f"Error parsing JSON in {command_file}: {str(e)}")
                                            with open(response_file, "w") as f:
                                                json.dump({"error": f"Invalid JSON format: {str(e)}"}, f, indent=2)
                                    except Exception as e:
                                        print(f"Error processing command file {command_file}: {str(e)}")
                                        traceback.print_exc()
                                        
                                        # Try to create an error response anyway
                                        try:
                                            with open(os.path.join(comm_dir, f"response_{command_id}.json"), "w") as f:
                                                json.dump({"error": str(e)}, f, indent=2)
                                        except Exception:
                                            pass
                        except Exception as e:
                            print(f"Error processing directory {comm_dir}: {str(e)}")
                            error_file = os.path.join(workspace_comm_dir, "error.txt")
                            with open(error_file, "w") as f:
                                f.write(f"Error in file monitor for directory {comm_dir}: {str(e)}\n\n{traceback.format_exc()}")
                    
                    # Sleep to avoid high CPU usage
                    time.sleep(0.5)
            except Exception as e:
                print(f"Error in file monitor thread: {str(e)}")
                error_file = os.path.join(workspace_comm_dir, "error.txt")
                with open(error_file, "w") as f:
                    f.write(f"File Monitor Error: {str(e)}\n\n{traceback.format_exc()}")
        
        # Start the file monitor thread
        file_monitor = threading.Thread(target=file_monitor_thread)
        file_monitor.daemon = True
        file_monitor.start()
        
        # Keep thread running
        while server_running:
            time.sleep(1)
            
        # Shutdown the server
        print("Shutting down server...")
        server.should_exit = True
        
        return True
        
    except Exception as e:
        print(f"Error in MCP server: {str(e)}")
        
        # Create error file
        workspace_path = str(Path(__file__).parent.parent.parent)
        if os.path.exists(workspace_path):
            workspace_comm_dir = os.path.join(workspace_path, "mcp_comm")
            os.makedirs(workspace_comm_dir, exist_ok=True)
            error_file = os.path.join(workspace_comm_dir, "mcp_server_error.txt")
            with open(error_file, "w") as f:
                f.write(f"MCP Server Error: {str(e)}\n\n{traceback.format_exc()}")
        
        return False

# Function to start the server
def start_server():
    global server_thread
    global server_running
    
    print("Starting MCP server...")
    
    # Create workspace comm directory if it doesn't exist
    workspace_path = str(Path(__file__).parent.parent.parent)
    workspace_comm_dir = os.path.join(workspace_path, "mcp_comm")
    if os.path.exists(workspace_path):
        os.makedirs(workspace_comm_dir, exist_ok=True)
        # Create a log file
        log_file = os.path.join(workspace_comm_dir, "mcp_server_log.txt")
        with open(log_file, "w") as f:
            f.write(f"MCP Server starting at {time.ctime()}\n")
    
    # Check if MCP is installed
    is_installed, err_msgs = check_mcp_installed()
    if not is_installed:
        print("Required packages not installed. Cannot start server.")
        ui.messageBox(f"Required packages are not installed. Detailed Error:\n{err_msgs}\n\nPlease install them with:\npip install \"mcp[cli]\" uvicorn")
        return False
    
    # Check if server is already running
    if server_running and server_thread and server_thread.is_alive():
        print("MCP server is already running")
        return True
    
    # Reset server state
    server_running = True
    
    # Start server in a separate thread
    def server_thread_func():
        try:
            success = run_mcp_server()
            if not success:
                print("Failed to start MCP server")
                server_running = False
                # ui.messageBox("Failed to start MCP server. See error log for details.") # Dangerous call from background thread
                pass
        except Exception as e:
            print(f"Error in server thread: {str(e)}")
            server_running = False
            error_file = os.path.join(workspace_comm_dir, "mcp_server_error.txt")
            with open(error_file, "w") as f:
                f.write(f"MCP Server Thread Error: {str(e)}\n\n{traceback.format_exc()}")
    
    server_thread = threading.Thread(target=server_thread_func)
    server_thread.daemon = True
    server_thread.start()
    
    print("MCP server thread started")
    
    # Check if the thread is still alive
    if not server_thread.is_alive():
        print("MCP server thread stopped unexpectedly")
        server_running = False
        return False
    
    print("MCP server started successfully")
    return True

# Function to stop the server
def stop_server():
    global server_running
    
    if not server_running:
        print("MCP server is not running")
        return
    
    # Set server running flag to stop the server loop
    server_running = False
    
    global server_instance
    if server_instance:
        server_instance.should_exit = True
    
    # Wait for the thread to finish
    if server_thread and server_thread.is_alive():
        server_thread.join(timeout=2.0)
    
    print("MCP server stopped")

# Command event handlers
class MCPServerCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    
    def notify(self, args):
        try:
            # Get command inputs
            cmd = args.command
            inputs = cmd.commandInputs
            
            # Add information text
            info_input = inputs.addTextBoxCommandInput('infoInput', '', 
                'Click OK to start the MCP Server.\n\n' +
                'This will enable communication between Fusion 360 and MCP clients.\n\n' +
                'Current server status: ' + ('Running' if server_running else 'Not Running'), 
                4, True)
            
            # Events
            onExecute = MCPServerCommandExecuteHandler()
            cmd.execute.add(onExecute)
            handlers.append(onExecute)
            
            onDestroy = MCPServerCommandDestroyHandler()
            cmd.destroy.add(onDestroy)
            handlers.append(onDestroy)
        except:
            if ui:
                ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class MCPServerCommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    
    def notify(self, args):
        try:
            # Start the server
            success = start_server()
            
            # Try to show a test message directly for debugging
            mcp_comm_dir = Path(__file__).parent.parent.parent / 'mcp_comm'
            mcp_comm_dir.mkdir(exist_ok=True)
            debug_path = str(mcp_comm_dir / 'execute_debug.txt')
            with open(debug_path, "a") as f:
                f.write(f"Execute handler called at {time.ctime()}\n")
                f.write(f"Trying command-based test message\n")
            
            if success:
                try:
                    create_message_box_command("MCP Server started - Test Message")
                except:
                    pass
                
                workspace_path = str(Path(__file__).parent.parent.parent)
                workspace_path = str(Path(__file__).parent.parent.parent)
                workspace_comm_dir = os.path.join(workspace_path, "mcp_comm")
                
                # Create a startup log file
                startup_log_file = os.path.join(workspace_comm_dir, "mcp_server_startup_log.txt")
                with open(startup_log_file, "w") as f:
                    f.write(f"MCP Server started successfully at {time.ctime()}\n")
                    f.write(f"Server URL: http://127.0.0.1:3000/sse\n")
                    f.write(f"Communication directory: {workspace_comm_dir}\n")
                
                ui.messageBox("MCP Server started successfully!\n\nServer is running at http://127.0.0.1:3000/sse\n\nReady for client connections.")
            else:
                workspace_path = str(Path(__file__).parent.parent.parent)
                workspace_comm_dir = os.path.join(workspace_path, "mcp_comm")
                
                # Check for error file
                error_file = os.path.join(workspace_comm_dir, "mcp_server_error.txt")
                error_message = "Unknown error. See error log for details."
                
                if os.path.exists(error_file):
                    try:
                        with open(error_file, "r") as f:
                            error_message = f.read()
                    except:
                        pass
                
                ui.messageBox(f"Failed to start MCP Server. Error: {error_message}")
        except:
            if ui:
                ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class MCPServerCommandDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    
    def notify(self, args):
        try:
            # Clean up as needed
            pass
        except:
            if ui:
                ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

# Function to stop server on add-in stop
def stop_server_on_stop(context):
    try:
        global server_running
        
        if server_running:
            print("Stopping MCP server...")
            server_running = False
            
            # Create a shutdown log file
            workspace_path = str(Path(__file__).parent.parent.parent)
            workspace_comm_dir = os.path.join(workspace_path, "mcp_comm")
            os.makedirs(workspace_comm_dir, exist_ok=True)
            
            shutdown_log_file = os.path.join(workspace_comm_dir, "mcp_server_shutdown_log.txt")
            with open(shutdown_log_file, "w") as f:
                f.write(f"MCP Server stopped at {time.ctime()}\n")
            
            # Wait for the thread to finish
            if server_thread and server_thread.is_alive():
                server_thread.join(timeout=2.0)
            
            print("MCP server stopped")
    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

# Function to create the UI elements
def create_ui():
    try:
        # Get the command definitions
        command_definitions = ui.commandDefinitions
        
        # Create a command definition for the MCP server command
        mcp_server_cmd_def = command_definitions.itemById('MCPServerCommand')
        if not mcp_server_cmd_def:
            mcp_server_cmd_def = command_definitions.addButtonDefinition('MCPServerCommand', 'MCP Server', 'Start the MCP Server for Fusion 360')
        
        # Connect to the command created event
        on_command_created = MCPServerCommandCreatedHandler()
        mcp_server_cmd_def.commandCreated.add(on_command_created)
        handlers.append(on_command_created)
        
        # Add to the add-ins panel
        add_ins_panel = ui.allToolbarPanels.itemById('SolidScriptsAddinsPanel')
        control = add_ins_panel.controls.itemById('MCPServerCommand')
        if not control:
            add_ins_panel.controls.addCommand(mcp_server_cmd_def)
        
        print("MCP Server command added to UI")
    except:
        if ui:
            ui.messageBox('Failed to create UI:\n{}'.format(traceback.format_exc()))

# Define the required start() and stop() functions for the add-in system
def start():
    """Called when the add-in is started."""
    try:
        create_ui()
    except:
        if ui:
            ui.messageBox('Failed to initialize add-in:\n{}'.format(traceback.format_exc()))

def stop():
    """Called when the add-in is stopped."""
    try:
        # Stop the server
        stop_server_on_stop(None)
        
        # Clean up UI
        command_definitions = ui.commandDefinitions
        mcp_server_cmd_def = command_definitions.itemById('MCPServerCommand')
        if mcp_server_cmd_def:
            mcp_server_cmd_def.deleteMe()
        
        # Clean up any panels
        add_ins_panel = ui.allToolbarPanels.itemById('SolidScriptsAddinsPanel')
        control = add_ins_panel.controls.itemById('MCPServerCommand')
        if control:
            control.deleteMe()
            
        print("MCP Server add-in stopped")
    except:
        if ui:
            ui.messageBox('Failed to clean up add-in:\n{}'.format(traceback.format_exc()))

# Main entry point
def run(context):
    try:
        create_ui()
    except:
        if ui:
            ui.messageBox('Failed to run:\n{}'.format(traceback.format_exc()))

# Function to create a message box command
def create_message_box_command(message):
    try:
        mcp_comm_dir = Path(__file__).parent.parent.parent / 'mcp_comm'
        mcp_comm_dir.mkdir(exist_ok=True)
        debug_file = str(mcp_comm_dir / 'message_command_debug.txt')
        with open(debug_file, "a") as f:
            f.write(f"\nCreating message box command for: {message} at {time.ctime()}\n")
        
        # Create a unique command ID
        command_id = f"MCPMessageBox_{int(time.time() * 1000)}"
        
        # Get or create the command definition
        cmdDefs = ui.commandDefinitions
        cmdDef = cmdDefs.itemById(command_id)
        if cmdDef:
            cmdDef.deleteMe()
        
        # Create a new command definition
        cmdDef = cmdDefs.addButtonDefinition(
            command_id, 
            "MCP Message Box", 
            f"Display message: {message}", 
            ""  # No resource folder needed
        )
        
        # Connect to the command created event
        onCommandCreated = MessageBoxCommandCreatedHandler(message)
        cmdDef.commandCreated.add(onCommandCreated)
        message_command_handlers.append(onCommandCreated)
        
        with open(debug_file, "a") as f:
            f.write(f"Command definition created with ID: {command_id} at {time.ctime()}\n")
        
        # Execute the command
        cmdDef.execute()
        
        with open(debug_file, "a") as f:
            f.write(f"Command execution triggered at {time.ctime()}\n")
        
        return True
    except Exception as e:
        try:
            with open(debug_file, "a") as f:
                f.write(f"Error creating message box command: {str(e)} at {time.ctime()}\n")
                f.write(traceback.format_exc())
        except:
            pass
        return False

# Function to create a script execution command
def create_script_execution_command(script):
    try:
        mcp_comm_dir = Path(__file__).parent.parent.parent / 'mcp_comm'
        mcp_comm_dir.mkdir(exist_ok=True)
        debug_file = str(mcp_comm_dir / 'script_execute_debug.txt')
        with open(debug_file, "a") as f:
            f.write(f"\nCreating script execution command at {time.ctime()}\n")
        
        # Create a unique command ID
        command_id = f"MCPScriptExec_{int(time.time() * 1000)}"
        
        # Get or create the command definition
        cmdDefs = ui.commandDefinitions
        cmdDef = cmdDefs.itemById(command_id)
        if cmdDef:
            cmdDef.deleteMe()
        
        # Create a new command definition
        cmdDef = cmdDefs.addButtonDefinition(
            command_id, 
            "MCP Script Execution", 
            "Executing MCP Command", 
            ""
        )
        
        # Connect to the command created event
        onCommandCreated = ScriptExecuteCommandCreatedHandler(script)
        cmdDef.commandCreated.add(onCommandCreated)
        message_command_handlers.append(onCommandCreated)
        
        # Execute the command
        cmdDef.execute()
        
        return True
    except Exception as e:
        try:
            with open(debug_file, "a") as f:
                f.write(f"Error creating script execution command: {str(e)} at {time.ctime()}\n")
                f.write(traceback.format_exc())
        except:
            pass
        return False

class ScriptExecuteCommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self, script):
        super().__init__()
        self.script = script
    
    def notify(self, args):
        try:
            # Execute the script in the context of Fusion 360
            # We provide some common globals for convenience
            exec_globals = {
                'adsk': adsk,
                'app': app,
                'ui': ui,
                'design': adsk.fusion.Design.cast(app.activeProduct) if app.activeProduct else None,
            }
            exec(self.script, exec_globals)
        except Exception as e:
            mcp_comm_dir = Path(__file__).parent.parent.parent / 'mcp_comm'
            debug_file = str(mcp_comm_dir / 'script_execute_error.txt')
            with open(debug_file, "a") as f:
                f.write(f"\nError executing script at {time.ctime()}:\n{str(e)}\n")
                f.write(traceback.format_exc())

class ScriptExecuteCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self, script):
        super().__init__()
        self.script = script
    
    def notify(self, args):
        try:
            cmd = args.command
            onExecute = ScriptExecuteCommandExecuteHandler(self.script)
            cmd.execute.add(onExecute)
            message_command_handlers.append(onExecute)
        except Exception as e:
            pass

# ── Result-aware script executor ───────────────────────────────────────────────
_result_counter = 0
_result_counter_lock = threading.Lock()

def exec_script_with_result(script: str, timeout: float = 10.0) -> dict:
    """Execute a script on the Fusion UI thread and return its result dict.
    Scripts can set __result__["data"] = <json-serializable value> to pass data back.
    Returns {"status": "ok", "data": ...} or {"status": "error", "error": ..., "traceback": ...}
    """
    global _result_counter
    with _result_counter_lock:
        _result_counter += 1
        result_id = str(_result_counter)

    mcp_comm_dir = Path(__file__).parent.parent.parent / 'mcp_comm'
    mcp_comm_dir.mkdir(exist_ok=True)
    result_file = str(mcp_comm_dir / f'result_{result_id}.json')

    indented = '\n'.join('    ' + line for line in script.strip().splitlines())
    wrapped = f"""import json as __json__, traceback as __tb__
__result_file__ = {repr(result_file)}
__result__ = {{"status": "ok", "data": None}}
try:
{indented}
except Exception as __e__:
    __result__ = {{"status": "error", "error": str(__e__), "traceback": __tb__.format_exc()}}
finally:
    try:
        with open(__result_file__, "w") as __f__:
            __json__.dump(__result__, __f__)
    except Exception as __we__:
        pass
"""
    success = create_script_execution_command(wrapped)
    if not success:
        return {"status": "error", "error": "Failed to queue script execution"}

    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(result_file):
            try:
                with open(result_file, 'r') as f:
                    result = json.load(f)
                try:
                    os.remove(result_file)
                except Exception:
                    pass
                return result
            except Exception:
                pass
        time.sleep(0.1)

    return {"status": "error", "error": f"Script timed out after {timeout}s"}

# Simple function to directly try showing a message box

def show_message_box(message):
    """Display a message box in Fusion 360."""
    try:
        # Log message for debugging
        mcp_comm_dir = Path(__file__).parent.parent.parent / 'mcp_comm'
        mcp_comm_dir.mkdir(exist_ok=True)
        debug_path = str(mcp_comm_dir / 'message_debug.txt')
        with open(debug_path, "a") as f:
            f.write(f"Trying to show message: {message} at {time.ctime()}\n")
        
        # Use the command-based approach
        success = create_message_box_command(message)
        
        # Log result
        with open(debug_path, "a") as f:
            f.write(f"Command creation result: {success} at {time.ctime()}\n")
        
        return success
    except Exception as e:
        # Log failure
        with open(debug_path, "a") as f:
            f.write(f"Error showing message box: {str(e)} at {time.ctime()}\n")
        return False

# Add a Command Handler for showing message boxes
class MessageBoxCommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self, message):
        super().__init__()
        self.message = message
    
    def notify(self, args):
        try:
            # Display the message
            mcp_comm_dir = Path(__file__).parent.parent.parent / 'mcp_comm'
            mcp_comm_dir.mkdir(exist_ok=True)
            debug_file = str(mcp_comm_dir / 'message_command_debug.txt')
            with open(debug_file, "a") as f:
                f.write(f"MessageBoxCommand executing for: {self.message} at {time.ctime()}\n")
            
            # Show the message box in the UI thread
            ui.messageBox(self.message, "Fusion MCP Message")
            
            with open(debug_file, "a") as f:
                f.write(f"Message box displayed successfully at {time.ctime()}\n")
        except Exception as e:
            with open(debug_file, "a") as f:
                f.write(f"Error in command handler: {str(e)} at {time.ctime()}\n")
                f.write(traceback.format_exc())

class MessageBoxCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self, message):
        super().__init__()
        self.message = message
    
    def notify(self, args):
        try:
            mcp_comm_dir = Path(__file__).parent.parent.parent / 'mcp_comm'
            mcp_comm_dir.mkdir(exist_ok=True)
            debug_file = str(mcp_comm_dir / 'message_command_debug.txt')
            with open(debug_file, "a") as f:
                f.write(f"MessageBoxCommand created for: {self.message} at {time.ctime()}\n")
            
            # Get the command
            cmd = args.command
            
            # Connect to the execute event
            onExecute = MessageBoxCommandExecuteHandler(self.message)
            cmd.execute.add(onExecute)
            message_command_handlers.append(onExecute)
            
            # Set command properties
            cmd.isEnabled = True
            cmd.isVisible = False
            
            with open(debug_file, "a") as f:
                f.write(f"Command handlers set up at {time.ctime()}\n")
        except Exception as e:
            with open(debug_file, "a") as f:
                f.write(f"Error in command created handler: {str(e)} at {time.ctime()}\n")
                f.write(traceback.format_exc()) 