from py_ecc.optimized_bls12_381 import FQ, FQ2, normalize
from py_ecc.typing import Optimized_Field, Optimized_Point3D
from pydantic import BaseModel, ConfigDict


class G1_Point(BaseModel):
    model_config = ConfigDict(frozen=True)
    x: int
    y: int

    @staticmethod
    def from_g1(point: Optimized_Point3D[Optimized_Field]) -> "G1_Point":
        """Convert a projective py_ecc G1 point to affine representation.

        Args:
            point: Projective G1 point from py_ecc.

        Returns:
            Affine G1_Point.
        """
        x, y = normalize(point)
        return G1_Point(x=x.n, y=y.n)

    def to_g1(self) -> Optimized_Point3D[Optimized_Field]:
        """Convert back to a projective py_ecc G1 point.

        Returns:
            Projective G1 point for use with py_ecc.
        """
        return (FQ(self.x), FQ(self.y), FQ.one())


class FQ2_Point(BaseModel):
    model_config = ConfigDict(frozen=True)

    c0: int
    c1: int

    @staticmethod
    def from_fq2(point: FQ2) -> "FQ2_Point":
        """Convert a py_ecc FQ2 element to serializable form.

        Args:
            point: FQ2 element from py_ecc.

        Returns:
            FQ2_Point with integer coefficients.
        """
        return FQ2_Point(c0=point.coeffs[0], c1=point.coeffs[1])

    def to_fq2(self) -> FQ2:
        """Convert back to a py_ecc FQ2 element.

        Returns:
            FQ2 element for use with py_ecc.
        """
        return FQ2((self.c0, self.c1))


class G2_Point(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: FQ2_Point
    y: FQ2_Point

    @staticmethod
    def from_g2(point: Optimized_Point3D[Optimized_Field]) -> "G2_Point":
        """Convert a projective py_ecc G2 point to affine representation.

        Args:
            point: Projective G2 point from py_ecc.

        Returns:
            Affine G2_Point.
        """
        x, y = normalize(point)
        return G2_Point(x=FQ2_Point.from_fq2(x), y=FQ2_Point.from_fq2(y))

    def to_g2(self) -> Optimized_Point3D[Optimized_Field]:
        """Convert back to a projective py_ecc G2 point.

        Returns:
            Projective G2 point for use with py_ecc.
        """
        return (self.x.to_fq2(), self.y.to_fq2(), FQ2.one())


class KeyShare(BaseModel):
    id: int
    share: int
    public_key: G1_Point


class PartialSignature(BaseModel):
    id: int
    signature: G2_Point
