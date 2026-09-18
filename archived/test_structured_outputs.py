"""Test: Structured Outputs nach User-Änderungen"""

from agent.structured_output import (
    AssemblyAnalysis,
    AssemblyBatchAnalysis,
    CertaintyItem,
    GeometricFeature,
    PartOverview,
    SinglePartAnalysis,
    SinglePartBatchAnalysis,
    MaterialInfo,
    PhysicalProperties,
    AssemblyInterface,
)

# Test AssemblyAnalysis
print("=" * 60)
print("TEST: AssemblyAnalysis")
print("=" * 60)

assembly = AssemblyAnalysis(
    assembly_name_guess=["Test Gearbox", "Simple Gear Assembly"],
    assembly_description=["A simple gearbox assembly"],
    primary_function=["Reduce speed and increase torque"],
    parts=[
        PartOverview(name="Housing", color="gray", quantity=1, task="Enclose gears"),
        PartOverview(name="Gear", color="silver", quantity=2),
    ],
    certainties=[
        CertaintyItem(topic="Material", level=0.8),
        CertaintyItem(topic="Function", level=0.95),
    ]
)

print(f"✓ AssemblyAnalysis erstellt")
print(f"  Name: {assembly.assembly_name_guess}")
print(f"  Parts: {len(assembly.parts)}")
print(f"  Certainties: {len(assembly.certainties)}")
print()

# Test SinglePartAnalysis mit neuen Feldern
print("=" * 60)
print("TEST: SinglePartAnalysis (mit MaterialInfo, PhysicalProperties, AssemblyInterface)")
print("=" * 60)

part = SinglePartAnalysis(
    part_name_guess=["Shaft", "Drive Shaft"],
    part_type_guess=["shaft", "transmission component"],
    task=["Transmit rotational motion"],
    geometry_features=[
        GeometricFeature(
            type="thread",
            description="M10 thread at end",
            quantity=1,
            is_interface=True,
            certainty=0.95
        ),
        GeometricFeature(
            type="keyway",
            description="Parallel keyway 8mm wide",
            quantity=1,
            is_interface=True,
            certainty=0.90
        ),
    ],
    material_info=MaterialInfo(
        possible_materials=["steel", "stainless steel"],
        density="high",
        mass="medium",
        certainty=0.85
    ),
    physical_properties=PhysicalProperties(
        rigidity="rigid",
        surface_sensitivity="sensitive",
        part_sensitivity="durable",
        certainty=0.80
    ),
    assembly_interface=AssemblyInterface(
        gripping_surfaces=["cylindrical body", "flat end face"],
        orientation_by_design="keyed",
        additional_joining_elements=["threads", "keyway"],
        certainty=0.92
    ),
    geometric_description="Cylindrical shaft with threaded end",
    packaging="Protective wrap",
    important_facts=["Precision ground surface", "Heat treated"],
    certainties=[
        CertaintyItem(topic="Material", level=0.85),
    ]
)

print(f"✓ SinglePartAnalysis erstellt")
print(f"  Name: {part.part_name_guess}")
print(f"  Type: {part.part_type_guess}")
print(f"  Features: {len(part.geometry_features)}")
print(f"  Material: {part.material_info.possible_materials if part.material_info else 'None'}")
print(f"  Rigidity: {part.physical_properties.rigidity if part.physical_properties else 'None'}")
print(f"  Orientation: {part.assembly_interface.orientation_by_design if part.assembly_interface else 'None'}")
print()

# Test Batch Wrappers
print("=" * 60)
print("TEST: Batch Wrappers")
print("=" * 60)

batch_assembly = AssemblyBatchAnalysis(analysis=assembly)
batch_part = SinglePartBatchAnalysis(analysis=part)

print(f"✓ AssemblyBatchAnalysis: {batch_assembly.analysis.assembly_name_guess}")
print(f"✓ SinglePartBatchAnalysis: {batch_part.analysis.part_name_guess}")
print()

# Test JSON Serialization
print("=" * 60)
print("TEST: JSON Serialization")
print("=" * 60)

assembly_json = assembly.model_dump_json(indent=2)
part_json = part.model_dump_json(indent=2)

print(f"✓ Assembly JSON: {len(assembly_json)} chars")
print(f"✓ Part JSON: {len(part_json)} chars")
print()

print("=" * 60)
print("✅ ALLE TESTS ERFOLGREICH")
print("=" * 60)
print("User-Änderungen funktionieren:")
print("  - AssemblyAnalysis mit Listen für name/description/function")
print("  - SinglePartAnalysis mit MaterialInfo, PhysicalProperties, AssemblyInterface")
print("  - GeometricFeature mit certainty")
print("  - JSON Serialization funktioniert")
print()
print("Ihre Änderungen sind vollständig kompatibel! ✓")
