from pathlib import Path
from datetime import datetime, timedelta, time
import pandas as pd
import numpy as np
from typing import Dict, List
from .data_store import DataStore
from .field import Field


class PersistData:  # Mixin to handle created data. With or without persisting 

    def __init__(self,name,config,ctx,vP,collect_data):
        super().__init__(name,config,ctx,vP,collect_data)
        self.dataStores: Dict[str,DataStore]={}
        self.currentVals={}
        self.prev_curVal={}
        self.config["processor_name"]=name

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



    def save_data(self, data, prev_data = None, config=None):
        """
        Public API: entscheidet, ob wir sync oder async schreiben.
        Kann im normalen Code einfach aufgerufen werden,
        oder in async-Coroutine via `await`, wenn Du möchtest.
        """
        if not config:
            config=self.config
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

    def getCurrentData(self,fieldName):
        return None
    
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

    def hist(self,fieldName,config=None,days=1,date=None,first=False,last=False,dropna=True,fullDay=False,recursive=True,current=False,currentValues=False,**kwargs):
        if config is None:
            config=self.config
        if currentValues:
            return self.getCurrentData(fieldName)
        if "persist" not in config:
            return None
        
        askedDate = date
        if askedDate is None:
            askedDate=datetime.now() 
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
