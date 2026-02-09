from py_ecc.bls12_381.bls12_381_curve import G1, G2, curve_order, multiply
from py_ecc.bls.hash_to_curve import hash_to_G2
import secrets
from payment.crypto.models import KeyShare, G1_Point
from py_ecc.optimized_bls12_381.optimized_curve import normalize
from py_ecc.bls.ciphersuites import G2Basic


def generate_polynomial(degree: int) -> list[int]:
    return [secrets.randbelow(curve_order) for _ in range(degree + 1)]


def evaluate_polynomial(coeffs: list[int], x: int) -> int:
    result = 0
    for a in reversed(coeffs):
        result = (result * x + a) % curve_order
    return result


def generate_shares(n: int, f: int) -> list[KeyShare]:
    coeffs = generate_polynomial(f)
    secret_key = coeffs[0]
    public_key = multiply(G1, secret_key)
    return [
        KeyShare(
            id=i,
            share=evaluate_polynomial(coeffs, i),
            public_key=G1_Point(x=public_key[0].n, y=public_key[1].n),
        )
        for i in range(1, n + 1)
    ]


def partial_sign(message: bytes, KeyShare: KeyShare) -> tuple[int, int]:
    # hash_to_curve = hash_to_G2(message, G2Basic.DST, G2Basic.xmd_hash_function)  // hash to G2 uses optimized with is jacobian coordinates
    # return multiply(hash_to_curve, KeyShare.share)
    return G2Basic.Sign(KeyShare.share, message)


# def combine_partial_signatures(partial_signatures: list[tuple[int, int]]) -> int:

if __name__ == "__main__":
    shares = generate_shares(5, 2)
    print(shares)
    print(partial_sign(b"Hello, world!", shares[0]))
