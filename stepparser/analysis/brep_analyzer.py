# ============================================
# src/analysis/brep_analyzer.py
# ============================================

import math
from typing import Dict, Tuple, Any
from collections import defaultdict
from functools import wraps

# OCC Imports
try:
    from OCC.Core.TopoDS import TopoDS_Shape, topods
    from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE, TopAbs_WIRE, TopAbs_EDGE, TopAbs_VERTEX
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepGProp import brepgprop
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.BRepBndLib import brepbndlib
    from OCC.Core.Bnd import Bnd_Box, Bnd_OBB
    from OCC.Core.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
    from OCC.Core.GeomAbs import (GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, 
                                   GeomAbs_Sphere, GeomAbs_Torus, GeomAbs_BezierSurface,
                                   GeomAbs_BSplineSurface, GeomAbs_SurfaceOfRevolution,
                                   GeomAbs_SurfaceOfExtrusion, GeomAbs_Circle)
    from OCC.Core.GeomAdaptor import GeomAdaptor_Surface
    from OCC.Core.BRepExtrema import BRepExtrema_DistShapeShape
    from OCC.Core.gp import gp_Dir, gp_Vec
    OCC_AVAILABLE = True
except Exception as e:
    print(f"[WARNING] OCC modules not available: {e}")
    OCC_AVAILABLE = False

from ..core.data_classes import GeometryData, BoundingBox


def safe_occ_operation(default_value=None):
    """Decorator for safe OCC operations with consistent error handling"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"[WARNING] {func.__name__} failed: {e}")
                return default_value if default_value is not None else {}
        return wrapper
    return decorator


class FaceAnalyzer:
    """Base class for face geometry analysis"""
    
    SURFACE_TYPES = {
        GeomAbs_Plane: "PLANE",
        GeomAbs_Cylinder: "CYLINDER",
        GeomAbs_Cone: "CONE",
        GeomAbs_Sphere: "SPHERE",
        GeomAbs_Torus: "TORUS",
        GeomAbs_BezierSurface: "BEZIER_SURFACE",
        GeomAbs_BSplineSurface: "BSPLINE_SURFACE",
        GeomAbs_SurfaceOfRevolution: "SURFACE_OF_REVOLUTION",
        GeomAbs_SurfaceOfExtrusion: "SURFACE_OF_EXTRUSION"
    }
    
    @staticmethod
    def analyze_face(face: TopoDS_Shape, feature_id: int) -> Dict:
        """Analyze a single face and return properties"""
        if not OCC_AVAILABLE:
            return {'feature_id': feature_id, 'type': 'ERROR', 'error': 'OCC not available'}
            
        try:
            adaptor = BRepAdaptor_Surface(face)
            surf_type = adaptor.GetType()
            face_type = FaceAnalyzer.SURFACE_TYPES.get(surf_type, f"UNKNOWN_{surf_type}")
            
            # Calculate area
            props = GProp_GProps()
            brepgprop.SurfaceProperties(face, props)
            area = props.Mass()
            
            # Base properties
            result = {
                'feature_id': feature_id,
                'type': face_type,
                'area': area,
                'is_planar': surf_type == GeomAbs_Plane,
                'orientation': str(face.Orientation()),
                'is_chamfer': False  # Chamfer analysis disabled
            }
            
            # Add geometry-specific properties
            analyzer_map = {
                'CYLINDER': FaceAnalyzer._analyze_cylinder,
                'CONE': FaceAnalyzer._analyze_cone,
                'PLANE': FaceAnalyzer._analyze_plane
            }
            
            analyzer = analyzer_map.get(face_type)
            if analyzer:
                geom_surf = BRep_Tool.Surface(face)
                geom_adaptor = GeomAdaptor_Surface(geom_surf)
                result[f'{face_type.lower()}_properties'] = analyzer(
                    face, geom_adaptor, area
                )
            
            return result
            
        except Exception as e:
            return {'feature_id': feature_id, 'type': 'ERROR', 'error': str(e), 'is_chamfer': False}
    
    @staticmethod
    @safe_occ_operation({})
    def _analyze_cylinder(face, adaptor, area: float) -> Dict:
        """Analyze cylindrical face"""
        cyl = adaptor.Cylinder()
        axis = cyl.Axis()
        loc, dir = axis.Location(), axis.Direction()
        radius = cyl.Radius()
        height = area / (2 * math.pi * radius) if radius > 0 else 0
        half_h = height / 2
        
        return {
            'diameter': radius * 2,
            'position': [loc.X(), loc.Y(), loc.Z()],
            'direction': [dir.X(), dir.Y(), dir.Z()],
            'estimated_height': height,
            'axis_endpoints': [
                [loc.X() - dir.X() * half_h, loc.Y() - dir.Y() * half_h, loc.Z() - dir.Z() * half_h],
                [loc.X() + dir.X() * half_h, loc.Y() + dir.Y() * half_h, loc.Z() + dir.Z() * half_h]
            ],
            'is_vertical': abs(dir.Z()) > 0.99,
            'is_horizontal': abs(dir.Z()) < 0.01
        }
    
    @staticmethod
    @safe_occ_operation({})
    def _analyze_cone(face, adaptor, area: float) -> Dict:
        """Analyze conical face"""
        cone = adaptor.Cone()
        axis = cone.Axis()
        loc, dir = axis.Location(), axis.Direction()
        apex = cone.Apex()
        semi_angle = cone.SemiAngle()
        ref_radius = cone.RefRadius()
        
        props = {
            'apex': [apex.X(), apex.Y(), apex.Z()],
            'axis_position': [loc.X(), loc.Y(), loc.Z()],
            'axis_direction': [dir.X(), dir.Y(), dir.Z()],
            'semi_angle_deg': math.degrees(semi_angle),
            'reference_radius': ref_radius
        }
        
        if ref_radius > 0:
            slant = area / (math.pi * ref_radius)
            props.update({
                'height': slant * math.cos(semi_angle),
                'slant_height': slant,
                'base_area': math.pi * ref_radius * ref_radius
            })
        
        return props
    
    @staticmethod
    @safe_occ_operation({})
    def _analyze_sphere(face, adaptor, area: float) -> Dict:
        """Analyze spherical face"""
        sphere = adaptor.Sphere()
        loc = sphere.Location()
        radius = sphere.Radius()
        complete_area = 4 * math.pi * radius * radius
        
        return {
            'center': [loc.X(), loc.Y(), loc.Z()],
            'diameter': radius * 2,
            'is_complete': abs(area - complete_area) < (0.01 * complete_area)
        }
    
    @staticmethod
    @safe_occ_operation({})
    def _analyze_torus(face, adaptor, area: float) -> Dict:
        """Analyze toroidal face"""
        torus = adaptor.Torus()
        loc = torus.Location()
        axis = torus.Axis()
        dir = axis.Direction()
        major_r = torus.MajorRadius()
        minor_r = torus.MinorRadius()
        
        return {
            'center': [loc.X(), loc.Y(), loc.Z()],
            'axis_direction': [dir.X(), dir.Y(), dir.Z()],
            'major_radius': major_r,
            'minor_radius': minor_r,
            'inner_diameter': 2 * (major_r - minor_r),
            'outer_diameter': 2 * (major_r + minor_r),
            'tube_diameter': 2 * minor_r
        }
    
    @staticmethod
    @safe_occ_operation({})
    def _analyze_plane(face, adaptor, area: float) -> Dict:
        """Analyze planar face"""
        plane = adaptor.Plane()
        loc = plane.Location()
        axis = plane.Axis()
        dir = axis.Direction()
        
        # Plane equation coefficients
        a, b, c = dir.X(), dir.Y(), dir.Z()
        d = a * loc.X() + b * loc.Y() + c * loc.Z()
        
        props = {
            'origin': [loc.X(), loc.Y(), loc.Z()],
            'normal': [a, b, c],
            'd_coefficient': d
        }
        
        # Centroid
        try:
            face_props = GProp_GProps()
            brepgprop.SurfaceProperties(face, face_props)
            com = face_props.CentreOfMass()
            props['centroid'] = [com.X(), com.Y(), com.Z()]
        except:
            props['centroid'] = props['origin']
        
        # Perimeter
        try:
            perim = 0.0
            edge_exp = TopExp_Explorer(face, TopAbs_EDGE)
            while edge_exp.More():
                edge = topods.Edge(edge_exp.Current())
                edge_props = GProp_GProps()
                brepgprop.LinearProperties(edge, edge_props)
                perim += edge_props.Mass()
                edge_exp.Next()
            props['perimeter'] = perim
        except:
            props['perimeter'] = 0.0
        
        return props


class UnifiedShapeAnalyzer:
    """Analyzes shape properties in one pass"""
    
    def __init__(self, shape: TopoDS_Shape, name: str, density: float = None):
        self.shape = shape
        self.name = name
        self.density = density or None
        self._cache = None
        self._feature_id = 0
    
    def analyze_complete(self) -> Dict:
        """Perform complete analysis once and cache"""
        if self._cache:
            return self._cache
        
        if not OCC_AVAILABLE:
            return {'error': 'OCC not available'}
            
        print(f"[DEBUG] Analyzing {self.name}")
        self._feature_id = 0
        
        # Extract part index
        import re
        match = re.search(r'_part_?(\d+)$', self.name)
        part_idx = int(match.group(1)) if match else None
        
        # Gather all analysis data
        geom = self._analyze_geometry()
        faces = self._analyze_all_faces()
        
        self._cache = {
            'mom_inertia': geom.get('mom_inertia', {}),
            'faces_details': faces.get('faces', {}).get('details', [])
        }
        
        print(f"[DEBUG] Analysis complete: {self.name} ({self._feature_id} features)")
        return self._cache
    
    @safe_occ_operation({})
    def _count_brep_entities(self) -> Dict:
        """Count topological entities"""
        types = [
            (TopAbs_SOLID, 'solids'),
            (TopAbs_SHELL, 'shells'),
            (TopAbs_FACE, 'faces'),
            (TopAbs_WIRE, 'wires'),
            (TopAbs_EDGE, 'edges'),
            (TopAbs_VERTEX, 'vertices')
        ]
        
        counts = {}
        for topo_type, key in types:
            exp = TopExp_Explorer(self.shape, topo_type)
            count = 0
            while exp.More():
                count += 1
                exp.Next()
            counts[key] = count
        
        return counts
    
    @safe_occ_operation({})
    def _analyze_geometry(self) -> Dict:
        """Analyze geometric properties"""
        props = GProp_GProps()
        
        # Volume and mass
        brepgprop.VolumeProperties(self.shape, props)
        volume = props.Mass()
        com = props.CentreOfMass()
        matrix = props.MatrixOfInertia()
        
        # Surface area
        brepgprop.SurfaceProperties(self.shape, props)
        surface_area = props.Mass()
        
        # Edge length
        brepgprop.LinearProperties(self.shape, props)
        edge_length = props.Mass()
        
        return {
            'volume': volume,
            'density': self.density,
            'mass': volume * self.density if self.density else None,
            'surface_area': surface_area,
            'total_edge_length': edge_length,
            'CoM': [com.X(), com.Y(), com.Z()],
            'mom_inertia': {
                'Ixx': matrix.Value(1, 1),
                'Iyy': matrix.Value(2, 2),
                'Izz': matrix.Value(3, 3),
                'Ixy': matrix.Value(1, 2),
                'Ixz': matrix.Value(1, 3),
                'Iyz': matrix.Value(2, 3)
            }
        }
    
    @safe_occ_operation({})
    def _analyze_bounding(self) -> Dict:
        """Analyze bounding boxes"""
        aabb = Bnd_Box()
        brepbndlib.Add(self.shape, aabb)
        xmin, ymin, zmin, xmax, ymax, zmax = aabb.Get()
        
        obb = Bnd_OBB()
        brepbndlib.AddOBB(self.shape, obb)
        center = obb.Center()
        
        return {
            'aabb': {
                'min': [xmin, ymin, zmin],
                'max': [xmax, ymax, zmax],
                'dimensions': [xmax - xmin, ymax - ymin, zmax - zmin],
                'volume': (xmax - xmin) * (ymax - ymin) * (zmax - zmin)
            },
            'obb': {
                'center': [center.X(), center.Y(), center.Z()]
            }
        }
    
    def _analyze_all_faces(self) -> Dict:
        """Analyze all faces"""
        faces_data = []
        type_counts = defaultdict(int)
        total_area = 0.0
        
        exp = TopExp_Explorer(self.shape, TopAbs_FACE)
        while exp.More():
            self._feature_id += 1
            face = topods.Face(exp.Current())
            face_data = FaceAnalyzer.analyze_face(face, self._feature_id)
            
            faces_data.append(face_data)
            type_counts[face_data['type']] += 1
            total_area += face_data.get('area', 0.0)
            
            exp.Next()
        
        return {
            'faces': {
                'count': len(faces_data),
                'total_area': total_area,
                'type_distribution': dict(type_counts),
                'geometry_summary': {
                    f'{k.lower()}_surfaces': v 
                    for k, v in type_counts.items()
                    if k in {'CYLINDER', 'CONE', 'SPHERE', 'TORUS', 'PLANE'}
                },
                'details': faces_data
            }
        }


class BRepAnalyzer:
    """Main analyzer that integrates with the existing system"""
    
    def __init__(self):
        self.analyzers_cache = {}
    
    @safe_occ_operation((0.0, 0.0, {'min': [0,0,0], 'max': [0,0,0]}, 0, 0, 0, 0, 0, 0, 0))
    def _compute_basic_geometry(self, shape: TopoDS_Shape):
        """Compute basic geometry data for GeometryData"""
        # Volume and surface area
        props = GProp_GProps()
        brepgprop.VolumeProperties(shape, props)
        volume = props.Mass()
        brepgprop.SurfaceProperties(shape, props)
        surface_area = props.Mass()
        
        # Bounding box
        aabb = Bnd_Box()
        brepbndlib.Add(shape, aabb)
        xmin, ymin, zmin, xmax, ymax, zmax = aabb.Get()
        bbox = {
            'min': [xmin, ymin, zmin],
            'max': [xmax, ymax, zmax]
        }
        
        # BREP counts
        types = [
            (TopAbs_FACE, 'faces'),
            (TopAbs_EDGE, 'edges'),
            (TopAbs_VERTEX, 'vertices')
        ]
        counts = {}
        for topo_type, key in types:
            exp = TopExp_Explorer(shape, topo_type)
            count = 0
            while exp.More():
                count += 1
                exp.Next()
            counts[key] = count
        
        # Face types
        cylinder_surfaces = 0
        plane_surfaces = 0
        sphere_surfaces = 0
        other_surfaces = 0
        
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = topods.Face(exp.Current())
            adaptor = BRepAdaptor_Surface(face)
            surf_type = adaptor.GetType()
            face_type = FaceAnalyzer.SURFACE_TYPES.get(surf_type, "OTHER")
            if face_type == "CYLINDER":
                cylinder_surfaces += 1
            elif face_type == "PLANE":
                plane_surfaces += 1
            elif face_type == "SPHERE":
                sphere_surfaces += 1
            else:
                other_surfaces += 1
            exp.Next()
        
        return volume, surface_area, bbox, counts['faces'], counts['edges'], counts['vertices'], cylinder_surfaces, plane_surfaces, sphere_surfaces, other_surfaces
    
    def analyze_shape(self, shape: TopoDS_Shape, name: str = "Unknown") -> GeometryData:
        """Main method called by processor to analyze shape and return GeometryData"""
        if not OCC_AVAILABLE:
            # Return empty GeometryData if OCC not available
            return GeometryData(
                volume=0.0,
                surface_area=0.0,
                bounding_box=BoundingBox((0, 0, 0), (0, 0, 0)),
                face_count=0,
                edge_count=0,
                vertex_count=0,
                cylinder_surfaces=0,
                plane_surfaces=0,
                sphere_surfaces=0,
                other_surfaces=0
            )
        
        # Compute basic geometry data
        volume, surface_area, bbox, face_count, edge_count, vertex_count, cylinder_surfaces, plane_surfaces, sphere_surfaces, other_surfaces = self._compute_basic_geometry(shape)
        
        # Use UnifiedShapeAnalyzer for detailed analysis
        analyzer = UnifiedShapeAnalyzer(shape, name)
        analysis_result = analyzer.analyze_complete()
        
        # Cache the analyzer for detailed analysis access
        self.analyzers_cache[name] = analyzer
        
        # Create BoundingBox
        bounding_box = BoundingBox(
            min_point=tuple(bbox['min']),
            max_point=tuple(bbox['max'])
        )
        
        # Create and return GeometryData
        return GeometryData(
            volume=volume,
            surface_area=surface_area,
            bounding_box=bounding_box,
            face_count=face_count,
            edge_count=edge_count,
            vertex_count=vertex_count,
            cylinder_surfaces=cylinder_surfaces,
            plane_surfaces=plane_surfaces,
            sphere_surfaces=sphere_surfaces,
            other_surfaces=other_surfaces
        )
    
    def get_bounding_box(self, shape: TopoDS_Shape) -> BoundingBox:
        """Get bounding box for a shape"""
        if not OCC_AVAILABLE:
            return BoundingBox((0, 0, 0), (0, 0, 0))
            
        try:
            aabb = Bnd_Box()
            brepbndlib.Add(shape, aabb)
            xmin, ymin, zmin, xmax, ymax, zmax = aabb.Get()
            return BoundingBox(
                min_point=(xmin, ymin, zmin),
                max_point=(xmax, ymax, zmax)
            )
        except Exception as e:
            print(f"[WARNING] Failed to compute bounding box: {e}")
            return BoundingBox((0, 0, 0), (0, 0, 0))
    
    def get_detailed_analysis(self, name: str) -> Dict:
        """Get detailed analysis for a part by name"""
        analyzer = self.analyzers_cache.get(name)
        if analyzer:
            analysis = analyzer.analyze_complete()
            # Round the analysis before returning
            return self.round_nested(analysis)
        return {}
    
    def round_nested(self, obj: Any, decimals: int = 3) -> Any:
        """Recursively round numerical values"""
        if isinstance(obj, dict):
            return {k: self.round_nested(v, decimals) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.round_nested(item, decimals) for item in obj]
        elif isinstance(obj, float):
            return 0.0 if abs(obj) < 1e-10 else round(obj, decimals)
        return obj
    
