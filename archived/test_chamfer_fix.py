#!/usr/bin/env python3
"""
Test-Script zur Überprüfung der BRep-Analyzer-Änderungen
"""

import sys
import os

# Mock OCC availability für Test
sys.modules['OCC'] = type(sys)('OCC')
sys.modules['OCC.Core'] = type(sys)('OCC.Core')
sys.modules['OCC.Core.TopoDS'] = type(sys)('TopoDS')
sys.modules['OCC.Core.TopAbs'] = type(sys)('TopAbs')
sys.modules['OCC.Core.TopExp'] = type(sys)('TopExp')
sys.modules['OCC.Core.BRep'] = type(sys)('BRep')
sys.modules['OCC.Core.BRepGProp'] = type(sys)('BRepGProp')
sys.modules['OCC.Core.GProp'] = type(sys)('GProp')
sys.modules['OCC.Core.BRepBndLib'] = type(sys)('BRepBndLib')
sys.modules['OCC.Core.Bnd'] = type(sys)('Bnd')
sys.modules['OCC.Core.BRepAdaptor'] = type(sys)('BRepAdaptor')
sys.modules['OCC.Core.GeomAbs'] = type(sys)('GeomAbs')
sys.modules['OCC.Core.GeomAdaptor'] = type(sys)('GeomAdaptor')
sys.modules['OCC.Core.BRepExtrema'] = type(sys)('BRepExtrema')
sys.modules['OCC.Core.gp'] = type(sys)('gp')

def test_brep_analyzer_import():
    """Test dass BRepAnalyzer ohne Chamfer-Fehler importiert werden kann"""
    try:
        from stepparser.analysis.brep_analyzer import BRepAnalyzer, FaceAnalyzer
        print("✓ BRepAnalyzer erfolgreich importiert")
        return True
    except Exception as e:
        print(f"✗ Import-Fehler: {e}")
        return False

def check_chamfer_references():
    """Prüfe die BRep-Analyzer-Datei auf verbleibende Chamfer-Verweise"""
    brep_file = "src/analysis/brep_analyzer.py"
    
    if not os.path.exists(brep_file):
        print(f"✗ Datei nicht gefunden: {brep_file}")
        return False
    
    with open(brep_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Suche nach problematischen Verweisen
    problematic_lines = []
    lines = content.split('\n')
    
    for i, line in enumerate(lines, 1):
        if '_analyze_chamfer_characteristics' in line:
            problematic_lines.append(f"Zeile {i}: {line.strip()}")
        elif 'chamfer_count' in line and 'chamfer_count = 0' not in line:
            # Erlaubt sind nur Initialisierungen
            problematic_lines.append(f"Zeile {i}: {line.strip()}")
    
    if problematic_lines:
        print("✗ Problematische Chamfer-Verweise gefunden:")
        for line in problematic_lines:
            print(f"  {line}")
        return False
    else:
        print("✓ Keine problematischen Chamfer-Verweise gefunden")
        return True

def test_face_analyzer_method():
    """Teste die FaceAnalyzer.analyze_face-Methode"""
    try:
        # Mock OCC-Objekte
        class MockFace:
            def Orientation(self):
                return "Forward"
        
        class MockAdaptor:
            def GetType(self):
                return 1  # GeomAbs_Plane
                
        class MockTool:
            @staticmethod
            def Surface(face):
                return None
        
        # Ersetze BRep_Tool temporär
        import stepparser.analysis.brep_analyzer as brep_module
        original_tool = getattr(brep_module, 'BRep_Tool', None)
        brep_module.BRep_Tool = MockTool()
        
        # Teste die Methode
        from stepparser.analysis.brep_analyzer import FaceAnalyzer
        
        # Diese sollte nicht mehr versuchen, _analyze_chamfer_characteristics aufzurufen
        result = FaceAnalyzer.analyze_face(MockFace(), 1, (0, 0, 1))
        
        print(f"✓ FaceAnalyzer.analyze_face funktioniert: {type(result)}")
        print(f"  Ergebnis-Typ: {result.get('type', 'Unbekannt')}")
        print(f"  is_chamfer: {result.get('is_chamfer', 'Nicht gesetzt')}")
        
        # Stelle BRep_Tool wieder her
        if original_tool:
            brep_module.BRep_Tool = original_tool
            
        return True
    except Exception as e:
        print(f"✗ FaceAnalyzer-Test fehlgeschlagen: {e}")
        return False

def main():
    print("=== Test der Chamfer-Analyse-Entfernung ===\\n")
    
    tests = [
        ("Import-Test", test_brep_analyzer_import),
        ("Chamfer-Referenz-Check", check_chamfer_references),
        ("FaceAnalyzer-Test", test_face_analyzer_method)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"Test: {test_name}")
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"✗ {test_name} Fehler: {e}")
            results.append(False)
        print()
    
    # Zusammenfassung
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"Test-Ergebnis: {passed}/{total} Tests bestanden")
    
    if passed == total:
        print("✅ Alle Tests erfolgreich! Chamfer-Analyse wurde erfolgreich entfernt.")
        print("\\nDie _analyze_chamfer_characteristics-Fehler sollten behoben sein.")
    else:
        print("⚠️  Einige Tests fehlgeschlagen. Überprüfen Sie die Ausgabe oben.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)