import py_compile
import pathlib
import sys

failed = []
for p in pathlib.Path('bot').rglob('*.py'):
    try:
        py_compile.compile(str(p), doraise=True)
    except Exception as e:
        failed.append((str(p), str(e)))

if failed:
    for f in failed:
        print(f"{f[0]}: {f[1]}")
    sys.exit(1)
print('OK')
