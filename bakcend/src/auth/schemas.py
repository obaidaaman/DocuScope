from typing import Optional
from pydantic import BaseModel

class Login(BaseModel):
    email: str
    password: str

class Register(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    org_id: Optional[int] = None
    org_name: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    org_id: Optional[int] = None
