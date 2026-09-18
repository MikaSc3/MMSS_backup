from agent.workflow import build_workflow

print("Testing workflow compilation...")
try:
    wf = build_workflow()
    print("✅ SUCCESS: Workflow kompiliert mit Phase 4.1-4.3")
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
