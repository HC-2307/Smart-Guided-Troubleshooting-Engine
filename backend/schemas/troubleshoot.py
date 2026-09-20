from pydantic import BaseModel

class TroubleshootRequest(BaseModel): #define the schema of request
    query: str

class TroubleshootResponse(BaseModel): # define the schema of resposne
    goal: str
    title: str
    scope: str
    actions: list