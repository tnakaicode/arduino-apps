import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom


def read_pv_file(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    pvs = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pvs.extend(line.split())
    return pvs


def build_xml(pvs, group="Main", period="0.1", deadband="0.01"):
    root = ET.Element("engineconfig")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xsi:noNamespaceSchemaLocation", "archive_config.xsd")

    g = ET.SubElement(root, "group")
    ET.SubElement(g, "name").text = group

    for pv in pvs:
        ch = ET.SubElement(g, "channel")
        ET.SubElement(ch, "name").text = pv
        ET.SubElement(ch, "period").text = period

        mon = ET.SubElement(ch, "monitor")
        ET.SubElement(mon, "deadband").text = deadband

    xml_str = minidom.parseString(
        ET.tostring(root, encoding="utf-8")
    ).toprettyxml(indent="  ")

    return xml_str


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pvfile", required=True)
    ap.add_argument("--out", default="engineconfig.xml")
    args = ap.parse_args()

    pvs = read_pv_file(Path(args.pvfile))

    if not pvs:
        print("ERROR: PV list is empty")
        return

    xml = build_xml(pvs)

    Path(args.out).write_text(xml, encoding="utf-8")

    print(f"OK: wrote {args.out} ({len(pvs)} PVs)")


if __name__ == "__main__":
    main()
