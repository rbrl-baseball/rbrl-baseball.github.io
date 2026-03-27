#!/usr/bin/env python3
"""Process news posts from Pages CMS.

Finds markdown images in news posts and promotes the first one to use the
article-image shortcode for proper floating layout.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "content" / "news"

# Match standard markdown images: ![alt](src)
MD_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

# Match the article-image shortcode (already processed)
SHORTCODE_RE = re.compile(r'\{\{<\s*article-image\s')


def process_post(filepath):
    """Process a single news post. Returns True if modified."""
    text = filepath.read_text()

    # Skip if already has an article-image shortcode
    if SHORTCODE_RE.search(text):
        return False

    # Split frontmatter from body
    parts = text.split('---', 2)
    if len(parts) < 3:
        return False

    frontmatter = parts[1]
    body = parts[2]

    # Find the first markdown image in the body
    match = MD_IMAGE_RE.search(body)
    if not match:
        return False

    alt = match.group(1) or filepath.stem.replace('-', ' ').title()
    src = match.group(2)

    # Replace the first image with the shortcode
    shortcode = '{{< article-image src="' + src + '" alt="' + alt + '" >}}'

    # Remove the original markdown image
    body_new = body[:match.start()] + body[match.end():]

    # Strip leading blank lines from body, then prepend shortcode
    body_new = body_new.lstrip('\n')
    body_new = '\n' + shortcode + '\n\n' + body_new

    new_text = '---' + frontmatter + '---' + body_new
    filepath.write_text(new_text)
    return True


def main():
    modified = []
    for f in NEWS_DIR.glob('*.md'):
        if f.name == '_index.md':
            continue
        if process_post(f):
            modified.append(f.name)
            print(f"Processed: {f.name}")

    if not modified:
        print("No posts needed image processing.")
    else:
        print(f"\n{len(modified)} post(s) updated.")

    return len(modified)


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
