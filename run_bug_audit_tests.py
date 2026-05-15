"""
Test Runner for Bug Audit and Output Grading E2E Tests
======================================================
Runs comprehensive tests against the aetherdesk codebase.

Usage:
    python run_bug_audit_tests.py          # Run all tests
    python run_bug_audit_tests.py --bugs   # Run only bug verification
    python run_bug_audit_tests.py --grade  # Run only output grading
    python run_bug_audit_tests.py --edge   # Run only edge cases
"""
import sys
import subprocess
import argparse
import os

def run_tests(args):
    """Run pytest with specified filters."""
    pytest_args = [
        "pytest",
        "tests/e2e/test_bug_audit_and_output_grading.py",
        "-v",
        "--tb=short",
    ]

    if args.bugs:
        pytest_args.extend(["-k", "TestBugVerification"])
    elif args.grade:
        pytest_args.extend(["-k", "TestOutputGrading"])
    elif args.edge:
        pytest_args.extend(["-k", "TestEdgeCases"])
    elif args.integration:
        pytest_args.extend(["-k", "TestIntegrationGradingSummary"])
    elif args.ui:
        pytest_args.extend(["-k", "TestUIOutputGrading"])

    if args.headed:
        pytest_args.append("--headed")

    print(f"Running: {' '.join(pytest_args)}")
    print("-" * 60)

    result = subprocess.run(pytest_args)
    return result.returncode

def run_quick_check():
    """Run quick sanity check against running API."""
    print("\n=== Quick API Health Check ===")
    try:
        import httpx
        resp = httpx.get("http://localhost:8000/health", timeout=5)
        print(f"API Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"Services: {resp.json().get('services', {})}")
    except Exception as e:
        print(f"API not reachable: {e}")
        print("Start API with: python start_api.py")

    print("-" * 60)

def print_bug_summary():
    """Print summary of bugs found in audit."""
    print("""
================================================================================
                        BUG AUDIT SUMMARY
================================================================================

CRITICAL BUGS (Must Fix):
-------------------------
1. DB Context Async/Sync Mismatch (auth.py, campaign.py)
   - db_context() is asynccontextmanager but used synchronously
   - Will fail at runtime

2. Null Pointer on Profile Query (orchestrator.py:116)
   - profile could be None but accessed without null check

3. Missing Tables in Schema (orchestrator.py, campaign.py)
   - agent_profiles, tenant_settings, action_approvals, rentals, etc.

4. API Key Not Set on Tenant Creation (main.py)
   - verify_api_key will fail for new tenants

RACE CONDITIONS:
-----------------
5. Hub Sockets Not Thread-Safe (agent.py)
6. Campaign Running Flag Race (campaign.py)
7. Voice Profile LRU Race (voice_cloning.py)
8. Agent Cache TTL Race (agent.py)

RESOURCE LEAKS:
---------------
9. File Handle Not Closed (voice_cloning.py:96)
10. HTTP Client Not Closed (main.py, campaign.py)
11. Redis PubSub Not Closed (main.py)
12. AgentOps Session Leak (orchestrator.py)

EDGE CASES:
-----------
13. No Voice File Size Validation
14. Missing Query Parameter Defaults
15. Division by Zero in Usage Stats
16. Skills JSON Parse Edge Cases

CODE SMELLS:
------------
- Hardcoded fallback values
- Code duplication (skills parsing repeated 6x)
- Empty exception handling
- Magic numbers

================================================================================
Run tests with:
    python run_bug_audit_tests.py --bugs      # Verify bugs
    python run_bug_audit_tests.py --grade     # Grade output
    python run_bug_audit_tests.py --edge      # Edge cases
    python run_bug_audit_tests.py --all      # Everything
================================================================================
""")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run bug audit and grading tests")
    parser.add_argument("--bugs", action="store_true", help="Run bug verification tests")
    parser.add_argument("--grade", action="store_true", help="Run output grading tests")
    parser.add_argument("--edge", action="store_true", help="Run edge case tests")
    parser.add_argument("--integration", action="store_true", help="Run integration grading")
    parser.add_argument("--ui", action="store_true", help="Run UI grading tests")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--headed", action="store_true", help="Run in headed mode (visible browser)")
    parser.add_argument("--check", action="store_true", help="Quick health check")
    parser.add_argument("--summary", action="store_true", help="Print bug summary")
    args = parser.parse_args()

    if args.summary:
        print_bug_summary()
        sys.exit(0)

    if args.check:
        run_quick_check()
        sys.exit(0)

    if not any([args.bugs, args.grade, args.edge, args.integration, args.ui, args.all]):
        print("No test filter specified. Use --all or specific flag.")
        parser.print_help()
        sys.exit(1)

    if args.all:
        # Reset to run all tests
        pass

    sys.exit(run_tests(args))