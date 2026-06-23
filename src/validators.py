from pydantic import BaseModel, EmailStr, Field

class UserCreateSchema(BaseModel):
    username: str = Field(..., min_length=3)
    email: EmailStr
    age: int = Field(..., gt=0, le=120)
