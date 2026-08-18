from typing import TypedDict, Literal
from datetime import datetime

class CandidateChange(TypedDict):
    change_id : str #unique id
    timestamp : datetime
    author : str #who
    files_changed : list[str] 
    change_type : Literal["code", "config", "dependancy"] #code change, configuration change, or dependancy bump
    lines_changed : int

class IncidentState(TypedDict): #no total=false because every field is needed
    incident_id : str #unique number
    timestamp : datetime #when
    service_name : str #what system
    symptom : str #what went wrong 
    affected_files : list[str]
    severity :  Literal["low", "medium", "high", "critical"]
    candidate_changes : list[CandidateChange] #possible commits/deployments that could have caused this
    true_cause_id : str #candidate that caused the error
    source : Literal["synthetic", "real_grounded"]




