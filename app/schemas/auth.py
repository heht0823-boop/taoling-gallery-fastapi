from pydantic import BaseModel, ConfigDict


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra='ignore')
    username:str
    email:str|None=None
    password:str
class LoginIn(BaseModel):
    model_config =ConfigDict(extra='ignore')
    account:str
    password:str
