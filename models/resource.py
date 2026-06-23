from pydantic import BaseModel, Field

class Resource(BaseModel):
    id: str
    data: dict
    version: int = Field(default=0) # Add versioning

    def update(self, newData: dict):
        self.version += 1 # Increment version on update
        self.data.update(newData)
        return self
