# ============================================
# src/io/step_loader.py
# ============================================
import os
from OCC.Core.STEPControl import STEPControl_Reader
from typing import Optional, List, Union
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TDocStd import TDocStd_Document
from OCC.Core.XCAFApp import XCAFApp_Application
from OCC.Core.XCAFDoc import (
    XCAFDoc_DocumentTool_ShapeTool,
    XCAFDoc_DocumentTool_ColorTool
)
from OCC.Core.TDF import TDF_LabelSequence, TDF_Label
from OCC.Core.TDataStd import TDataStd_Name
from OCC.Core.TopoDS import TopoDS_Shape
from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_COMPOUND
from OCC.Core.TopExp import TopExp_Explorer

from ..core.assembly import Assembly
from ..core.part import Part

class StepLoader:
    """Loads and parses STEP files with assembly structure"""
    
    def __init__(self):
        self.reader = STEPControl_Reader()
        self.shape_tool = None
        self.color_tool = None
    
    def load_step_file(self, file_path: str) -> Assembly:
        print(f"Loading STEP file: {file_path}")

        # Create a fresh reader for this file
        reader = STEPControl_Reader()
        status = reader.ReadFile(file_path)
        if status != IFSelect_RetDone:
            raise Exception(f"Failed to read STEP file: {file_path}")

        # Transfer roots
        reader.TransferRoots()
        shape = reader.OneShape()

        if shape.IsNull():
            raise Exception("No shape found in STEP file")

        try:
            root_assembly = self._parse_xcaf_structure(file_path)
            print(f"Successfully parsed assembly structure with XCAF")
            return root_assembly
        except Exception as e:
            print(f"XCAF parsing failed: {e}")
            print("Falling back to simple shape parsing")
            return self._parse_simple_structure(shape, file_path)
    
    def _parse_xcaf_structure(self, file_path: str) -> Assembly:
        """Parse STEP file using XCAF for assembly hierarchy"""
        # Create document
        app = XCAFApp_Application.GetApplication()
        doc = TDocStd_Document("MDTV-XCAF")
        
        # Read STEP with XCAF
        reader = STEPControl_Reader()
        reader.SetColorMode(True)
        reader.SetNameMode(True)
        reader.SetLayerMode(True)
        
        status = reader.ReadFile(file_path)
        if status != IFSelect_RetDone:
            raise Exception("Failed to read STEP file")
        
        reader.Transfer(doc)
        
        # Get shape and color tools
        shape_tool = XCAFDoc_DocumentTool.ShapeTool(doc.Main())
        color_tool = XCAFDoc_DocumentTool.ColorTool(doc.Main())
        
        # Get free shapes (root level shapes)
        free_shapes = TDF_LabelSequence()
        shape_tool.GetFreeShapes(free_shapes)
        
        if free_shapes.Length() == 0:
            raise Exception("No free shapes found")
        
        # Parse first free shape as root assembly
        root_label = free_shapes.Value(1)
        root_assembly = self._parse_label_recursive(root_label, shape_tool, color_tool)
        
        return root_assembly
    
    def _parse_label_recursive(self, label: TDF_Label, shape_tool, color_tool, 
                               depth: int = 0) -> Union[Assembly, Part]:
        """Recursively parse XCAF labels into Assembly/Part hierarchy"""
        
        if depth > 10:  # Max depth limit
            print(f"Warning: Max depth reached at label {label}")
            return None
        
        # Get shape
        shape = shape_tool.GetShape(label)
        
        # Get name
        name = self._get_label_name(label)
        if not name:
            name = f"Component_{depth}_{label.Tag()}"
        
        # Check if this is an assembly
        is_assembly = shape_tool.IsAssembly(label)
        
        if is_assembly:
            # Create Assembly
            assembly = Assembly(shape=shape, name=name)
            assembly.depth = depth
            
            # Get components
            components = TDF_LabelSequence()
            shape_tool.GetComponents(label, components)
            
            print(f"{'  ' * depth}Assembly: {name} ({components.Length()} children)")
            
            # Parse children recursively
            for i in range(1, components.Length() + 1):
                component_label = components.Value(i)
                ref_label = TDF_Label()
                
                # Get referred shape
                if shape_tool.GetReferredShape(component_label, ref_label):
                    child = self._parse_label_recursive(ref_label, shape_tool, color_tool, depth + 1)
                    if child:
                        assembly.add_child(child)
            
            return assembly
        
        else:
            # Create Part
            print(f"{'  ' * depth}Part: {name}")
            part = Part(shape=shape, name=name)
            return part
    
    def _get_label_name(self, label: TDF_Label) -> str:
        """Extract name from label"""
        from OCC.Core.TDataStd import TDataStd_Name
        
        name_attr = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID(), name_attr):
            name_str = name_attr.Get()
            # Convert TCollection_ExtendedString to Python string
            return name_str.ToExtString()
        return None
    
    def _parse_simple_structure(self, shape: TopoDS_Shape, file_path: str) -> Assembly:
        """
        Fallback parser: treat shape as single assembly
        Split compound shapes into parts
        """
        from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_COMPOUND
        from OCC.Core.TopExp import TopExp_Explorer
        
        filename = os.path.basename(file_path).replace('.step', '').replace('.stp', '')
        root_assembly = Assembly(shape=shape, name=filename)
        
        # If it's a compound, extract solids
        if shape.ShapeType() == TopAbs_COMPOUND:
            print("Extracting solids from compound shape")
            
            # Explore for solids
            exp = TopExp_Explorer(shape, TopAbs_SOLID)
            part_counter = 1
            
            while exp.More():
                solid = exp.Current()
                part = Part(shape=solid, name=f"Part_{part_counter}")
                root_assembly.add_child(part)
                part_counter += 1
                exp.Next()
            
            print(f"Extracted {part_counter - 1} parts")
        
        else:
            # Single solid - treat as one part
            part = Part(shape=shape, name="Part_1")
            root_assembly.add_child(part)
        
        return root_assembly