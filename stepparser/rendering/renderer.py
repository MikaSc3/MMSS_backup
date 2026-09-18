# ============================================
# src/rendering/renderer.py
# ============================================
from typing import List, Tuple, Callable, Any
from enum import Enum
import os
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.stats import entropy as scipy_entropy
import threading
import time
from OCC.Core.TopoDS import TopoDS_Shape
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCC.Core.AIS import AIS_Shape
from OCC.Core.gp import gp_Trsf, gp_Vec, gp_Pnt, gp_Pln, gp_Ax1, gp_Dir
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Section
from OCC.Core.GProp import GProp_GProps
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCC.Core.BRepLib import breplib
from OCC.Core.TopTools import TopTools_ListOfShape
from OCC.Display.SimpleGui import init_display
from OCC.Core.Graphic3d import Graphic3d_MaterialAspect, Graphic3d_NOM_PLASTIC

from ..core.assembly import Assembly
from ..core.part import Part
from ..core.data_classes import BoundingBox, Color


class ViewType(Enum):
    ISOMETRIC = "isometric"
    FRONT = "front"
    TOP = "top"
    SIDE = "side"
    CUSTOM = "custom"

class View:
    """Defines camera position and orientation for rendering"""
    
    def __init__(self, view_type: ViewType, eye_position: Tuple[float, float, float],
                 target: Tuple[float, float, float] = (0, 0, 0),
                 up_vector: Tuple[float, float, float] = (0, 0, 1)):
        self.view_type = view_type
        self.eye_position = eye_position
        self.target = target
        self.up_vector = up_vector
    
    @staticmethod
    def create_standard_views(bbox: BoundingBox) -> List['View']:
        """Create standard views based on bounding box"""
        center = bbox.get_center()
        diagonal = bbox.get_diagonal()
        distance = diagonal * 2  # Camera distance from center
        
        views = [
            # Isometric 1 (Front-Left-Top - above left corner)
            View(ViewType.ISOMETRIC, 
                 (center[0] - distance, center[1] + distance, center[2] + distance),
                 center, (0, 0, 1)),
            
            # Isometric 2 (Front-Left-Bottom - below left corner)
            View(ViewType.ISOMETRIC, 
                 (center[0] - distance, center[1] + distance, center[2] - distance),
                 center, (0, 0, 1)),

            # Isometric 3 (Front-Left-Bottom - below left corner)
            View(ViewType.ISOMETRIC, 
                 (center[0] + distance, center[1] - distance, center[2] - distance),
                 center, (0, 0, 1)),
            
            # Isometric 3 (Front-Left-Bottom - below left corner)
            View(ViewType.ISOMETRIC, 
                 (center[0] - distance, center[1] + distance, center[2] - distance),
                 center, (0, 0, 1))
        ]
        
        return views

class Renderer:
    """Handles all rendering operations"""
    
    def __init__(self, output_resolution: Tuple[int, int] = (1920, 1080), 
                 edge_width: float = 1.0,
                 headless_mode: bool = True,
                 render_timeout: float = 5.0):
        """
        Initialize renderer.
        
        Args:
            output_resolution: Output image resolution (width, height)
            edge_width: Edge line width for rendering
            headless_mode: If True, uses minimal display cleanup to avoid hanging on complex geometry.
                          If False, recreates display every 3 renders for additional stability.
                          Recommended: True for batch processing, False for troubleshooting.
            render_timeout: Maximum time in seconds for a single render operation.
                           If exceeded, the render is skipped. Default: 5.0 seconds
        """
        self.resolution = output_resolution
        self.display = None
        self.background_color = (1.0, 1.0, 1.0)  # White
        self.edge_width = edge_width  # Edge line width
        self.headless_mode = headless_mode
        self.render_timeout = render_timeout
        self._render_count = 0  # Track number of renders


    def initialize_display(self):
        """Initialize OCC display"""
        if not self.display:
            try:
                # Cleanup before initializing
                import gc
                gc.collect()
                
                self.display, self.start_display, self.add_menu, self.add_function_to_menu = init_display()
                self.display.View.SetBackgroundColor(Quantity_Color(*self.background_color, Quantity_TOC_RGB))

                # Hide the Win32/WNT window immediately.
                # OCC with the pyqt6 backend creates a real Win32 window that normally
                # requires a Qt event loop (GetMessage/DispatchMessage) to process
                # WM_PAINT/WM_SIZE messages.  Without an event loop, any OCC call that
                # internally sends window messages (FitAll, Redraw, UpdateCurrentViewer)
                # will block indefinitely.  Unmap() hides the window so it stops
                # receiving those messages.
                try:
                    win = self.display.View.Window()
                    if win is not None:
                        win.Unmap()
                        print("[Renderer] Win32 window unmapped — no event loop needed.", flush=True)
                except Exception as hide_err:
                    print(f"[Renderer] Could not unmap Win32 window: {hide_err}", flush=True)

                # Configure rendering parameters for better transparency
                try:
                    render_params = self.display.View.ChangeRenderingParams()
                    render_params.TransparencyMethod = 1  # Use blend method
                    render_params.NbMsaaSamples = 4  # Anti-aliasing
                except Exception as e:
                    print(f"[DEBUG] Could not set rendering params: {e}")
                
            except Exception as e:
                print(f"[ERROR] Failed to initialize display: {e}")
                raise
    
    
    def _initialize_windowed_display(self):
        """This method is deprecated - kept for compatibility"""
        self.initialize_display()
    
    
    def _initialize_headless_display(self):
        """This method is deprecated - kept for compatibility"""
        self.initialize_display()
    
    
    def _reset_display_aggressive(self):
        """Reset display state between renders.

        The display is intentionally NEVER recreated here. Recreating the WNT window
        after each render accumulated HWND handles and caused wglMakeCurrent() failures.
        Instead, we use ToPixMap() for image capture (FBO-based, WGL-context-safe) and
        simply remove all AIS objects from the context between renders.
        """
        import gc
        try:
            if self.display:
                # RemoveAll truly removes AIS objects from the context (vs EraseAll which
                # only hides them). Prevents unbounded memory growth across many renders.
                try:
                    # False = do NOT trigger UpdateCurrentViewer / Redraw
                    # (True would send Win32 messages that block without an event loop)
                    self.display.Context.RemoveAll(False)
                except Exception:
                    try:
                        self.display.EraseAll()
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Display cleanup] Reset issue: {e}", flush=True)
        gc.collect()

    def _destroy_current_window(self):
        """No-op: display is never recreated, so no window destruction needed."""
        pass

    def _recreate_display_if_needed(self):
        """No-op: display is created once in initialize_display() and reused for the
        lifetime of this Renderer instance.

        Previously this method recreated the display + Win32 WNT window after each render,
        which caused wglMakeCurrent() failures due to accumulating HWND/WGL handles.
        With ToPixMap()-based image capture the display context is stable across renders.
        """
        pass

    
    def _run_with_timeout(self, operation: Callable, timeout: float = 10.0, operation_name: str = "operation") -> bool:
        """Run an operation in a daemon thread with a real timeout.
        
        NOTE: This cannot interrupt an OCC C++ crash, but it WILL handle hangs/infinite loops.
        If the operation crashes the C++ layer, the whole process will still die.
        
        Args:
            operation: Callable to execute
            timeout: Real timeout in seconds - thread is abandoned after this
            operation_name: Name of operation for logging
        
        Returns:
            bool: True if operation completed successfully within timeout
        """
        import threading
        result = {"done": False, "exception": None}
        
        def target():
            try:
                operation()
                result["done"] = True
            except Exception as e:
                result["exception"] = e
        
        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(timeout)
        
        if result["exception"]:
            print(f"[Error] {operation_name} failed: {result['exception']}")
            return False
        if not result["done"]:
            print(f"[TIMEOUT] {operation_name} exceeded {timeout}s - skipping")
            return False
        return True

    
    def render_assembly(self, assembly: Assembly, view: View, 
                       output_path: str, transparency: float = 0.0):
        """Render assembly with all parts colored"""
        self.initialize_display()
        self.display.EraseAll()
        
        # Add all parts to display
        all_parts = assembly.get_all_parts()
        for part in all_parts:
            self._display_part(part, transparency)
        
        # Set camera
        self._set_view(view)
        
        # Render and save
        self._save_image(output_path)
    
    def render_assembly_step(self, assembly: Assembly, part_ids: List[str], 
                            view: View, output_path: str, transparency: float = 0.0):
        """Render specific parts from assembly (for incremental assembly sequence)
        
        Args:
            assembly: Full assembly object
            part_ids: List of part IDs to render (e.g., ['part_001', 'part_003'])
            view: Camera view
            output_path: Output PNG path
            transparency: Transparency value (0.0 = opaque, 1.0 = fully transparent)
        """
        self.initialize_display()
        self.display.EraseAll()
        
        # Get all parts from assembly
        all_parts = assembly.get_all_parts()
        
        # Filter parts by ID
        parts_to_render = [p for p in all_parts if p.part_id in part_ids]
        
        if not parts_to_render:
            raise ValueError(f"No parts found for IDs: {part_ids}")
        
        # Display filtered parts with their original colors (from BOM)
        for part in parts_to_render:
            self._display_part(part, transparency=transparency)
        
        # Set camera
        self._set_view(view)
        
        # Render and save
        self._save_image(output_path)
    
    def render_part_standalone(self, part: Part, view: View, output_path: str, transparency: float = 0.0):
        """Render single part"""
        self.initialize_display()
        self.display.EraseAll()
        
        self._display_part(part, transparency=transparency)
        self._set_view(view)
        self._save_image(output_path)
    
    def render_part_standalone_section_view(self, part: Part, output_folder: str, 
                                           line_color: Color = None):
        """Render part section views through center of mass in XY, XZ, YZ planes"""
        # Get center of mass
        props = GProp_GProps()
        brepgprop.VolumeProperties(part.shape, props)
        com = props.CentreOfMass()
        com_point = gp_Pnt(com.X(), com.Y(), com.Z())
        
        # Get bounding box for camera distance calculation
        bbox = part.geometry_data.bounding_box if part.geometry_data else None
        if bbox:
            center = bbox.get_center()
            diagonal = bbox.get_diagonal()
            distance = diagonal * 1.5
        else:
            center = (com.X(), com.Y(), com.Z())
            distance = 100
        
        # Define cutting planes and corresponding views through COM
        plane_configs = {
            'xy': {
                'plane': gp_Pln(com_point, gp_Dir(0, 0, 1)),  # XY plane (normal in Z)
                'view': View(ViewType.TOP, 
                           (center[0], center[1], center[2] + distance),  # Look down from above
                           center, (0, 1, 0))  # Y-axis as up vector
            },
            'xz': {
                'plane': gp_Pln(com_point, gp_Dir(0, 1, 0)),  # XZ plane (normal in Y)
                'view': View(ViewType.FRONT,
                           (center[0], center[1] - distance, center[2]),  # Look from front
                           center, (0, 0, 1))  # Z-axis as up vector
            },
            'yz': {
                'plane': gp_Pln(com_point, gp_Dir(-1, 0, 0)),  # YZ plane (normal inverted to -X)
                'view': View(ViewType.SIDE,
                           (center[0] - distance, center[1], center[2]),  # Look from side (inverted direction)
                           center, (0, 0, 1))  # Z-axis as up vector
            }
        }
        
        # Default line color if not provided
        if line_color is None:
            line_color = Color(255, 0, 0)  # Red
        
        # Create section views for each plane
        for plane_name, config in plane_configs.items():
            try:
                # Create section
                section_algo = BRepAlgoAPI_Section(part.shape, config['plane'])
                section_algo.Build()
                
                if section_algo.IsDone():
                    section_shape = section_algo.Shape()
                    
                    # Initialize display for this section
                    self.initialize_display()
                    self.display.EraseAll()
                    
                    # Display original part as transparent
                    self._display_part(part, transparency=0.0)
                    
                    # Display section lines
                    self._display_shape(section_shape, line_color, transparency=0.0)
                    
                    # Set view parallel to cutting plane
                    self._set_view(config['view'])
                    
                    # Save section view
                    output_path = os.path.join(output_folder, f"{part.name}-section_{plane_name}.png")
                    self._save_image(output_path)
                    
                    print(f"Saved section view: {output_path}")
                else:
                    print(f"[WARNING] Section creation failed for {plane_name} plane")
                    
            except Exception as e:
                print(f"[ERROR] Failed to create {plane_name} section view: {e}")
    
    def render_part_highlighted_in_assembly(self, assembly: Assembly, 
                                           highlighted_part: Part,
                                           view: View, output_path: str):
        """Render assembly with one part highlighted, others dimmed"""
        self.initialize_display()
        self.display.EraseAll()
        
        all_parts = assembly.get_all_parts()
        highlight_color = Color(255, 0, 255)  # magenta
        base_color = Color(150, 150, 150)  # magenta
        
        for part in all_parts:
            if part.part_id == highlighted_part.part_id:
                # Highlight this part
                self._display_part(part, transparency=0.0, override_color=highlight_color)
            else:
                # Dim other parts
                self._display_part(part, transparency=0.8, override_color = base_color)
        
        self._set_view(view)
        self._save_image(output_path)
    
    def render_explosion_view(self, assembly: Assembly, view: View, 
                              output_path: str, explosion_factor: float = 4.0, transparency: float = 0.0,
                              part_ids: List[str] = None):
        """
        Render exploded assembly
        Parts explode radially from center
        Subassemblies explode as groups
        
        Args:
            assembly: Assembly to render
            view: Camera view
            output_path: Output PNG path
            explosion_factor: How far to explode parts (2.0 = 2x distance from center)
            transparency: Transparency value (0.0 = opaque, 1.0 = fully transparent)
            part_ids: Optional list of part IDs to render. If None, renders all parts.
        """
        self.initialize_display()
        self.display.EraseAll()
        
        center = assembly.bounding_box.get_center()
        
        # Determine which parts to render
        if part_ids:
            # Render specific parts (for incremental assembly sequence)
            all_parts = assembly.get_all_parts()
            parts_to_render = [p for p in all_parts if p.part_id in part_ids]
        else:
            # Render all parts (original behavior)
            parts_to_render = assembly.get_all_parts()
        
        # Explode each part individually
        for part in parts_to_render:
            exploded_shape = self._explode_shape(part.shape, center, explosion_factor)
            self._display_shape(exploded_shape, part.color, transparency=transparency)
        
        self._set_view(view)
        self._save_image(output_path)
    
    def calculate_image_entropy(self, image_path: str) -> float:
        """Calculate Shannon entropy of rendered image to quantify information content.
        
        Higher entropy = more distributed, diverse visual information (more parts/regions visible)
        Lower entropy = concentrated information (fewer parts or mostly uniform areas)
        
        Args:
            image_path: Path to the rendered PNG image
        
        Returns:
            float: Shannon entropy value (bits)
        """
        try:
            # Load image and convert to grayscale for entropy calculation
            img = Image.open(image_path).convert('L')
            img_array = np.array(img)
            
            # Flatten and normalize pixel values to 0-255 range
            pixels = img_array.flatten()
            
            # Calculate histogram (probability distribution of pixel values)
            hist, _ = np.histogram(pixels, bins=256, range=(0, 256))
            
            # Normalize histogram to probabilities
            p = hist / np.sum(hist)
            
            # Remove zero probabilities (log of zero is undefined)
            p = p[p > 0]
            
            # Calculate Shannon entropy: -sum(p_i * log2(p_i))
            image_entropy = -np.sum(p * np.log2(p))
            
            return float(image_entropy)
        
        except Exception as e:
            print(f"[WARNING] Could not calculate entropy for {image_path}: {e}")
            return 0.0
    
    def _perform_section_cut(
        self,
        part_shape: TopoDS_Shape,
        cut_box: TopoDS_Shape,
        geom_diagonal: float = 1.0,
    ) -> "TopoDS_Shape | None":
        """Boolean cut with geometry-scaled fuzzy tolerance, full error checking
        and BRepLib.BuildCurves3d() rebuild.

        Improvements over bare BRepAlgoAPI_Cut(S1, S2):
          - SetFuzzyValue scaled to geometry size: avoids silent failures on
            near-coplanar / nearly-touching faces (very common in STEP assemblies).
          - HasErrors() check in addition to IsDone() for early failure detection.
          - BRepLib.BuildCurves3d() rebuilds all 3-D edge curves after the cut
            which prevents Z-fighting artefacts and missing cap faces on the
            cut surface.
          - Builder-style API (SetArguments/SetTools) keeps the algo object
            properly scoped so del cut_algo actually releases OCC memory.

        Args:
            part_shape:     The shape to cut.
            cut_box:        Cutting tool shape (the removal volume).
            geom_diagonal:  Overall scene diagonal used to scale the fuzzy value.

        Returns:
            Cut TopoDS_Shape if successful, None otherwise (caller should fall
            back to displaying the original part).
        """
        # Scale fuzzy tolerance to geometry size; clamp to [1e-6, 1e-3]
        fuzzy = max(1e-6, min(geom_diagonal * 1e-5, 1e-3))
        try:
            cut_algo = BRepAlgoAPI_Cut()
            args = TopTools_ListOfShape()
            args.Append(part_shape)
            tools = TopTools_ListOfShape()
            tools.Append(cut_box)
            cut_algo.SetArguments(args)
            cut_algo.SetTools(tools)
            cut_algo.SetFuzzyValue(fuzzy)
            cut_algo.SetRunParallel(False)
            cut_algo.Build()

            if not cut_algo.IsDone():
                print(f"[WARNING] BRepAlgoAPI_Cut: IsDone=False (fuzzy={fuzzy:.2e})")
                del cut_algo
                return None

            if cut_algo.HasErrors():
                print(f"[WARNING] BRepAlgoAPI_Cut: HasErrors=True (fuzzy={fuzzy:.2e})")
                del cut_algo
                return None

            result = cut_algo.Shape()
            del cut_algo

            # Rebuild all 3-D curves on the result shape.  This is required
            # after boolean operations: the BRep kernel may leave pcurve-only
            # edges whose 3-D counterparts are stale, leading to Z-fighting and
            # 'ghost' faces in the OpenGL display.
            try:
                breplib.BuildCurves3d(result)
            except Exception as _e:
                print(f"[DEBUG] BRepLib.BuildCurves3d: {_e}")

            return result

        except Exception as exc:
            print(f"[WARNING] _perform_section_cut exception: {exc}")
            return None

    def render_section_view(self, assembly: Assembly, part_ids: List[str], 
                           output_path: str, transparency: float = 0.0, reference_part_id: str = None):
        """Render XY section view (from top-down) by cutting at z midplane of reference part.
        
        Creates a cutting plane at the z-midpoint of the reference part (or last part in sequence).
        Renders all parts in part_ids. Useful for before/after comparisons where cutting plane should stay fixed.
        
        Args:
            assembly: Full assembly object
            part_ids: List of part IDs to render (e.g., ['part_001', 'part_003'])
            output_path: Output PNG path
            transparency: Transparency value (0.0 = opaque, 1.0 = fully transparent)
            reference_part_id: Part ID whose bbox should define the cutting plane. If None, uses last in part_ids.
            output_path: Output PNG path
            transparency: Transparency value (0.0 = opaque, 1.0 = fully transparent)
        """
        self.initialize_display()
        self.display.EraseAll()
        
        # Get all parts from assembly
        all_parts = assembly.get_all_parts()
        
        # Filter parts by ID
        parts_to_render = [p for p in all_parts if p.part_id in part_ids]
        
        if not parts_to_render:
            raise ValueError(f"No parts found for IDs: {part_ids}")
        
        # Compute combined bounding box of selected parts
        all_mins = []
        all_maxs = []
        for part in parts_to_render:
            if part.geometry_data and part.geometry_data.bounding_box:
                bbox = part.geometry_data.bounding_box
                all_mins.append(bbox.min_point)
                all_maxs.append(bbox.max_point)
        
        # Determine which part defines the cutting plane
        if reference_part_id is None:
            reference_part_id = part_ids[-1]  # Default to last in sequence
        
        # Get the reference part for cutting plane calculation
        all_parts = assembly.get_all_parts()
        reference_part = next((p for p in all_parts if p.part_id == reference_part_id), None)
        if not reference_part:
            raise ValueError(f"Reference part not found: {reference_part_id}")
        
        # Calculate cutting plane from reference part
        reference_bbox = reference_part.geometry_data.bounding_box
        center_z = (reference_bbox.min_point[2] + reference_bbox.max_point[2]) / 2.0
        
        # Get overall XY bounds for camera positioning
        min_x = min(p[0] for p in all_mins)
        min_y = min(p[1] for p in all_mins)
        min_z = min(p[2] for p in all_mins)
        max_x = max(p[0] for p in all_maxs)
        max_y = max(p[1] for p in all_maxs)
        max_z = max(p[2] for p in all_maxs)
        
        # Create cutting box at absolute z=center_z extending upward
        # Use tight margin based on actual geometry to avoid OCC Boolean kernel instability
        # huge_margin of 100000 caused C++ crashes due to numerical precision issues
        geom_diagonal = ((max_x - min_x)**2 + (max_y - min_y)**2 + (max_z - min_z)**2)**0.5
        margin = max(geom_diagonal * 0.5, 10.0)  # At least 10 units, max 50% of diagonal
        
        cut_box = BRepPrimAPI_MakeBox(
            gp_Pnt(min_x - margin, min_y - margin, center_z),  # Start at cutting plane Z
            2 * margin + (max_x - min_x),  # Width covers all parts + margin
            2 * margin + (max_y - min_y),  # Depth covers all parts + margin
            margin + (max_z - center_z)    # Height extends upward from cutting plane
        ).Shape()
        
        # Apply boolean cut to each part and display result.
        # _perform_section_cut uses: geometry-scaled fuzzy tolerance,
        # IsDone+HasErrors checks, and BRepLib.BuildCurves3d() curve rebuild.
        import gc
        for part in parts_to_render:
            try:
                cut_result = [None]
                
                # Calculate fuzzy value based on THIS PART's size, not assembly size
                # This ensures small parts are cut with appropriate precision
                if part.geometry_data and part.geometry_data.bounding_box:
                    part_bbox = part.geometry_data.bounding_box
                    part_diagonal = ((part_bbox.max_point[0] - part_bbox.min_point[0])**2 +
                                    (part_bbox.max_point[1] - part_bbox.min_point[1])**2 +
                                    (part_bbox.max_point[2] - part_bbox.min_point[2])**2)**0.5
                else:
                    part_diagonal = geom_diagonal  # Fallback to assembly diagonal
                
                def perform_cut():
                    cut_result[0] = self._perform_section_cut(
                        part.shape, cut_box, geom_diagonal=part_diagonal
                    )

                if self._run_with_timeout(perform_cut, timeout=5.0, operation_name=f"Section XY cut for {part.part_id}"):
                    if cut_result[0] is not None:
                        self._display_shape(cut_result[0], part.color, transparency=transparency)
                    else:
                        print(f"[FALLBACK] Section XY cut failed for {part.part_id}, displaying original")
                        self._display_part(part, transparency=transparency)
                else:
                    print(f"[FALLBACK] Section XY cut timed out for {part.part_id}, displaying original")
                    self._display_part(part, transparency=transparency)

                gc.collect()

            except Exception as e:
                print(f"[WARNING] Exception during section XY cut for {part.part_id}: {e}")
                self._display_part(part, transparency=transparency)
                gc.collect()

        # Set camera to top-down view (looking straight down at XY plane)
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0

        # Create top-down view
        diagonal = ((max_x - min_x)**2 + (max_y - min_y)**2)**0.5
        camera_height = center_z + diagonal * 1.5  # Camera far above

        top_down_view = View(
            ViewType.TOP,
            (center_x, center_y, camera_height),  # Camera looking straight down
            (center_x, center_y, center_z),  # Look at section plane
            (0, 1, 0)  # Y-axis points up
        )

        self._set_view(top_down_view)

        # No explicit Redraw/UpdateCurrentViewer — View.Dump() renders internally.
        self._save_image_with_entropy(output_path)
    
    def render_section_view_xz(self, assembly: Assembly, part_ids: List[str], 
                               output_path: str, transparency: float = 0.0, reference_part_id: str = None):
        """Render XZ section view (side view) by cutting at y midplane of reference part.
        
        Creates a cutting plane at the y-midpoint of the reference part (or last part in sequence).
        Renders all parts in part_ids. Useful for before/after comparisons where cutting plane should stay fixed.
        
        Args:
            assembly: Full assembly object
            part_ids: List of part IDs to render (e.g., ['part_001', 'part_003'])
            output_path: Output PNG path
            transparency: Transparency value (0.0 = opaque, 1.0 = fully transparent)
            reference_part_id: Part ID whose bbox should define the cutting plane. If None, uses last in part_ids.
        
        Args:
            assembly: Full assembly object
            part_ids: List of part IDs to render (e.g., ['part_001', 'part_003'])
            output_path: Output PNG path
            transparency: Transparency value (0.0 = opaque, 1.0 = fully transparent)
        """
        self.initialize_display()
        self.display.EraseAll()
        
        # Get all parts from assembly
        all_parts = assembly.get_all_parts()
        
        # Filter parts by ID
        parts_to_render = [p for p in all_parts if p.part_id in part_ids]
        
        if not parts_to_render:
            raise ValueError(f"No parts found for IDs: {part_ids}")
        
        # Compute combined bounding box of selected parts
        all_mins = []
        all_maxs = []
        for part in parts_to_render:
            if part.geometry_data and part.geometry_data.bounding_box:
                bbox = part.geometry_data.bounding_box
                all_mins.append(bbox.min_point)
                all_maxs.append(bbox.max_point)
        
        if not all_mins:
            raise ValueError("No bounding box data for parts")
        
        # Determine which part defines the cutting plane
        if reference_part_id is None:
            reference_part_id = part_ids[-1]  # Default to last in sequence
        
        # Get the reference part for cutting plane calculation
        all_parts = assembly.get_all_parts()
        reference_part = next((p for p in all_parts if p.part_id == reference_part_id), None)
        if not reference_part:
            raise ValueError(f"Reference part not found: {reference_part_id}")
        
        # Calculate cutting plane from reference part
        reference_bbox = reference_part.geometry_data.bounding_box
        center_y = (reference_bbox.min_point[1] + reference_bbox.max_point[1]) / 2.0
        
        # Get overall bounds for camera positioning
        min_x = min(p[0] for p in all_mins)
        min_y = min(p[1] for p in all_mins)
        min_z = min(p[2] for p in all_mins)
        max_x = max(p[0] for p in all_maxs)
        max_y = max(p[1] for p in all_maxs)
        max_z = max(p[2] for p in all_maxs)
        
        # Create cutting box at absolute y=center_y extending upward
        # Use tight margin based on actual geometry to avoid OCC Boolean kernel instability
        geom_diagonal = ((max_x - min_x)**2 + (max_y - min_y)**2 + (max_z - min_z)**2)**0.5
        margin = max(geom_diagonal * 0.5, 10.0)
        
        cut_box = BRepPrimAPI_MakeBox(
            gp_Pnt(min_x - margin, center_y, min_z - margin),  # Start at cutting plane Y
            2 * margin + (max_x - min_x),  # Width covers all parts + margin
            margin + (max_y - center_y),   # Extends beyond max Y from cutting plane
            2 * margin + (max_z - min_z)   # Depth covers all parts + margin
        ).Shape()
        
        # Apply boolean cut to each part and display result.
        import gc
        for part in parts_to_render:
            try:
                cut_result = [None]
                
                # Calculate fuzzy value based on THIS PART's size, not assembly size
                # This ensures small parts are cut with appropriate precision
                if part.geometry_data and part.geometry_data.bounding_box:
                    part_bbox = part.geometry_data.bounding_box
                    part_diagonal = ((part_bbox.max_point[0] - part_bbox.min_point[0])**2 +
                                    (part_bbox.max_point[1] - part_bbox.min_point[1])**2 +
                                    (part_bbox.max_point[2] - part_bbox.min_point[2])**2)**0.5
                else:
                    part_diagonal = geom_diagonal  # Fallback to assembly diagonal

                def perform_cut():
                    cut_result[0] = self._perform_section_cut(
                        part.shape, cut_box, geom_diagonal=part_diagonal
                    )

                if self._run_with_timeout(perform_cut, timeout=5.0, operation_name=f"Section XZ cut for {part.part_id}"):
                    if cut_result[0] is not None:
                        self._display_shape(cut_result[0], part.color, transparency=transparency)
                    else:
                        print(f"[FALLBACK] Section XZ cut failed for {part.part_id}, displaying original")
                        self._display_part(part, transparency=transparency)
                else:
                    print(f"[FALLBACK] Section XZ cut timed out for {part.part_id}, displaying original")
                    self._display_part(part, transparency=transparency)

                gc.collect()

            except Exception as e:
                print(f"[WARNING] Exception during section XZ cut for {part.part_id}: {e}")
                self._display_part(part, transparency=transparency)
                gc.collect()

        # Set camera to side view (looking along Y-axis from above)
        center_x = (min_x + max_x) / 2.0
        center_z = (min_z + max_z) / 2.0

        diagonal = ((max_x - min_x)**2 + (max_z - min_z)**2)**0.5
        camera_distance = center_y + diagonal * 1.5  # Camera far above

        side_view = View(
            ViewType.FRONT,
            (center_x, camera_distance, center_z),  # Camera looking down along Y-axis
            (center_x, center_y, center_z),  # Look at section plane
            (0, 0, -1)  # Z-axis points down (inverted)
        )

        self._set_view(side_view)
        # No explicit Redraw/UpdateCurrentViewer — View.Dump() renders internally.
        self._save_image_with_entropy(output_path)
    
    def render_section_view_yz(self, assembly: Assembly, part_ids: List[str], 
                               output_path: str, transparency: float = 0.0, reference_part_id: str = None):
        """Render YZ section view (side view) by cutting at x midplane of reference part.
        
        Creates a cutting plane at the x-midpoint of the reference part (or last part in sequence).
        Renders all parts in part_ids. Useful for before/after comparisons where cutting plane should stay fixed.
        
        Args:
            assembly: Full assembly object
            part_ids: List of part IDs to render (e.g., ['part_001', 'part_003'])
            output_path: Output PNG path
            transparency: Transparency value (0.0 = opaque, 1.0 = fully transparent)
            reference_part_id: Part ID whose bbox should define the cutting plane. If None, uses last in part_ids.
        
        Args:
            assembly: Full assembly object
            part_ids: List of part IDs to render (e.g., ['part_001', 'part_003'])
            output_path: Output PNG path
            transparency: Transparency value (0.0 = opaque, 1.0 = fully transparent)
        """
        self.initialize_display()
        self.display.EraseAll()
        
        # Get all parts from assembly
        all_parts = assembly.get_all_parts()
        
        # Filter parts by ID
        parts_to_render = [p for p in all_parts if p.part_id in part_ids]
        
        if not parts_to_render:
            raise ValueError(f"No parts found for IDs: {part_ids}")
        
        # Compute combined bounding box of selected parts
        all_mins = []
        all_maxs = []
        for part in parts_to_render:
            if part.geometry_data and part.geometry_data.bounding_box:
                bbox = part.geometry_data.bounding_box
                all_mins.append(bbox.min_point)
                all_maxs.append(bbox.max_point)
        
        if not all_mins:
            raise ValueError("No bounding box data for parts")
        
        # Determine which part defines the cutting plane
        if reference_part_id is None:
            reference_part_id = part_ids[-1]  # Default to last in sequence
        
        # Get the reference part for cutting plane calculation
        all_parts = assembly.get_all_parts()
        reference_part = next((p for p in all_parts if p.part_id == reference_part_id), None)
        if not reference_part:
            raise ValueError(f"Reference part not found: {reference_part_id}")
        
        # Calculate cutting plane from reference part
        reference_bbox = reference_part.geometry_data.bounding_box
        center_x = (reference_bbox.min_point[0] + reference_bbox.max_point[0]) / 2.0
        
        # Get overall bounds for camera positioning
        min_x = min(p[0] for p in all_mins)
        min_y = min(p[1] for p in all_mins)
        min_z = min(p[2] for p in all_mins)
        max_x = max(p[0] for p in all_maxs)
        max_y = max(p[1] for p in all_maxs)
        max_z = max(p[2] for p in all_maxs)
        
        # Create cutting box at absolute x=center_x extending upward (inverted direction)
        # Use tight margin based on actual geometry to avoid OCC Boolean kernel instability
        geom_diagonal = ((max_x - min_x)**2 + (max_y - min_y)**2 + (max_z - min_z)**2)**0.5
        margin = max(geom_diagonal * 0.5, 10.0)
        
        cut_box = BRepPrimAPI_MakeBox(
            gp_Pnt(center_x, min_y - margin, min_z - margin),  # Start at cutting plane X
            margin + (max_x - center_x),   # Extends beyond max X from cutting plane
            2 * margin + (max_y - min_y),  # Height covers all parts + margin
            2 * margin + (max_z - min_z)   # Depth covers all parts + margin
        ).Shape()
        
        # Apply boolean cut to each part and display result.
        import gc
        for part in parts_to_render:
            try:
                cut_result = [None]
                
                # Calculate fuzzy value based on THIS PART's size, not assembly size
                # This ensures small parts are cut with appropriate precision
                if part.geometry_data and part.geometry_data.bounding_box:
                    part_bbox = part.geometry_data.bounding_box
                    part_diagonal = ((part_bbox.max_point[0] - part_bbox.min_point[0])**2 +
                                    (part_bbox.max_point[1] - part_bbox.min_point[1])**2 +
                                    (part_bbox.max_point[2] - part_bbox.min_point[2])**2)**0.5
                else:
                    part_diagonal = geom_diagonal  # Fallback to assembly diagonal

                def perform_cut():
                    cut_result[0] = self._perform_section_cut(
                        part.shape, cut_box, geom_diagonal=part_diagonal
                    )

                if self._run_with_timeout(perform_cut, timeout=5.0, operation_name=f"Section YZ cut for {part.part_id}"):
                    if cut_result[0] is not None:
                        self._display_shape(cut_result[0], part.color, transparency=transparency)
                    else:
                        print(f"[FALLBACK] Section YZ cut failed for {part.part_id}, displaying original")
                        self._display_part(part, transparency=transparency)
                else:
                    print(f"[FALLBACK] Section YZ cut timed out for {part.part_id}, displaying original")
                    self._display_part(part, transparency=transparency)

                gc.collect()

            except Exception as e:
                print(f"[WARNING] Exception during section YZ cut for {part.part_id}: {e}")
                self._display_part(part, transparency=transparency)
                gc.collect()

        # Set camera to side view (looking along X-axis at YZ plane)
        center_y = (min_y + max_y) / 2.0
        center_z = (min_z + max_z) / 2.0

        diagonal = ((max_y - min_y)**2 + (max_z - min_z)**2)**0.5
        camera_distance = center_x + diagonal * 1.5  # Camera far to the side (inverted direction)

        side_view = View(
            ViewType.SIDE,
            (camera_distance, center_y, center_z),  # Camera looking along X-axis (inverted)
            (center_x, center_y, center_z),  # Look at section plane
            (0, 0, 1)  # Z-axis points up
        )

        self._set_view(side_view)
        # No explicit Redraw/UpdateCurrentViewer — View.Dump() renders internally.
        self._save_image_with_entropy(output_path)
    
    def _explode_shape(self, shape: TopoDS_Shape, center: Tuple[float, float, float],
                       factor: float) -> TopoDS_Shape:
        """Move shape away from center by factor"""
        # Get shape center
        props = GProp_GProps()
        brepgprop.VolumeProperties(shape, props)
        shape_center = props.CentreOfMass()
        
        # Calculate explosion vector
        vec = gp_Vec(
            shape_center.X() - center[0],
            shape_center.Y() - center[1],
            shape_center.Z() - center[2]
        )
        
        # Scale by factor
        length = vec.Magnitude()
        if length > 0:
            vec.Normalize()
            vec.Multiply(length * (factor - 1))
        
        return self._translate_shape(shape, vec)
    
    def _translate_shape(self, shape: TopoDS_Shape, vec: gp_Vec) -> TopoDS_Shape:
        """Translate shape by vector"""
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
        
        trsf = gp_Trsf()
        trsf.SetTranslation(vec)
        
        transform = BRepBuilderAPI_Transform(shape, trsf, True)
        return transform.Shape()
    
    def _display_part(self, part: Part, transparency: float = 0.0, 
                     override_color: Color = None):
        """Display part with color and transparency"""
        color = override_color if override_color else part.color
        self._display_shape(part.shape, color, transparency)
    
    def _display_shape(self, shape: TopoDS_Shape, color: Color, transparency: float):
        """Display shape with color and transparency"""
        from OCC.Core.Prs3d import Prs3d_LineAspect
        from OCC.Core.Aspect import Aspect_TOL_SOLID
        
        ais_shape = AIS_Shape(shape)

        # Set color
        if color:
            r, g, b = color.to_normalized()
            ais_shape.SetColor(Quantity_Color(r, g, b, Quantity_TOC_RGB))

        # Set transparency
        if transparency > 0:
            ais_shape.SetTransparency(transparency)

        # Set edge width
        drawer = ais_shape.Attributes()
        edge_color = Quantity_Color(0.0, 0.0, 0.0, Quantity_TOC_RGB)  # Black edges
        line_aspect = Prs3d_LineAspect(edge_color, Aspect_TOL_SOLID, self.edge_width)
        drawer.SetFaceBoundaryAspect(line_aspect)
        drawer.SetFaceBoundaryDraw(True)
        ais_shape.SetAttributes(drawer)

        # Apply material with reduced shininess
        try:
            from OCC.Core.Graphic3d import Graphic3d_MaterialAspect, Graphic3d_NOM_PLASTIC
            material = Graphic3d_MaterialAspect(Graphic3d_NOM_PLASTIC)
            material.SetShininess(0.1)
            ais_shape.SetMaterial(material)
        except Exception as e:
            print(f"[DEBUG] Material application failed: {e}")

        # Display shape — pass False to suppress immediate per-shape Redraw().
        # A single explicit Redraw() is called later, after all shapes are loaded
        # and the camera is set. This prevents multiple intermediate OCC redraws
        # (one per part) from stalling the offscreen GL context.
        self.display.Context.Display(ais_shape, False)
    
    def _set_view(self, view: View):
        """Set camera position"""
        self.display.View.SetProj(
            view.eye_position[0] - view.target[0],
            view.eye_position[1] - view.target[1],
            view.eye_position[2] - view.target[2]
        )
        self.display.View.SetUp(*view.up_vector)
        # FitAll(aspect, update=False) adjusts the camera frustum without triggering
        # a Redraw or sending Win32 window messages.  View.Dump() performs its own
        # internal render when capturing the image.
        try:
            self.display.View.FitAll(0.01, False)
        except Exception:
            try:
                self.display.FitAll()
            except Exception:
                pass
    
    def _save_to_file(self, path: str) -> bool:
        """Capture the current view to a file via View.Dump().

        The display is intentionally never recreated between renders (see
        _reset_display_aggressive). With a stable, persistent WNT window the
        wglMakeCurrent() log messages emitted by OCC are harmless — they are
        OCC-internal warnings that the offscreen context switches back to the
        neutral state after the Dump, not actual errors. Images are written
        correctly on every call.
        """
        try:
            self.display.View.Dump(path)
            return True
        except Exception as e:
            print(f"[ERROR] View.Dump failed for {path}: {e}", flush=True)
            return False

    def _save_image_with_entropy(self, output_path: str) -> float:
        """Save current view to PNG and calculate Shannon entropy.
        
        Embeds entropy value in filename as: base_entropy_X_YZ.png
        Example: assembly_iso1.png -> assembly_iso1_entropy_5_23.png
        
        Args:
            output_path: Desired output PNG path (absolute or relative)
        
        Returns:
            float: Entropy value in bits
        """
        output_path_obj = Path(output_path).resolve()  # Convert to absolute path
        
        # Ensure parent directory exists
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        # Create temporary filename
        temp_path = output_path_obj.parent / f"{output_path_obj.stem}_temp.png"
        
        try:
            # Save to temporary file
            print(f"[Dump] Writing temp image: {temp_path.name}", flush=True)
            self._save_to_file(str(temp_path))
            print(f"[Dump] Done.", flush=True)
            
            # Check if temp file was actually created
            if not temp_path.exists():
                print(f"[WARNING] Temp image dump failed: {temp_path}", flush=True)
                # Fallback: save directly without entropy
                self._save_to_file(str(output_path_obj))
                self._render_count += 1
                print(f"[Reset] Starting reset after fallback dump...", flush=True)
                self._reset_display_aggressive()
                print(f"[Reset] Done.", flush=True)
                return 0.0

            # Calculate entropy
            entropy_value = self.calculate_image_entropy(str(temp_path))
            
            # Format entropy for filename (5.23 -> entropy_5_23)
            entropy_str = f"{entropy_value:.2f}".replace(".", "_")
            
            # Create final filename with entropy
            final_filename = f"{output_path_obj.stem}_entropy_{entropy_str}.png"
            final_path = output_path_obj.parent / final_filename
            
            # Remove final file if it already exists (shouldn't happen, but just in case)
            if final_path.exists():
                final_path.unlink()
            
            # Rename temp file to final
            temp_path.rename(final_path)
            
            self._render_count += 1
            self._reset_display_aggressive()
            
            return entropy_value
        
        except Exception as e:
            print(f"[WARNING] Entropy save failed for {output_path_obj}: {e}", flush=True)
            # Fallback: save directly without entropy
            try:
                self._save_to_file(str(output_path_obj))
                self._render_count += 1
                self._reset_display_aggressive()
            except Exception as e2:
                print(f"[ERROR] Direct save also failed: {e2}", flush=True)
            return 0.0
    
    def _save_image(self, output_path: str):
        """Save current view to PNG"""
        try:
            self._save_to_file(output_path)
            self._render_count += 1
            self._reset_display_aggressive()
        except Exception as e:
            print(f"[ERROR] Image save failed: {e}", flush=True)
    
    def generate_all_views(self, assembly: Assembly, output_folder: str):
        """Generate all standard views for assembly"""
        views = View.create_standard_views(assembly.bounding_box)
        view_names = ['iso1', 'iso2', 'iso3', 'iso4']
        
        for view, name in zip(views, view_names):
            output_path = os.path.join(output_folder, f"{assembly.name}-{name}.png")
            self.render_assembly(assembly, view, output_path)
        
        # Explosion view (isometric)
        explosion_path = os.path.join(output_folder, f"{assembly.name}-explosion.png")
        self.render_explosion_view(assembly, views[0], explosion_path, explosion_factor=2.0)