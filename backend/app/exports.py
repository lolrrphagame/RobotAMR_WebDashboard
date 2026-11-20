"""Bounded event queries and CSV exports (UTC ISO timestamps, escaped cells)."""
import csv
import io


def filter_events(events, level="all", query=""):
    needle = query.casefold()
    return [event for event in events if (level == "all" or event["level"] == level)
            and needle in event["message"].casefold()]


def csv_export(rows, columns):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        values = []
        for column in columns:
            value = row.get(column, "")
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return output.getvalue()
