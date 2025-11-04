#!/usr/bin/env python3
"""freeze_company_ids.py
---------------------------------
Generate a *static* Python file with the complete, current Bluetooth Company Identifiers
(a.k.a. Manufacturer IDs) mapping, using official SIG sources (YAML) or Nordic's mirror (JSON).

Output: company_ids_static.py (by default) with:
    COMPANY_IDS = { 0x0000: "Ericsson AB", ... }
    def lookup(company_id: int) -> str: ...

Sources (authoritative & mirrors)
---------------------------------
- SIG Assigned Numbers repository (YAML):
  https://bitbucket.org/bluetooth-SIG/public/src/main/assigned_numbers/company_identifiers/company_identifiers.yaml
- SIG portal (Assigned Numbers PDF references the YAML and its last-modified date)
- Nordic Semiconductor Bluetooth Numbers Database (JSON mirror):
  https://github.com/NordicSemiconductor/bluetooth-numbers-database/blob/master/v1/company_ids.json

Notes
-----
* The output is *static*: no network at import time.
* IDs are written as 0xNNNN literals for readability and exact match with SIG.
* Names are normalized for whitespace; otherwise not modified.
* 0xFFFF is reserved by the SIG for testing; it will be included if present with its label.
"""
from __future__ import annotations
import argparse, io, json, os, re, sys, time, urllib.request

SIG_CANDIDATES = (
    # HEAD and main - Bitbucket sometimes changes default branch label
    "https://bitbucket.org/bluetooth-SIG/public/raw/HEAD/assigned_numbers/company_identifiers/company_identifiers.yaml",
    "https://bitbucket.org/bluetooth-SIG/public/raw/main/assigned_numbers/company_identifiers/company_identifiers.yaml",
)
NORDIC_CANDIDATES = (
    "https://raw.githubusercontent.com/NordicSemiconductor/bluetooth-numbers-database/master/v1/company_ids.json",
    "https://raw.githubusercontent.com/NordicSemiconductor/bluetooth-numbers-database/master/company_ids.json",
)

def _fetch(url: str, timeout: float = 20.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "freeze-company-ids/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="replace")

def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip()

def _parse_sig_yaml(text: str) -> dict[int, str] | None:
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        mapping: dict[int, str] = {}
        def _push(code_val, name_val):
            try:
                if isinstance(code_val, str) and code_val.lower().startswith("0x"):
                    code = int(code_val, 16)
                else:
                    code = int(code_val)
                mapping[code & 0xFFFF] = _normalize_name(str(name_val))
            except Exception:
                pass
        if isinstance(data, dict):
            # common structure: {'company_identifiers': [{'value': '0x004C', 'name': 'Apple, Inc.'}, ...]}
            for key in ("company_identifiers", "Company Identifiers", "values", "entries"):
                if key in data and isinstance(data[key], list):
                    for entry in data[key]:
                        if isinstance(entry, dict):
                            val = entry.get("value") or entry.get("code") or entry.get("id")
                            name = entry.get("name") or entry.get("Company") or entry.get("label")
                            if val is not None and name is not None:
                                _push(val, name)
                    if mapping:
                        return mapping
            # fallback if it's a dict of name->value
            for k, v in data.items():
                if isinstance(v, str) and v.lower().startswith("0x") or isinstance(v, int):
                    _push(v, k)
            return mapping or None
        elif isinstance(data, list):
            mapping = {}
            for entry in data:
                if isinstance(entry, dict):
                    val = entry.get("value") or entry.get("code") or entry.get("id")
                    name = entry.get("name") or entry.get("Company") or entry.get("label")
                    if val is not None and name is not None:
                        _push(val, name)
            return mapping or None
    except Exception:
        # very small hand-rolled fallback parser
        mapping: dict[int, str] = {}
        # pattern for blocks: - value: 0x004C\n  name: Apple, Inc.
        block_re = re.compile(r"(?ims)-\s*value\s*:\s*(0x[0-9A-Fa-f]{4}|\d+)\s*\n\s*name\s*:\s*(.+?)\s*(?=\n-\s*value|\Z)")
        for m in block_re.finditer(text):
            code_txt, name = m.groups()
            code = int(code_txt, 16) if code_txt.lower().startswith("0x") else int(code_txt)
            mapping[code & 0xFFFF] = _normalize_name(name)
        return mapping or None

def _parse_nordic_json(text: str) -> dict[int, str] | None:
    try:
        j = json.loads(text)
        items = j["company_ids"] if isinstance(j, dict) and "company_ids" in j else j
        mapping: dict[int, str] = {}
        for itm in items:
            code = int(itm["code"])
            name = _normalize_name(str(itm["name"]))
            mapping[code & 0xFFFF] = name
        return mapping or None
    except Exception:
        return None

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="company_ids_static.py", help="output Python file path")
    ap.add_argument("--timeout", type=float, default=20.0, help="network timeout seconds")
    args = ap.parse_args()

    mapping: dict[int, str] | None = None
    # Prefer SIG YAML
    for url in SIG_CANDIDATES:
        try:
            txt = _fetch(url, timeout=args.timeout)
        except Exception:
            continue
        mapping = _parse_sig_yaml(txt)
        if mapping:
            source = url
            break
    # Fallback: Nordic mirror
    if not mapping:
        for url in NORDIC_CANDIDATES:
            try:
                txt = _fetch(url, timeout=args.timeout)
            except Exception:
                continue
            mapping = _parse_nordic_json(txt)
            if mapping:
                source = url
                break

    if not mapping:
        print("ERROR: Could not fetch company identifiers from SIG or Nordic.", file=sys.stderr)
        return 2

    # Write static file
    lines = []
    lines.append("# Auto-generated on %s from %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), source))
    lines.append("# Source of truth: Bluetooth SIG Assigned Numbers (Company Identifiers).\n")
    lines.append("# https://www.bluetooth.com/specifications/assigned-numbers/\n\n")
    lines.append("COMPANY_IDS = {\n")
    for code in sorted(mapping.keys()):
        name = mapping[code].replace("\\", r"\\").replace('"', r'\"')
        lines.append(f"    0x{code:04X}: \"{name}\",\n")
    lines.append("}\n\n")
    lines.append("def lookup(company_id: int) -> str:\n")
    lines.append("    cid = int(company_id) & 0xFFFF\n")
    lines.append('    return COMPANY_IDS.get(cid, f"Unknown (0x{cid:04X})")\n')

    with open(args.out, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"Wrote {len(mapping)} entries to {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
