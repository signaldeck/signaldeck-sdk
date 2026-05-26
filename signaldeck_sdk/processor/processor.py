import asyncio, json
import pandas as pd
import logging
from dataclasses import dataclass
from typing import List, Tuple, Any 
from pathlib import Path
from ..cmd import Cmd
from importlib import resources
from ..value_provider import ValueProvider
from ..context import ApplicationContext

@dataclass(frozen=True)
class Placeholder:
    name: str                 # e.g. "HOST" (matches $HOST$)
    prompt: str               # what user sees
    type: str = "str"         # str|int|float|bool|path|secret
    default: Any | None = None
    help: str | None = None

class Processor:

    def __init__(self,name,config,ctx: ApplicationContext,valueProvider,collect_data):
        self.config=config
        self.cachedFiles={}
        self.ctx: ApplicationContext=ctx
        self.name=name
        self.className=None
        self.collect_data=collect_data
        self.valueProvider: ValueProvider =valueProvider
        self.logger=logging.getLogger(__name__)
        self.valueProvider.registerProcessor(self,config.get("export",None))
    
    @classmethod
    def default_config_resource(cls) -> str:
        """
        Relative resource path inside the plugin package.

        Default convention:
          samples/<ClassName>/config.json
        """
        return f"samples/{cls.__name__}/config.json"

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        """
        Loads default config JSON shipped with the plugin package.
        """
        pkg = cls.__module__.split(".", 1)[0]  # root package of plugin
        rel = cls.default_config_resource()

        try:
            data = resources.files(pkg).joinpath(rel).read_text(encoding="utf-8")
        except FileNotFoundError as e:
            return {}

        return json.loads(data)


    @classmethod
    def config_placeholders(cls) -> List[Placeholder]:
        return []
        
    def withClassName(self,className):
        self.className=className
        return self

    def get_asyncio_tasks(self,collect_data) -> List[asyncio.Future]:
        return []

    def process(self,value,actionHash,file=None,**params):
        raise NotImplementedError("to be implemented")

    def must_be_queued(self):
        if "queued" not in self.config:
            return False
        return self.config["queued"]


    def getState(self,value,actionHash):
        return ""

    def getValue(self,fieldName):
        if hasattr(self,fieldName):
            return getattr(self,fieldName)
        return None
    
    def processHTTPCall(self,**kwargs):
        return None

    def getMethodValue(self, methodName,*args,**kwargs):
        return getattr(self,methodName)(*args,**kwargs)
    
    def shutdown(self):
        pass


    def registerCommands(self, cmd: Cmd):
        return

    def getAdditionalJsAndCssFiles(self,value):
        return [self.ctx.url.forFile(f[0],f[1]) for f in self.getAdditionalJsFiles(value)], [self.ctx.url.forFile(f[0],f[1]) for f in self.getAdditionalCssFiles(value)]

    def getAdditionalJsFiles(self,value) -> List[Tuple[str, str]]:
        ''' 
        Return a list of (pluginname, path) tuples for additional JS files to include in the frontend.
        '''
        return []
    
    def getAdditionalCssFiles(self,value) -> List[Tuple[str, str]]:
        ''' 
        Return a list of (pluginname, path) tuples for additional CSS files to include in the frontend.
        '''
        return []

    def refresh(self):
        if "values" in self.config:
            for val in self.config["values"]:
                if val["type"]=="field":
                    setattr(self,val["name"],self.valueProvider.getValue(val["from"]))
                if val["type"]=="method":
                    argrs = val.get("args",[])
                    params= val.get("params",{})
                    setattr(self,val["name"],self.valueProvider.getMethodValue(val["from"],*argrs,**params))
        if "methods" in self.config:
            for method in self.config["methods"]:
                setattr(self,method["name"],self.valueProvider.methods[method["from"]][1])