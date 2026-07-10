from pydantic import BaseModel, Field


class HelloData(BaseModel):
    message: str
