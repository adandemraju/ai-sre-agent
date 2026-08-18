
import random #to randomize
import uuid #to create unique ids
from datetime import timedelta,datetime #change in time

SERVICE_FILES = {
    "checkout-service": ["checkout/cart.py", "checkout/payment.py", "checkout/session.py", "checkout/utils.py"],
    "auth-service": ["auth/login.py", "auth/tokens.py", "auth/middleware.py"],
    "search-service": ["search/index.py", "search/query.py", "search/ranking.py"],
}
AUTHOR_POOL = ["jsmith", "akumar", "mgarcia", "twong", "rpatel", "cchen", "dolsen", "ynakamura"]


def generate_candidates(incident_time, service_files, n=8):
    candidates = []
    for _ in range(n):
        offset = random.randint(1, 720) #up to 12 hours before, wide range
        candidates.append({
            "change_id" : str(uuid.uuid4()), #generates unique random id
            "timestamp" : incident_time - timedelta(minutes=offset),
            "author" : random.choice(AUTHOR_POOL), #placeholder for authors
            "files_changed" : random.sample(service_files, k = random.randint(1,3)), #chooses 1 to 3 random files in the files given
            "change_type" : random.choice(["code", "config", "dependency"]),
            "lines_changed" : random.randint(5,400), #chooses random number from 5 to 400 lines changed
        })

    return candidates

def inject_guilty_candidate(candidates, incident_time, affected_files):
    guilty = random.choice(candidates)
    guilty["timestamp"] = incident_time - timedelta(minutes=random.randint(1,20)) #make it closer to incident type
    guilty["files_changed"] = random.sample(affected_files, k = min(2,len(affected_files)))
    return guilty["change_id"] #because the guilty persons change id will become the source

def build_incident(service_name, symptom, severity, base_time):
    service_files = SERVICE_FILES[service_name]
    affected_files = random.sample(service_files, k = min(2, len(service_files)))

    candidates = generate_candidates(base_time, service_files, n = random.randint(4,10))
    true_cause_id = inject_guilty_candidate(candidates, base_time, affected_files)

    return {
        "incident_id" : str(uuid.uuid4()),
        "timestamp" : base_time,
        "service_name" : service_name,
        "symptom" : symptom,
        "affected_files" : affected_files,
        "severity" : severity,
        "candidate_changes" : candidates,
        "true_cause_id" : true_cause_id,
        "source" : "synthetic"
    }

SYMPTOMS = ["500 error rate spike", "latency increase", "job failure", "timeout spike"]
SEVERITIES = ["low", "medium", "high", "critical"]

def generate_incident_batch(n_incidents, start_time):
    incidents = []
    for _ in range(n_incidents):
        service = random.choice(list(SERVICE_FILES.keys()))
        symptom = random.choice(SYMPTOMS)
        severity = random.choice(SEVERITIES)
        base_time = start_time - timedelta(hours=random.randint(0, 24*30)) #spread over 30 days

        incidents.append(build_incident(service, symptom, severity, base_time))

    return incidents

def split_incidents(incidents, test_fraction = 0.2): #standard to split 80 training 20 test
    random.shuffle(incidents)
    split_idx = int(len(incidents) * (1 - test_fraction))
    return incidents[:split_idx], incidents[split_idx:]

#datetime serialization for json
import json

def serialize_incident(incident): #builds json safe incidents
    incident = dict(incident) #json is in dictionary form
    incident["timestamp"] = incident["timestamp"].isoformat()
    incident["candidate_changes"] = [
        {**c, "timestamp": c["timestamp"].isoformat()} for c in incident["candidate_changes"] #converts timestamp into str for every candidate
    ]
    return incident

def save_incidents(incidents, path): #builds new list of json safe versions and writes to json files
    with open(path, "w") as f:
        json.dump([serialize_incident(i) for i in incidents], f, indent=2)


if __name__ == "__main__":
    all_incidents = generate_incident_batch(n_incidents=150, start_time=datetime.now())
    train, synthetic_test = split_incidents(all_incidents)

    save_incidents(train, "data/incidents/train.json")
    save_incidents(synthetic_test, "data/incidents/synthetic_test.json")

