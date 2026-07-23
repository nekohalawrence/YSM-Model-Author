#!/usr/bin/env python3
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2] / "models"
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
PREVIEW_MARKER = re.compile(r'preview', re.I)
START_MARKER = '<!-- GENERATED MODEL PREVIEW README START -->'
END_MARKER = '<!-- GENERATED MODEL PREVIEW README END -->'


def is_preview_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTS and PREVIEW_MARKER.search(path.stem)


def collect_preview_images(model_dir: Path) -> list[Path]:
    images = []
    for candidate in [model_dir, model_dir / 'previews']:
        if candidate.is_dir():
            for file_path in sorted(candidate.iterdir()):
                if is_preview_image(file_path):
                    images.append(file_path)
    return images


def should_generate(readme_path: Path) -> bool:
    if not readme_path.exists():
        return True
    text = readme_path.read_text(encoding='utf-8', errors='ignore')
    return START_MARKER in text and END_MARKER in text


def build_readme_content(model_dir: Path, image_paths: list[Path]) -> str:
    title = model_dir.name
    lines = [
        f"# {title}",
        "",
        "> 此 README 由 `.github/scripts/generate_model_readmes.py` 自动生成。",
        "",
        "## 预览图",
        "",
        START_MARKER,
        "",
    ]

    for image_path in image_paths:
        rel_path = image_path.relative_to(model_dir).as_posix()
        lines.append(f"![{image_path.name}]({rel_path})")
        lines.append("")

    lines.extend([
        END_MARKER,
        "",
    ])
    return "\n".join(lines)


def is_author_dir(path: Path) -> bool:
    return path.is_dir() and path.name.isdigit() and len(path.name) == 4


def main() -> int:
    if not ROOT_DIR.is_dir():
        print(f"Error: models directory not found at {ROOT_DIR}")
        return 1

    updated = 0
    skipped = 0
    created = 0

    for author_dir in sorted(ROOT_DIR.iterdir()):
        if not is_author_dir(author_dir):
            continue

        for model_dir in sorted(author_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            if model_dir.name.startswith('.') or model_dir.name == 'previews':
                continue

            preview_images = collect_preview_images(model_dir)
            if not preview_images:
                continue

            readme_path = model_dir / 'README.md'
            if readme_path.exists() and not should_generate(readme_path):
                skipped += 1
                continue

            new_content = build_readme_content(model_dir, preview_images)
            if readme_path.exists():
                existing_content = readme_path.read_text(encoding='utf-8', errors='ignore')
                if existing_content == new_content:
                    continue
                action = 'Updated'
                updated += 1
            else:
                action = 'Created'
                created += 1

            readme_path.write_text(new_content, encoding='utf-8')
            print(f"{action} {readme_path.relative_to(ROOT_DIR.parent)}")

    print(f"Summary: created={created}, updated={updated}, skipped={skipped}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
