import os
import sys
import urllib.request
from pathlib import Path


def main() -> None:
    model_url = os.getenv("GPT_OSS_MODEL_URL")
    model_name = os.getenv("GPT_OSS_MODEL_FILENAME", "gpt-oss-20b.gguf")
    target_dir = Path(os.getenv("GPT_OSS_MODEL_DIR", "models")).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / model_name

    if target_path.exists():
        print(target_path)
        return

    if not model_url:
        raise SystemExit("GPT_OSS_MODEL_URL is not set")

    tmp_path = target_path.with_suffix(target_path.suffix + ".part")
    with urllib.request.urlopen(model_url) as response, open(tmp_path, "wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    tmp_path.replace(target_path)
    print(target_path)


if __name__ == "__main__":
    sys.exit(main())
