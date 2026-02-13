from py_ecc.typing import Optimized_Field, Optimized_Point3D
from pydantic import BaseModel
from py_ecc.optimized_bls12_381 import normalize, FQ, FQ2


class G1_Point(BaseModel):
    x: int
    y: int

    @staticmethod
    def from_g1(point: Optimized_Point3D[Optimized_Field]) -> "G1_Point":
        x, y = normalize(point)
        return G1_Point(x=x.n, y=y.n)

    def to_g1(self) -> Optimized_Point3D[Optimized_Field]:
        return (FQ(self.x), FQ(self.y), FQ.one())


class FQ2_Point(BaseModel):
    c0: int
    c1: int

    @staticmethod
    def from_fq2(point: FQ2) -> "FQ2_Point":
        return FQ2_Point(c0=point.coeffs[0], c1=point.coeffs[1])

    def to_fq2(self) -> FQ2:
        return FQ2((self.c0, self.c1))


class G2_Point(BaseModel):
    x: FQ2_Point
    y: FQ2_Point

    @staticmethod
    def from_g2(point: Optimized_Point3D[Optimized_Field]) -> "G2_Point":
        x, y = normalize(point)
        return G2_Point(x=FQ2_Point.from_fq2(x), y=FQ2_Point.from_fq2(y))

    def to_g2(self) -> Optimized_Point3D[Optimized_Field]:
        return (self.x.to_fq2(), self.y.to_fq2(), FQ2.one())


class KeyShare(BaseModel):
    id: int
    share: int
    public_key: G1_Point


class PartialSignature(BaseModel):
    id: int
    signature: G2_Point
