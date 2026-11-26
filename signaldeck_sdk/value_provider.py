import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class ValueProviderValueInfo:
    name: str
    processor: str
    value: Any


@dataclass(frozen=True)
class ValueProviderMethodInfo:
    name: str
    processor: str


def getReducedFunction(func,args,params):
    def reduced_func(*a,**k):
        return func(*args,*a,**params,**k)
    return reduced_func

class HttpRequestError(ValueError):
    """Expected HTTP request rejection by an input processor."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class ValueProvider:
    def __init__(self):
        self.values: Dict[str, Tuple[Any, str]] = {}
        self.methods: Dict[str, Tuple[Any, Any]] = {}
        self.processors: Dict[str, Any] = {}
        self.http: Dict[str, Dict[str, str]] = {}
        self.http_processors: Dict[str, Any] = {}
        self.http_options: Dict[str, dict] = {}
        self.publish_definitions: Dict[tuple[str, str], dict] = {}
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
                self.http_options[h["name"]] = dict(h)

        for definition in exportConfig.get("publish", []):
            key = (processor.name, definition["name"])
            if key in self.publish_definitions:
                raise ValueError(f"Duplicate publisher: {key}")
            self.publish_definitions[key] = dict(definition)

    def listValues(self) -> list[ValueProviderValueInfo]:
        return [
            ValueProviderValueInfo(
                name=name,
                processor=processor.name,
                value=processor.getValue(field),
            )
            for name, (processor, field) in sorted(self.values.items())
        ]

    def listMethods(self) -> list[ValueProviderMethodInfo]:
        return [
            ValueProviderMethodInfo(
                name=name,
                processor=processor.name,
            )
            for name, (processor, _method) in sorted(self.methods.items())
        ]

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

    def dispatchHttp(self, name: str, method: str, payload: dict):
        """Route new receivers explicitly; preserve legacy parameter dispatch."""
        if name not in self.http:
            raise HttpRequestError(f"Unknown HTTP endpoint: {name}", 404)
        options = self.http_options[name]
        processor = self.http_processors[name]
        if options.get("receive", False):
            if method == "POST" or (method == "GET" and payload and options.get("allow_get", False)):
                return processor.processHTTPCall(**payload)
            if method != "GET" or not self.http[name]:
                raise HttpRequestError("HTTP method not allowed", 405)
        elif payload:
            # Existing Ecowitt and other legacy form/query receivers.
            result = processor.processHTTPCall(**payload)
            if result:
                return result
        return self.getHttp(name)

    def getPublishValues(self, mapping: dict[str, str]) -> dict[str, Any]:
        """Resolve explicitly exported values, refreshing each source once."""
        sources = {}
        for name, value_name in mapping.items():
            if value_name not in self.values:
                raise ValueError(f"Unknown exported value: {value_name}")
            sources[name] = self.values[value_name]
        refreshed = set()
        for processor, _ in sources.values():
            if id(processor) not in refreshed:
                processor.refresh()
                refreshed.add(id(processor))
        return {name: processor.getValue(field) for name, (processor, field) in sources.items()}

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