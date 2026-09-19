from pydantic import BaseModel


class BlockAisleRequest(BaseModel):
    row: int
    col: int


class SetModeRequest(BaseModel):
    mode: str  # "decentralized" | "stop_and_wait"
