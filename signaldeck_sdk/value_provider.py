import asyncio
from typing import Dict, List, Tuple, Any


def getReducedFunction(func,args,params):
    def reduced_func(*a,**k):
        return func(*args,*a,**params,**k)
    return reduced_func

class ValueProvider:
    def __init__(self):
        self.values: Dict[str, Tuple[Any, str]] = {}
        self.methods: Dict[str, Tuple[Any, Any]] = {}
        self.processors: Dict[str, Any] = {}
        self.http: Dict[str, Dict[str, str]] = {}
        self.http_processors: Dict[str, Any] = {}
        self.loop: asyncio.AbstractEventLoop = None
        pass

    def registerProcessor(self,processor: Any,exportConfig):
        self.processors[processor.name]=processor
        if exportConfig is None:
            return
        vals = exportConfig.get("values",None)
        if vals is not None:
            for val in vals:
                key = list(val.keys())[0]
                if key in self.values.keys():
                    raise ValueError("Value name '"+key+"' already used")
                self.values[key]=(processor,val[key])
        methods = exportConfig.get("methods",None)
        if methods is not None:
            for meth in methods:
                name = meth["name"]
                if name in self.methods.keys():
                    raise ValueError("Method name '"+name+"' already used")
                targetMethod = meth["target_function"]
                if "args" not in meth.keys() and "params" not in meth.keys():
                    #Simple. Method is used as it is
                    self.methods[name]=(processor,getattr(processor,targetMethod))#(processor,targetMethod)
                else:
                    args= meth.get("args",[])
                    params= meth.get("params",{})
                    self.methods[name]=(processor,getReducedFunction(getattr(processor,targetMethod),args,params))
        http = exportConfig.get("http",None)
        if http is not None:
            for h in http:
                self.http[h["name"]]=h["values"]
                self.http_processors[h["name"]]=processor

    def getHttp(self, name, **kwargs):
        httPCallRes = None
        if len(kwargs) > 0:
            httPCallRes = self.http_processors[name].processHTTPCall(**kwargs)
        if httPCallRes:
            return httPCallRes
        http = self.http.get(name,{})
        if len(http) == 0:
            return http
        res= {}
        self.http_processors[name].refresh()
        for resField in http.keys():
            res[resField]=self.getValue(http[resField],refresh=False)
        return res

    def getValue(self,valueName, refresh = True):
        if valueName not in self.values:
            raise ValueError("Value name '"+valueName+"' unknown!")
        processor, field = self.values[valueName]
        if refresh:
            processor.refresh()
        return processor.getValue(field)

    def getMethodValue(self, methodName, *args,**params):
        if methodName not in self.methods:
            raise ValueError("Method name '"+methodName+"' unknown!")
        processor, method = self.methods[methodName]
        processor.refresh()
        return method(*args,**params)
        #processor.refresh()
        #return processor.getMethodValue(field,*args,**params)