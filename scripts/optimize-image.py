#!/usr/bin/env python3
"""Optimize images for the RBRL website.

Usage: python3 scripts/optimize-image.py <input> [output] [--width 500] [--quality 75]

Resizes and compresses JPEG/PNG images for web use.
Default: 500px wide, quality 75 (good for 250px display on retina screens).
"""
import sys
import os
from PIL import Image

def optimize(input_path, output_path=None, max_width=500, quality=75):
    if output_path is None:
        output_path = input_path

    img = Image.open(input_path)
    original_size = os.path.getsize(input_path)

    # Resize if wider than max_width
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    # Convert RGBA to RGB for JPEG
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')

    img.save(output_path, 'JPEG', quality=quality, optimize=True)
    new_size = os.path.getsize(output_path)

    print(f"  Input:  {input_path} ({original_size // 1024}KB, {img.width}x{img.height})")
    print(f"  Output: {output_path} ({new_size // 1024}KB)")
    print(f"  Saved:  {(original_size - new_size) // 1024}KB ({100 - (new_size * 100 // original_size)}%)")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    optimize(input_path, output_path)
