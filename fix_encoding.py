with open(r"C:\Users\EDY\recruiter_finance_tool\advanced_analysis\app.py", "rb") as f:
    data = f.read()

# Fix the corrupted byte sequence: \xe7\x89? -> \xe7\x89\x88 (版)
data = data.replace(b"\xe7\x89?\"\"\"", b"\xe7\x89\x88\"\"\"")

with open(r"C:\Users\EDY\recruiter_finance_tool\advanced_analysis\app.py", "wb") as f:
    f.write(data)

try:
    data.decode("utf-8")
    print("Fixed! Valid UTF-8 now.")
except UnicodeDecodeError as e:
    print(f"Still error: {e}")
    print(f"Context: {data[e.start-20:e.end+20]}")
