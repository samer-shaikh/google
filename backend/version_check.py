"""
version_check.py — inspect LangGraph + psycopg versions and PostgresSaver API
Run: python version_check.py
"""
import sys, subprocess

pkgs = [
    "langgraph",
    "langgraph-checkpoint-postgres",
    "psycopg",
    "psycopg-binary",
    "psycopg2",
    "psycopg2-binary",
]

print("=" * 55)
print("Package versions")
print("=" * 55)
for pkg in pkgs:
    r = subprocess.run([sys.executable, "-m", "pip", "show", pkg],
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith(("Name:", "Version:")):
            print(line)
    if not r.stdout:
        print(f"{pkg}: NOT INSTALLED")
    print()

print("=" * 55)
print("PostgresSaver introspection")
print("=" * 55)
try:
    from langgraph.checkpoint.postgres import PostgresSaver
    import inspect

    print(f"Class location : {inspect.getfile(PostgresSaver)}")
    print()

    for m in ["__init__", "from_conn_string", "setup",
              "__enter__", "__exit__", "__aenter__", "__aexit__"]:
        exists = hasattr(PostgresSaver, m)
        if exists:
            try:
                sig = inspect.signature(getattr(PostgresSaver, m))
                print(f"  {m}{sig}")
            except Exception:
                print(f"  {m} — (no inspectable sig)")
        else:
            print(f"  {m} — MISSING")

    print()
    print("Is context manager (sync) :", hasattr(PostgresSaver, "__enter__"))
    print("Is context manager (async):", hasattr(PostgresSaver, "__aenter__"))

except ImportError as e:
    print(f"Cannot import PostgresSaver: {e}")
