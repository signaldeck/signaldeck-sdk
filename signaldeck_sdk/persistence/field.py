from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np

@dataclass
class Field:
    id: int = None
    name: str =None
    processor_id: int = -1
    unit: Optional[str] = None
    dtype: str = None
    display_name: Optional[str] = None
    processor_name: Optional[str]=None

    def is_type(self,type_values=[],default_type=False):
        if self.dtype is None:
            return default_type
        return self.dtype.lower() in type_values    

    def is_str(self):
        return self.is_type(["string", "str", "text"])
    
    def is_bool(self):
        return self.is_type(["boolean", "bool"])
        
    def is_numeric(self):
        return self.is_type(["float", "integer", "int", "double"],default_type=True)
    
    def is_date(self):
        return self.is_type(["datetime", "date"])
    
    def _ts_to_int(self, ts, config,logger) -> int:
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=ZoneInfo(config.get("timezone","Europe/Berlin")))
            epoch = ts.timestamp()
            return int(epoch * 1000) 
        logger.warning(f'Unable to parse date: {ts}')
        return None
    
    def _int_ts_to_date(self,ts,config):
        return datetime.fromtimestamp(
            ts / 1000,
            tz=ZoneInfo(config.get("timezone","Europe/Berlin")),
        )

    def handleValueToDB(self,v,data,config,logger):
        if self.is_numeric():
            try:
                val = float(v)
                if np.isnan(val):
                    logger.warning(f'Value for field "{self.name}" is nan: {v}. Skip field from record {data}')
                    return True, None
                return True, val
            except (ValueError, TypeError):
                logger.warning(f'Cannot parse numeric field "{self.name}": {v}. Skip field from record {data}')
                return True, None
        elif self.is_str():
            return False, str(v)
        elif self.is_bool():
            return True, 1.0 if v else 0.0
        elif self.is_date():
                return True, self._ts_to_int(v,config,logger)
        
    def handleValueFromDB(self,v,config):
        if self.is_numeric():
            return float(v)
        if self.is_str():
            return str(v)
        if self.is_bool():
            return bool(int(v))
        if self.is_date():
            return self._int_ts_to_date(v,config)

    def has_compatible_dtype(self, other: Field):
        if other is None:
            return False
        if self.dtype == other.dtype:
            return True
        if self.is_str():
            return other.is_str()
        if self.is_numeric():
            return other.is_numeric()
        if self.is_bool():
            return other.is_bool()
        if self.is_date():
            return other.is_date()

    def __eq__(self, other):
        return isinstance(other,Field) and self.id == other.id and self.processor_id == other.processor_id and self.processor_name == other.processor_name and self.name == other.name and self.display_name == other.display_name and self.dtype == other.dtype and self.unit == other.unit
        

    def __repr__(self):
        return f'<Field id={self.id} name={self.name} processor_id={self.processor_id} processor_name={self.processor_name} unit={self.unit} dtype={self.dtype} display_name={self.display_name}>'   