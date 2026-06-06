from pydantic import BaseModel

class GenerationRequest(BaseModel):
    prompt: str
