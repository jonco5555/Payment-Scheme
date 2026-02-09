from pydantic import BaseModel


class G1_Point(BaseModel):
    x: int
    y: int


class KeyShare(BaseModel):
    id: int
    share: int
    public_key: G1_Point
