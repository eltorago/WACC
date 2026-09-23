"""Private parser worker: bounded local input, JSON output, no external commands."""
import json
import sys
from .documents import extract
from .contracts import PolicyError


def main():
    try:
        request = json.loads(sys.stdin.buffer.read(32768))
        if request.get('framework'):
            from .framework_import import parse
            result = parse(request['framework'], request['path'])
        else:
            result = extract(request["path"])
    except PolicyError as error:
        result = {"error": str(error)}
    except Exception:
        result = {"error": "The document could not be parsed safely. Use a text copy or inspect it manually."}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
