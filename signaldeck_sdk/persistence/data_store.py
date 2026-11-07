import time, json
from typing import Any, Literal, Mapping, Optional, Sequence
from dataclasses import dataclass
import pandas as pd
from .field import Field
from datetime import datetime
from zoneinfo import ZoneInfo

@dataclass(frozen=True)
class RecordsPage:
    """One ordered page of persisted records and a continuation cursor."""

    records: pd.DataFrame
    next_cursor: str | None = None


class DataStore:
    def __init__(self,loop,config):
        self._loop = loop
        self.config = config
        self.fields = []

    def should_save(self,data, prev_data, persist_config):
        if persist_config is None:
            return False
        if not hasattr(self,"_last_action_time"):
            self._last_action_time={}
        if "saveCondition" in persist_config.keys():
            field=persist_config["saveCondition"].get("field",None)
            condition = persist_config["saveCondition"].get("condition",{"op":"eq","value":-10000000}) #Default never true
            if field is None:   
                return False
            value = data.get(field,None)
            if value is None:
                return False  
            prev_value = None
            if prev_data is not None:
                prev_value = prev_data.get(field,None)  
            firstConitionMatch = True
            if condition.get("onlyFirst",False):
                firstConitionMatch = value != prev_value
            if not firstConitionMatch:
                return False
            if condition["op"] == "eq":
                return value == condition["value"]
            elif condition["op"] == "gt":   
                return value > condition["value"]
            elif condition["op"] == "lt":   
                return value < condition["value"]
            elif condition["op"] == "gte":   
                return value >= condition["value"]
            elif condition["op"] == "lte":   
                return value <= condition["value"]
        min_interval = persist_config.get("minInterval",{}).get("value",0) # Sekunden
        now = time.time()
        # erste Ausführung oder genug Zeit vergangen?
        key = json.dumps(persist_config)
        lastSave= self._last_action_time.get(key,0)
        if lastSave is None or (now - lastSave) >= min_interval:
            self._last_action_time[key] = now
            return True

        return False

    def register_field(
            self, field: Field
        ) -> Field:
        self.fields.append(field)

    def get_fields(self):
        return self.fields
    
    def assure_tz_aware(self,date: datetime,config) -> datetime:
        if date.tzinfo is None:
            return date.replace(tzinfo=ZoneInfo(config.get("timezone","Europe/Berlin")))
        return date

    def use_previous_value(self,persist_config):
        return persist_config.get('saveCondition',{}).get("pre",False)
    
    def get_first_from_day(self,processor_name,fieldName,askedDate,config):
        raise NotImplementedError("Must implement get_first_from_day method in subclass")
    
    def get_last_from_day(self,processor_name,fieldName,askedDate,config):
        raise NotImplementedError("Must implement get_last_from_day method in subclass")

    def get_full_day(self,processor_name,fieldName,askedDate,config):
        raise NotImplementedError("Must implement get_full_day method in subclass")
    
    def get_best_value(self,processor_name,fieldName,askedDate,config):
        raise NotImplementedError("Must implement get_best_value method in subclass")    
    
    def get_current_vals(self,processor_name,config):
        raise NotImplementedError("Must implement get_current_vals in subclass") 

    def save(self,processor_name,data,persist_config):
        raise NotImplementedError("Must implement save method in subclass")
    
    def query_records(
        self,
        processor_name: str,
        fields: Sequence[str],
        config: dict,
        *,
        filters: Mapping[str, Any] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        order: Literal["asc", "desc"] = "asc",
    ) -> RecordsPage:
        """Query rows with optional equality filters and keyset pagination.

        Date bounds are inclusive at the start and exclusive at the end.
        A store without query support must raise NotImplementedError.
        """
        raise NotImplementedError("This DataStore does not implement query_records")

    def backup(self):
        raise NotImplementedError("Must implement backup method in subclass")