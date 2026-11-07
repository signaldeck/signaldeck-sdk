from pathlib import Path
from datetime import datetime, timedelta, time
import pandas as pd
import numpy as np
from typing import Any, Dict, List, Literal, Mapping, Sequence
from zoneinfo import ZoneInfo
from collections import deque
from .data_store import DataStore, RecordsPage
from .field import Field


class PersistData:  # Mixin to handle created data. With or without persisting 

    def __init__(self,name,config,ctx,vP,collect_data):
        super().__init__(name,config,ctx,vP,collect_data)
        self.dataStores: Dict[str,DataStore]={}
        self.currentVals={}
        self.prev_curVal={}
        self.config["processor_name"]=name
        self.memory: dict[str, deque] = {}

    def _getRequiredDataStores(self,config=None) -> List[str]:
        if not config:
            config=self.config
        return [e["type"] for e in config.get("persist",[])  if "type" in e]

    def registerDataStores(self,dataStores:Dict[str,DataStore]):
        self.logger.info(f'Registering data stores for processor {self.name}: {self._getRequiredDataStores()}')
        for dataStoreName in self._getRequiredDataStores():
            if dataStoreName in dataStores:
                self.dataStores[dataStoreName]=dataStores[dataStoreName]
            else:
                self.logger.warning(f'Required data store {dataStoreName} not found!')
        self._registerFieldsForDataStores()

    def init_current_vals(self,config=None):
        if not config:
            config = self.config
        if "persist" not in config:
            return None
        persistConfig= config["persist"][0]
        data= self.dataStores[persistConfig["type"]].get_current_vals(config["processor_name"],persistConfig)
        if data:
            self.setCurVal(data,config=config)
            self.makeDataAvailable(config=config)
            return data


    def _registerFieldsForDataStores(self):
        if not hasattr(self,"dataStores"):
            return
        for dataStoreName in self.dataStores:
            for persistConfig in self.config.get("persist",[]):
                if persistConfig["type"] != dataStoreName:
                    continue
                fields = self.getFields(config=persistConfig)
                if fields is None:
                    self.logger.warning(f'No fields defined for processor {self.name}, cannot register data store {dataStoreName}!')
                    continue
                self.logger.info(f'Registering fields for data store {dataStoreName} and processor {self.name}: {fields}')
                for field in fields:
                    self.dataStores[dataStoreName].register_field(field)



    def getFields(self,config, postfix_name= "") -> List[Field]:
        return [Field(processor_name=self.name+postfix_name, **data) for data in config.get("fields",[])]


    def getFieldNames(self,config,postfix_name="") -> List[str]:
        return [f.name for f in self.getFields(config,postfix_name)]


    def setCurVal(self,curVal,config=None):
        if hasattr(self,"currVal"):
            self.prev_curVal = self.currVal
        self.currVal=curVal


    def add_memory(self,data,config):
        if config.get("cacheSize",0) <= 0:
            return
        if config["processor_name"] not in self.memory and config.get("cacheSize",0) > 0:
            maxlen = config.get("cacheSize",1000)
            self.memory[config["processor_name"]] = deque(maxlen=maxlen)
        self.memory[config["processor_name"]].append(data)


    def save_data(self, data, prev_data = None, config=None):
        """
        Public API: entscheidet, ob wir sync oder async schreiben.
        Kann im normalen Code einfach aufgerufen werden,
        oder in async-Coroutine via `await`, wenn Du möchtest.
        """
        if not config:
            config=self.config
        self.add_memory(data,config=config)
        self.setCurVal(data,config=config)
        self.makeDataAvailable(config=config)
        for dataStoreConfig in config.get("persist",[]):
            if self.dataStores[dataStoreConfig["type"]].should_save(data=data, prev_data= self.prev_curVal ,persist_config=dataStoreConfig):
                data_to_store = data
                if self.dataStores[dataStoreConfig["type"]].use_previous_value(persist_config=dataStoreConfig):
                    if prev_data is not None:
                        data_to_store = prev_data
                    else:
                        data_to_store = self.prev_curVal
                data_to_store = {k: v for k, v in data_to_store.items() if k in self.getFieldNames(dataStoreConfig)}
                self.dataStores[dataStoreConfig["type"]].save(config["processor_name"],data_to_store,persist_config=dataStoreConfig)
       
    
    def getDateFormat(self,config=None):
        return "%d.%m.%Y %H:%M:%S"

    def makeDataAvailable(self,config=None):
        if not hasattr(self,"currVal"):
            return
        for k in self.currVal.keys():
            setattr(self,k,self.currVal[k])
        if isinstance(self.date,str):
            self.date=datetime.strptime(self.date,self.getDateFormat())

    def getCurrentData(self,fieldName,config):
        if config["processor_name"] not in self.memory:
            return None
        res = pd.DataFrame(list(self.memory[config["processor_name"]]))
        res=res.set_index(self.getDateFieldName(config))
        if not fieldName in res.columns:
            return None
        return res[fieldName].dropna()
    
    def getDateFieldName(self,config):
        return "date"

    def getDfForFile(self,fileName,cacheable):
        if not cacheable:
            #Don't cache, values can change!
            if Path(fileName).exists():
                return pd.read_csv(fileName)
            else:
                return None
        if fileName not in self.cachedFiles:
            if Path(fileName).exists():
                self.cachedFiles[fileName] = pd.read_csv(fileName)
        return self.cachedFiles.get(fileName,None)    

    def getCurFieldValue(self,fieldName,**kwargs):
        return self.currVal[fieldName]

    def _query_data_store(
        self,
        fields: Sequence[str],
        *,
        config: dict | None,
        filters: Mapping[str, Any] | None,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int | None,
        cursor: str | None,
        order: Literal["asc", "desc"],
    ) -> RecordsPage:
        config = self.config if config is None else config
        if not config.get("persist"):
            return RecordsPage(pd.DataFrame(columns=list(fields)))

        persist_config = config["persist"][0]
        store = self.dataStores[persist_config["type"]]
        return store.query_records(
            config["processor_name"], fields, persist_config,
            filters=filters, date_from=date_from, date_to=date_to,
            limit=limit, cursor=cursor, order=order,
        )

    def _query_date_bounds(self, days, config, date_from, date_to):
        if date_from is not None or date_to is not None or days is None:
            return date_from, date_to
        if not isinstance(days, int) or days < 1:
            raise ValueError("days must be a positive integer or None")
        persist_config = (config.get("persist") or [{}])[0]
        zone = ZoneInfo(persist_config.get("timezone", config.get("timezone", "Europe/Berlin")))
        now = self.ctx.date.now()
        today = now.astimezone(zone).date() if now.tzinfo else now.date()
        start = datetime.combine(today - timedelta(days=days - 1), time.min, tzinfo=zone)
        end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=zone)
        return start, end

    def get_records(
        self,
        fields,
        days=1,
        config=None,
        *,
        filters: Mapping[str, Any] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        order: Literal["asc", "desc"] = "asc",
    ):
        # Preserve the original daily hist()-based path exactly for existing callers.
        if filters is not None or date_from is not None or date_to is not None or days is None or order != "asc":
            cfg = self.config if config is None else config
            start, end = self._query_date_bounds(days, cfg, date_from, date_to)
            return self._query_data_store(
                fields, config=cfg, filters=filters,
                date_from=start, date_to=end,
                limit=None, cursor=None, order=order,
            ).records

        frames = []

        for day in range(days):
            field_series = []

            for field in fields:
                series = self.hist(
                    field,
                    config=config,
                    days=day,
                    fullDay=True,
                )

                if series is not None:
                    field_series.append(
                        series.rename(field)
                    )

            if field_series:
                frames.append(
                    pd.concat(
                        field_series,
                        axis=1,
                        join="outer",
                    )
                )

        if not frames:
            return pd.DataFrame(columns=fields)

        result = pd.concat(frames)
        result.sort_index(inplace=True)

        return result

    def get_records_page(
        self,
        fields: Sequence[str],
        *,
        filters: Mapping[str, Any] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 500,
        cursor: str | None = None,
        order: Literal["asc", "desc"] = "asc",
        config: dict | None = None,
    ) -> RecordsPage:
        """Paginate all matching records (no implicit age limit)."""
        if not isinstance(limit, int) or not 1 <= limit <= 10_000:
            raise ValueError("limit must be between 1 and 10000")
        return self._query_data_store(
            fields, config=config, filters=filters,
            date_from=date_from, date_to=date_to,
            limit=limit, cursor=cursor, order=order,
        )

    def hist(self,fieldName,config=None,days=1,date=None,first=False,last=False,dropna=True,fullDay=False,recursive=True,current=False,currentValues=False,**kwargs):
        if config is None:
            config=self.config
        if currentValues:
            return self.getCurrentData(fieldName,config)
        if "persist" not in config:
            return None
        
        askedDate = date
        if askedDate is None:
            askedDate=self.ctx.date.now() 
        askedDate= askedDate + timedelta(days=-days)

        if last and datetime.combine(askedDate,time.min) == datetime.combine(datetime.now(),time.min):
            return self.getCurFieldValue(fieldName,**kwargs)
        
        persistConfig= config["persist"][0]

        if first:
            return self.dataStores[persistConfig["type"]].get_first_from_day(config["processor_name"],fieldName,askedDate,config=persistConfig)
        if last:
            return self.dataStores[persistConfig["type"]].get_last_from_day(config["processor_name"],fieldName,askedDate,config=persistConfig)
        if fullDay: 
            return self.dataStores[persistConfig["type"]].get_full_day(config["processor_name"],fieldName,askedDate,config=persistConfig)

        return self.dataStores[persistConfig["type"]].get_best_value(config["processor_name"],fieldName,askedDate,config=persistConfig)
