import os
import json

# Pfad zum Ordner mit den JSON-Dateien
folder_path = r"C:/Users/KAB-MS/Desktop/FfA_report_annotated/End-to-End"  # ggf. anpassen

import re

def clean_text(text):
    # Entfernt alle []-Tags wie [f], [d], [h], [] usw.
    text = re.sub(r"\[[^\]]*\]", "", text)
    return text.strip()


def extract_statements(data):
    f_statements = []
    d_statements = []
    h_statements = []

    def search(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                search(v)
        elif isinstance(obj, list):
            for item in obj:
                search(item)
        elif isinstance(obj, str):
            text_raw = obj.strip()
            text_lower = text_raw.lower()

            cleaned = clean_text(text_raw)

            if "[f]" in text_lower:
                f_statements.append(cleaned)
            if "[d]" in text_lower:
                d_statements.append(cleaned)
            if "[h]" in text_lower:
                h_statements.append(cleaned)

    search(data)
    return f_statements, d_statements, h_statements


# Alle JSON-Dateien durchgehen
for file_name in os.listdir(folder_path):
    if file_name.endswith(".json"):
        file_path = os.path.join(folder_path, file_name)

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        f_statements, d_statements, h_statements = extract_statements(data)

        print("=" * 60)
        print(f"JSON: {file_name}\n")

        print("F (falsche Aussagen):")
        for s in f_statements:
            print(f" - {s}")

        print("\nD (diskutable Aussagen):")
        for s in d_statements:
            print(f" - {s}")

        print("\nH (hervorzuhebende Aussagen):")
        for s in h_statements:
            print(f" - {s}")

        print("\n")

    def extract_and_count(data):

        f_statements = []
        d_statements = []
        h_statements = []

        counts = {
            "total_tags": 0,
            "d": 0,
            "f": 0,
            "h": 0
        }

        def search(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    search(v)
            elif isinstance(obj, list):
                for item in obj:
                    search(item)
            elif isinstance(obj, str):
                text_raw = obj.strip()
                text_lower = text_raw.lower()

                # ALLE Tags zählen
                tags = re.findall(r"\[[^\]]*\]", text_raw)
                counts["total_tags"] += len(tags)

                # Spezifische zählen
                if "[f]" in text_lower:
                    counts["f"] += 1
                    f_statements.append(clean_text(text_raw))

                if "[d]" in text_lower:
                    counts["d"] += 1
                    d_statements.append(clean_text(text_raw))

                if "[h]" in text_lower:
                    counts["h"] += 1
                    h_statements.append(clean_text(text_raw))

        search(data)
        return f_statements, d_statements, h_statements, counts


    # GLOBAL COUNTER
    global_counts = {
        "total_tags": 0,
        "d": 0,
        "f": 0,
        "h": 0
    }


    # Alle JSON-Dateien durchgehen
    for file_name in os.listdir(folder_path):
        if file_name.endswith(".json"):
            file_path = os.path.join(folder_path, file_name)

            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            f_statements, d_statements, h_statements, counts = extract_and_count(data)

            # GLOBAL addieren
            for k in global_counts:
                global_counts[k] += counts[k]

            print("=" * 60)
            print(f"JSON: {file_name}\n")

            print(f"Tags gesamt: {counts['total_tags']}")
            print(f"[f]: {counts['f']}")
            print(f"[d]: {counts['d']}")
            print(f"[h]: {counts['h']}")

            print("\nF (falsche Aussagen):")
            for s in f_statements:
                print(f" - {s}")

            print("\nD (diskutable Aussagen):")
            for s in d_statements:
                print(f" - {s}")

            print("\nH (hervorzuhebende Aussagen):")
            for s in h_statements:
                print(f" - {s}")

            print("\n")


    # GLOBAL OUTPUT
    print("=" * 60)
    print("GESAMT ÜBER ALLE REPORTS:\n")
    print(f"Tags gesamt: {global_counts['total_tags']}")
    print(f"[f]: {global_counts['f']}")
    print(f"[d]: {global_counts['d']}")
    print(f"[h]: {global_counts['h']}")