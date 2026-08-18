from collections import defaultdict


from collections import defaultdict

def build_author_rates(incidents) -> dict:
    appearances = defaultdict(int)
    hits = defaultdict(int)

    for incident in incidents:
        true_cause_id = incident["true_cause_id"]
        for candidate in incident["candidate_changes"]:
            author = candidate["author"]
            appearances[author] += 1
            if candidate["change_id"] == true_cause_id:
                hits[author] += 1

    author_rates = {}
    for author in appearances:
        author_rates[author] = hits[author] / appearances[author]

    return author_rates


CHANGE_TYPE_RISK = {
    "code": 0.6,
    "config": 0.3,
    "dependency": 0.5,
}

def compute_features(incident_timestamp, candidate, affected_files, author_rates):
    time_delta_minutes = max(0, (incident_timestamp - candidate["timestamp"]).total_seconds() / 60)
    file_overlap = len(set(candidate["files_changed"]) & set(affected_files))

    lines_changed = candidate["lines_changed"]
    author_incident_rate = author_rates.get(candidate["author"], 0)
    change_type_risk = CHANGE_TYPE_RISK[candidate["change_type"]]

    result = {
        "time_delta_minutes" : time_delta_minutes,
        "file_overlap" : file_overlap,
        "lines_changed" : lines_changed,
        "author_incident_rate" : author_incident_rate,
        "change_type_risk" : change_type_risk
    }

    return result


