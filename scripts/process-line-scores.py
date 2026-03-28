#!/usr/bin/env python3
"""Convert plain-text baseball line scores to styled HTML tables.

Detects pairs of consecutive lines like:
  ROYALS     100 100 0 -2
  PIRATES    310 000 x -4

And converts them to an HTML line-score table.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "content" / "news"

# Match a line score line: team name, inning digits (groups of 1-3), dash, total
# Handles optional ** bold markers, mixed case, extra whitespace
LINE_SCORE_RE = re.compile(
    r'^\*{0,2}'              # optional leading **
    r'([A-Za-z][\w\s\']+?)'  # team name
    r'\*{0,2}'               # optional trailing ** on team name
    r'\s{2,}'                # 2+ spaces separating name from innings
    r'([\dx ]+)'             # inning scores (digits, x, spaces)
    r'\s*-\s*'               # dash separator
    r'(\d+)'                 # total runs
    r'\*{0,2}'               # optional trailing **
    r'\s*$'                  # end of line
)

# Already-processed marker
TABLE_MARKER = 'class="line-score"'


def parse_line_score(line):
    """Parse a single line score line. Returns (team, innings, total) or None."""
    m = LINE_SCORE_RE.match(line.strip())
    if not m:
        return None
    team = m.group(1).strip().strip('*')
    innings_raw = m.group(2).strip()
    total = m.group(3)

    # Split innings: could be "310 000 x" or "3 1 0 0 0 0 x"
    # First try groups of 3+ as inning-groups, then individual chars
    innings = []
    for chunk in innings_raw.split():
        if len(chunk) > 1 and chunk.isdigit():
            # Group like "310" = individual innings 3, 1, 0
            for ch in chunk:
                innings.append(ch)
        else:
            innings.append(chunk)

    return (team, innings, total)


def build_table(score1, score2):
    """Build an HTML line score table from two parsed scores."""
    team1, inn1, total1 = score1
    team2, inn2, total2 = score2

    num_innings = max(len(inn1), len(inn2))
    # Pad shorter line
    while len(inn1) < num_innings:
        inn1.append('')
    while len(inn2) < num_innings:
        inn2.append('')

    header_cells = ''.join(f'<th>{i+1}</th>' for i in range(num_innings))
    row1_cells = ''.join(f'<td>{v}</td>' for v in inn1)
    row2_cells = ''.join(f'<td>{v}</td>' for v in inn2)

    return (
        f'<table class="line-score">'
        f'<thead><tr><th></th>{header_cells}'
        f'<th class="line-score-total">R</th></tr></thead>'
        f'<tbody>'
        f'<tr><td class="line-score-team">{team1}</td>{row1_cells}'
        f'<td class="line-score-total">{total1}</td></tr>'
        f'<tr><td class="line-score-team">{team2}</td>{row2_cells}'
        f'<td class="line-score-total">{total2}</td></tr>'
        f'</tbody></table>'
    )


def process_post(filepath):
    """Process a single post. Returns True if modified."""
    text = filepath.read_text()

    if TABLE_MARKER in text:
        return False

    lines = text.split('\n')
    new_lines = []
    i = 0
    modified = False

    while i < len(lines):
        score1 = parse_line_score(lines[i])
        if score1:
            # Look ahead for second line score (may have blank line between)
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines):
                score2 = parse_line_score(lines[j])
                if score2:
                    table = build_table(score1, score2)
                    new_lines.append('')
                    new_lines.append(table)
                    new_lines.append('')
                    i = j + 1
                    modified = True
                    continue
        new_lines.append(lines[i])
        i += 1

    if modified:
        filepath.write_text('\n'.join(new_lines))

    return modified


def main():
    modified = []
    for f in NEWS_DIR.glob('*.md'):
        if f.name == '_index.md':
            continue
        if process_post(f):
            modified.append(f.name)
            print(f"Processed: {f.name}")

    if not modified:
        print("No line scores found to process.")
    else:
        print(f"\n{len(modified)} post(s) updated.")


if __name__ == "__main__":
    main()
