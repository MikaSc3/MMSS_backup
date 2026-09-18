# ============================================
# src/processor.py
# ============================================
import os
import shutil
from pathlib import Path
from typing import Union, Dict, Optional

from .core.assembly import Assembly
from .core.part import Part
from .core.data_classes import BoundingBox
from .analysis.brep_analyzer import BRepAnalyzer
from .identification.part_identifier import PartIdentifier
from .rendering.color_generator import ColorGenerator
from .rendering.renderer import Renderer, View
from .io.step_loader import StepLoader
from .io.metadata_manager import MetadataManager
from .io.sanity_check import SanityChecker

class StepProcessor:
    """
    Main orchestrator for STEP file processing
    Coordinates all analysis, rendering, and output generation
    """
    
    def __init__(self, input_folder: str, output_folder: str, 
                 skip_if_processed: bool = True, color_mode: str = "geometry",
                 transparency_values: list = None, edge_width: float = 1.0,
                 headless_mode: bool = False):
        """
        Args:
            input_folder: Path to folder containing STEP files
            output_folder: Path to processed output folder
            skip_if_processed: If True, skip assemblies that already exist in output
            color_mode: Color generation mode - "geometry" or "different"
            transparency_values: List of transparency values (e.g., [0.0, 0.2]). Default: [0.0]
            edge_width: Width of edge lines in renderings. Default: 1.0
            headless_mode: If True, use headless rendering with aggressive display cleanup.
                          Recommended for complex section view rendering that hangs on some assemblies.
        """
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.skip_if_processed = skip_if_processed
        self.color_mode = color_mode
        self.transparency_values = transparency_values if transparency_values else [0.0]
        self.headless_mode = headless_mode
        
        # Initialize components
        self.loader = StepLoader()
        self.brep_analyzer = BRepAnalyzer()
        self.part_identifier = PartIdentifier()
        self.color_generator = ColorGenerator()
        self.renderer = Renderer(edge_width=edge_width, headless_mode=headless_mode)
        self.metadata_manager = MetadataManager()
        self.sanity_check = SanityChecker()
        self.reset = Reset(self)
        
        if headless_mode:
            print(f"\n[HEADLESS MODE] Enabled - Display will reset aggressively after each render")
            print(f"[HEADLESS MODE] Recommended for assemblies with complex section views")
    
    def process_step_file(self, step_file_path: str):
        """
        Main processing pipeline for a single STEP file
        """
        print(f"\n{'='*80}")
        print(f"Processing: {step_file_path}")
        print(f"{'='*80}\n")
        
        # Get assembly name
        assembly_name = Path(step_file_path).stem
        
        # Check if already processed
        if self.skip_if_processed:
            if self.metadata_manager.check_if_processed(assembly_name, self.output_folder):
                print(f"Assembly '{assembly_name}' already processed. Skipping.")
                return
        
        try:
            # Step 1: Load STEP file
            print("\n[1/8] Loading STEP file...")
            root_assembly = self.loader.load_step_file(step_file_path)
            
            # Step 2: Analyze all parts
            print("\n[2/8] Analyzing parts...")
            self._analyze_all_parts(root_assembly)
            
            # Step 3: Identify duplicates and assign IDs
            print("\n[3/8] Identifying duplicate parts...")
            self._identify_and_assign_ids(root_assembly)
            
            # Step 4: Assign colors
            print("\n[4/8] Assigning colors...")
            all_parts = root_assembly.get_all_parts()
            if self.color_mode == "different":
                self.color_generator.generate_colors_all_different(all_parts)
            else:
                self.color_generator.assign_colors_to_parts(all_parts)
            
            # Step 5: Create output folder structure
            print("\n[5/8] Creating output structure...")
            self._create_output_structure(root_assembly, assembly_name)
            
            # Step 6: Generate all renderings
            print("\n[6/8] Generating renderings...")
            self._render_all(root_assembly)
            
            # Step 7: Generate BOMs and save metadata
            print("\n[7/8] Generating BOMs and saving metadata...")
            self._save_all_metadata(root_assembly)

                        # Step 7: Run sanity checks
            print("\n[8/8] Running sanity checks...")
            if root_assembly.output_folder:
                self._run_sanity_checks(root_assembly.output_folder)
            else:
                print("[WARNING] No output folder specified for sanity checks.")
            
            print(f"\n{'='*80}")
            print(f"Successfully processed: {assembly_name}")
            print(f"{'='*80}\n")
        
        except Exception as e:
            print(f"\n{'!'*80}")
            print(f"ERROR processing {assembly_name}: {str(e)}")
            print(f"{'!'*80}\n")
            import traceback
            traceback.print_exc()
    
    def process_all_step_files(self, color_mode: str = None):
        """Process all STEP files in input folder
        
        Args:
            color_mode: Optional color mode override - "geometry" or "different"
        """
        if color_mode:
            self.color_mode = color_mode
            print(f"Using color mode: {self.color_mode}")
        
        step_files = list(Path(self.input_folder).glob("*.step")) + \
                    list(Path(self.input_folder).glob("*.stp"))
        
        if not step_files:
            print(f"No STEP files found in {self.input_folder}")
            return
        
        print(f"Found {len(step_files)} STEP file(s)")
        
        for step_file in step_files:
            self.process_step_file(str(step_file))
    
    def _analyze_all_parts(self, root_assembly: Assembly):
        """Analyze geometry and features for all parts"""
        all_parts = root_assembly.get_all_parts()
        
        for idx, part in enumerate(all_parts, 1):
            print(f"  Analyzing part {idx}/{len(all_parts)}: {part.name}")
            
            # BRep analysis
            part.geometry_data = self.brep_analyzer.analyze_shape(part.shape, part.name)
            
            # Get detailed BREP analysis
            part.detailed_brep_analysis = self.brep_analyzer.get_detailed_analysis(part.name)
            
            # Feature recognition (if available)
            if hasattr(self, 'feature_recognizer') and self.feature_recognizer:
                part.features = self.feature_recognizer.recognize_all_features(part.shape)
            
            print(f"    Volume: {part.geometry_data.volume:.2f}")
            print(f"    Surface Area: {part.geometry_data.surface_area:.2f}")
            print(f"    Features found: {len(part.features)}")
            
            # Print face analysis summary if available
            if part.detailed_brep_analysis and 'faces' in part.detailed_brep_analysis:
                faces = part.detailed_brep_analysis['faces'].get('details', [])
                print(f"    Face analysis: {len(faces)} faces analyzed")
        
        # Analyze assembly bounding boxes
        all_assemblies = root_assembly.get_all_assemblies()
        for assembly in all_assemblies:
            assembly.bounding_box = self._compute_assembly_bbox(assembly)
            assembly.total_volume = sum(p.geometry_data.volume 
                                       for p in assembly.get_all_parts() 
                                       if p.geometry_data)
    
    def _compute_assembly_bbox(self, assembly: Assembly) -> BoundingBox:
        """Compute bounding box encompassing all parts in assembly"""
        parts = assembly.get_all_parts()
        
        if not parts:
            return self.brep_analyzer.get_bounding_box(assembly.shape)
        
        # Get all bounding boxes
        all_mins = []
        all_maxs = []
        
        for part in parts:
            if part.geometry_data:
                bbox = part.geometry_data.bounding_box
                all_mins.append(bbox.min_point)
                all_maxs.append(bbox.max_point)
        
        # Compute overall min/max
        min_x = min(p[0] for p in all_mins)
        min_y = min(p[1] for p in all_mins)
        min_z = min(p[2] for p in all_mins)
        
        max_x = max(p[0] for p in all_maxs)
        max_y = max(p[1] for p in all_maxs)
        max_z = max(p[2] for p in all_maxs)
        
        return BoundingBox(
            min_point=(min_x, min_y, min_z),
            max_point=(max_x, max_y, max_z)
        )
    
    def _identify_and_assign_ids(self, root_assembly: Assembly):
        """Identify duplicate parts and assign unique IDs"""
        all_parts = root_assembly.get_all_parts()
        
        # Assign IDs to parts
        self.part_identifier.assign_part_ids(all_parts, prefix="part")
        
        # Compute spatial relations (after part_ids are assigned)
        print(f"  Computing spatial touching relations...")
        from stepparser.core.part import Part
        Part.compute_spatial_relations(all_parts, max_neighbors=5, bbox_threshold_mm=3.0)
        
        # Print touching relations summary
        parts_with_touching = sum(1 for p in all_parts if p.part_is_touching)
        total_touching_relations = sum(len(p.part_is_touching) for p in all_parts)
        print(f"    Parts touching other parts: {parts_with_touching}/{len(all_parts)}")
        print(f"    Total touching relations: {total_touching_relations}")
        
        # Assign IDs to assemblies
        all_assemblies = root_assembly.get_all_assemblies()
        for idx, assembly in enumerate(all_assemblies, 1):
            assembly.assembly_id = f"assy_{idx:03d}"
        
        # Print duplicate summary
        duplicate_groups = self.part_identifier.find_duplicates(all_parts)
        print(f"  Total parts: {len(all_parts)}")
        print(f"  Unique parts: {len(duplicate_groups)}")
        
        for geom_hash, parts in duplicate_groups.items():
            if len(parts) > 1:
                print(f"    {parts[0].part_id}: {len(parts)} identical copies")
    
    def _create_output_structure(self, root_assembly: Assembly, assembly_name: str):
        """Create folder structure for output files"""
        base_folder = os.path.join(self.output_folder, assembly_name)
        
        # Create folders for all assemblies
        all_assemblies = root_assembly.get_all_assemblies()
        for assembly in all_assemblies:
            # Use 'assembly_{name}' prefix for consistency, strip .STEP extension
            clean_asm_name = assembly.name.replace('.STEP', '').replace('.step', '')
            assembly_folder = os.path.join(base_folder, f"assembly_{clean_asm_name}")
            os.makedirs(assembly_folder, exist_ok=True)
            assembly.output_folder = assembly_folder
        
        # Create folders for all parts (using part_id for consistent naming)
        all_parts = root_assembly.get_all_parts()
        for part in all_parts:
            # Use part_id instead of part.name for folder naming (e.g., "part_001" instead of "Part_1")
            folder_name = part.get_effective_part_id()
            part_folder = os.path.join(base_folder, folder_name)
            os.makedirs(part_folder, exist_ok=True)
            part.output_folder = part_folder
    
    def _render_all(self, root_assembly: Assembly):
        """Generate all renderings for assembly and parts"""
        all_assemblies = root_assembly.get_all_assemblies()
        all_parts = root_assembly.get_all_parts()
        
        # Build a map of base parts for efficient copy detection
        # base_part_id -> Part object (e.g., "part_001" -> Part)
        base_parts_map: Dict[str, Part] = {}
        for part in all_parts:
            if part.part_id and "_copy" not in part.part_id:
                # Extract base ID (without _copy suffix)
                base_id = part.part_id
                base_parts_map[base_id] = part
        
        # Render each assembly
        for idx, assembly in enumerate(all_assemblies, 1):
            print(f"  Rendering assembly {idx}/{len(all_assemblies)}: {assembly.name}")
            self._render_assembly(assembly)
        
        # Render each part (or copy from base if it's a copy)
        for idx, part in enumerate(all_parts, 1):
            print(f"  Rendering part {idx}/{len(all_parts)}: {part.name}")
            self._render_part(part, root_assembly, base_parts_map)
    
    def _get_base_part_id(self, part_id: str) -> str:
        """Extract base part ID from a potentially copy ID.
        
        E.g., 'part_001_copy1' -> 'part_001'
              'part_001' -> 'part_001'
        """
        if "_copy" in part_id:
            return part_id.split("_copy")[0]
        return part_id
    
    def _copy_part_images(self, source_folder: str, target_folder: str, 
                          source_part_id: str, target_part_id: str,
                          pattern: str = "*.png") -> int:
        """Copy PNG images from source folder to target folder, renaming with target part ID.
        
        E.g., copy part_001-iso1_transp_0_0.png to part_001_copy1-iso1_transp_0_0.png
        
        Args:
            source_folder: Source folder path (e.g., part_001/)
            target_folder: Target folder path (e.g., part_001_copy1/)
            source_part_id: Original part ID (e.g., "part_001")
            target_part_id: Copy part ID (e.g., "part_001_copy1")
            pattern: Glob pattern for files to copy (default: "*.png", use "*-iso[14]_transp*.png" for standalone only)
        
        Returns:
            Number of files copied
        """
        source_path = Path(source_folder)
        target_path = Path(target_folder)
        
        if not source_path.exists():
            print(f"    WARNING: Source folder not found: {source_folder}")
            return 0
        
        target_path.mkdir(parents=True, exist_ok=True)
        
        copied_count = 0
        for png_file in source_path.glob(pattern):
            # Rename file: replace source_part_id with target_part_id in filename
            # E.g., "part_001-iso1_transp_0_0.png" -> "part_001_copy1-iso1_transp_0_0.png"
            new_name = png_file.name.replace(source_part_id, target_part_id, 1)
            target_file = target_path / new_name
            try:
                shutil.copy2(png_file, target_file)
                copied_count += 1
            except Exception as e:
                print(f"    WARNING: Failed to copy {png_file.name}: {e}")
        
        return copied_count
    
    def _render_assembly(self, assembly: Assembly):
        """Render all views of an assembly"""
        views = View.create_standard_views(assembly.bounding_box)
        view_names = ['iso1', 'iso2', 'iso3', 'iso4']
        
        # Render all views (standard + explosion) with all transparency values
        for transparency in self.transparency_values:
            # Build transparency suffix - always include for consistency
            transp_str = str(transparency).replace(".", "_")
            transp_suffix = f"_transp_{transp_str}"
            
            # Standard views
            for view, name in zip(views, view_names):
                output_path = os.path.join(assembly.output_folder, 
                                          f"{assembly.name}-{name}{transp_suffix}.png")
                self.renderer.render_assembly(assembly, view, output_path, transparency=transparency)
            
            # Explosion views (both iso1 and iso2) - use "exp" suffix instead of "explosion-"
            for view, name in zip(views, view_names):
                explosion_path = os.path.join(assembly.output_folder, 
                                             f"{assembly.name}-{name}_exp{transp_suffix}.png")
                self.renderer.render_explosion_view(assembly, view, 
                                                   explosion_path, explosion_factor=2.5, transparency=transparency)
    
    def _render_part(self, part: Part, root_assembly: Assembly, base_parts_map: Dict[str, Part] = None):
        """Render standalone part and highlighted in assembly
        
        For copy parts: 
        - Copy standalone views (iso1, iso4) from base part (they're identical)
        - BUT always render highlighted-in-assembly separately (position differs per copy!)
        
        For parts with >10 copies: skip highlighted in assembly rendering for all
        """
        part_id = part.get_effective_part_id()
        is_copy_part = "_copy" in part_id
        base_id = self._get_base_part_id(part_id) if is_copy_part else None
        
        # ===== STANDALONE VIEWS (iso1, iso4) =====
        if is_copy_part and base_parts_map and base_id in base_parts_map:
            # Copy standalone views from base (they're geometrically identical)
            base_part = base_parts_map[base_id]
            if base_part.output_folder and part.output_folder:
                copied_count = self._copy_part_images(
                    base_part.output_folder, 
                    part.output_folder,
                    source_part_id=base_id,
                    target_part_id=part_id,
                    pattern="*-iso[14]_transp*.png"  # Only iso1 and iso4
                )
                print(f"    -> Copied {copied_count} standalone views from {base_id} (renamed to {part_id})")
        else:
            # Render standalone views (base part or copy with no base map)
            if part.geometry_data and part.geometry_data.bounding_box:
                views = View.create_standard_views(part.geometry_data.bounding_box)
                view_names = ['iso1','iso4']
                
                for transparency in self.transparency_values:
                    transp_str = str(transparency).replace(".", "_")
                    transp_suffix = f"_transp_{transp_str}"
                    
                    for view, name in zip(views, view_names):
                        output_path = os.path.join(part.output_folder, 
                                                  f"{part_id}-{name}{transp_suffix}.png")
                        self.renderer.render_part_standalone(part, view, output_path, transparency=transparency)
        
        # ===== HIGHLIGHTED IN ASSEMBLY (ALWAYS PER-PART-POSITION) =====
        # RULE: Skip if more than 10 copies of this part exist (skip for ALL copies)
        skip_highlighted = part.quantity_in_assembly > 10
        
        if skip_highlighted:
            print(f"    -> Skipping highlighted-in-assembly (>10 copies exist: {part.quantity_in_assembly})")
        else:
            # Always render highlighted individually (position differs per copy!)
            highlight_path = os.path.join(part.output_folder,
                                         f"{part_id}-highlighted-in-assy-isometric.png")
            assembly_views = View.create_standard_views(root_assembly.bounding_box)
            self.renderer.render_part_highlighted_in_assembly(
                root_assembly, part, assembly_views[0], highlight_path
            )
    
    def _save_all_metadata(self, root_assembly: Assembly):
        """Save all metadata and a consolidated parts table"""
        all_assemblies = root_assembly.get_all_assemblies()
        all_parts = root_assembly.get_all_parts()
        
        # Save part metadata
        for part in all_parts:
            self.metadata_manager.save_part_metadata(part, part.output_folder)

        # Save consolidated parts table (root assembly folder)
        if not root_assembly.output_folder:
            raise ValueError("root_assembly.output_folder not set; output structure not created")
        # Strip .STEP extension from assembly name for clean filenames
        clean_name = root_assembly.name.replace('.STEP', '').replace('.step', '')
        self.metadata_manager.save_parts_table(
            all_parts,
            root_assembly.output_folder,
            filename=f"{clean_name}_BOM.csv",
        )

        # Also save a pure JSON list (no assembly header/metadata)
        self.metadata_manager.save_parts_list_json(
            all_parts,
            root_assembly.output_folder,
            filename=f"{clean_name}_BOM.json",
        )
        
        # Save assembly metadata
        for assembly in all_assemblies:
            self.metadata_manager.save_assembly_metadata(assembly, assembly.output_folder)
    
    def _run_sanity_checks(self, processed_dir: str, keywords: list = None):
        """Run sanity checks on processed assemblies."""
        SanityChecker.check_assemblies(processed_dir, keywords)

class Reset:
    """
    Handles resetting of all caches and states for the StepProcessor.
    """
    def __init__(self, processor):
        self.processor = processor

    def clear_all(self):
        """
        Clears all caches and resets states in the StepProcessor.
        """
        def _safe_reset(obj, name: str) -> None:
            if obj is None:
                return
            reset_fn = getattr(obj, "reset", None)
            if callable(reset_fn):
                reset_fn()
                return
            clear_fn = getattr(obj, "clear_cache", None)
            if callable(clear_fn):
                clear_fn()

        _safe_reset(getattr(self.processor, "metadata_manager", None), "metadata_manager")
        _safe_reset(getattr(self.processor, "color_generator", None), "color_generator")
        _safe_reset(getattr(self.processor, "part_identifier", None), "part_identifier")
        _safe_reset(getattr(self.processor, "brep_analyzer", None), "brep_analyzer")
        _safe_reset(getattr(self.processor, "feature_recognizer", None), "feature_recognizer")

        print("All caches and states have been reset.")