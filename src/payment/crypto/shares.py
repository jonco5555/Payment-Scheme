import secrets

from py_ecc.optimized_bls12_381.optimized_pairing import pairing
from payment.crypto.models import KeyShare, G1_Point, G2_Point, PartialSignature
from py_ecc.bls.ciphersuites import G2Basic, hash_to_G2
from py_ecc.optimized_bls12_381 import curve_order, G1, multiply, add, Z2


def generate_polynomial(degree: int) -> list[int]:
    """Generate a random polynomial of specified degree over Z_q.
    
    Creates g(x) = a_0 + a_1·x + ... + a_degree·x^degree where coefficients are
    randomly sampled from [0, q) with q being the BLS12-381 curve order.
    
    Args:
        degree: Polynomial degree (number of coefficients = degree + 1).
    
    Returns:
        List of coefficients [a_0, a_1, ..., a_degree].
    """
    return [secrets.randbelow(curve_order) for _ in range(degree + 1)]


def evaluate_polynomial(coeffs: list[int], x: int) -> int:
    """Evaluate polynomial at point x using Horner's method.
    
    Computes g(x) = a_0 + a_1·x + a_2·x² + ... mod q efficiently.
    
    Args:
        coeffs: Polynomial coefficients [a_0, a_1, ..., a_n].
        x: Evaluation point.
    
    Returns:
        g(x) mod q.
    """
    result = 0
    for a in reversed(coeffs):
        result = (result * x + a) % curve_order
    return result


def lagrange_coefficient(i: int, points: list[int]) -> int:
    """Compute Lagrange coefficient λ_i for interpolation at x=0.
    
    Computes λ_i = ∏_{j≠i} (-x_j)/(x_i - x_j) mod q, used in Lagrange interpolation
    to reconstruct g(0) = Σ_i y_i · λ_i from points {(x_i, y_i)}.
    
    Args:
        i: Index for which to compute coefficient.
        points: List of all point indices.
    
    Returns:
        Lagrange coefficient λ_i mod q.
    """
    num = 1
    den = 1
    for j in points:
        if j == i:
            continue
        num = (num * (-j)) % curve_order
        den = (den * (i - j)) % curve_order
    return (num * pow(den, curve_order - 2, curve_order)) % curve_order


def reconstruct_secret(shares: list[KeyShare]) -> int:
    """Reconstruct secret from shares using Lagrange interpolation.
    
    Computes g(0) = Σ_i s_i · λ_i mod q from shares s_i = g(i).
    Requires at least f+1 shares for a degree-f polynomial.
    
    Args:
        shares: List of KeyShare objects with id and share value.
    
    Returns:
        Reconstructed secret g(0) mod q.
    """
    return (
        sum(
            share.share
            * lagrange_coefficient(share.id, [share.id for share in shares])
            % curve_order
            for share in shares
        )
        % curve_order
    )


def generate_shares(n: int, f: int) -> tuple[int, list[KeyShare]]:
    """Generate secret and n shares using Shamir's Secret Sharing.
    
    Creates a random polynomial g(x) of degree f, then generates:
    - Secret key SK = g(0)
    - Public key PK = SK·G1
    - n shares s_i = g(i) for i = 1, ..., n
    
    Args:
        n: Total number of shares.
        f: Polynomial degree (threshold = f+1).
    
    Returns:
        Tuple of (secret_key, shares).
    """
    coeffs = generate_polynomial(f)
    secret_key = coeffs[0]
    public_key = multiply(G1, secret_key)
    return secret_key, [
        KeyShare(
            id=i,
            share=evaluate_polynomial(coeffs, i),
            public_key=G1_Point.from_g1(public_key),
        )
        for i in range(1, n + 1)
    ]


def partial_sign(message: bytes, key_share: KeyShare) -> PartialSignature:
    """Generate partial BLS signature σ_i = H(m)^{s_i}.
    
    Args:
        message: Message to sign.
        key_share: KeyShare with id and share value s_i.
    
    Returns:
        PartialSignature with id and signature point in G2.
    """
    message_point = hash_to_G2(message, G2Basic.DST, G2Basic.xmd_hash_function)
    signature = multiply(message_point, key_share.share)
    return PartialSignature(id=key_share.id, signature=G2_Point.from_g2(signature))


def combine_partial_signatures(partial_signatures: list[PartialSignature]) -> G2_Point:
    """Combine partial signatures using Lagrange interpolation in the exponent.
    
    Computes σ = Σ_i λ_i · σ_i where σ_i are partial signatures and λ_i are
    Lagrange coefficients. Results in σ = H(m)^{SK}.
    
    Args:
        partial_signatures: List of partial signatures to combine.
    
    Returns:
        Combined signature as G2_Point.
    """
    ids = [p.id for p in partial_signatures]
    signature = Z2
    for p in partial_signatures:
        lam = lagrange_coefficient(p.id, ids)
        signature = add(signature, multiply(p.signature.to_g2(), lam))
    return G2_Point.from_g2(signature)


def verify_signature(message: bytes, signature: G2_Point, public_key: G1_Point) -> bool:
    """Verify BLS signature using pairing check: e(σ, G1) = e(H(m), PK).
    
    Args:
        message: Signed message.
        signature: BLS signature σ ∈ G2.
        public_key: Public key PK ∈ G1.
    
    Returns:
        True if signature is valid, False otherwise.
    """
    message_point = hash_to_G2(message, G2Basic.DST, G2Basic.xmd_hash_function)

    lhs = pairing(signature.to_g2(), G1)
    rhs = pairing(message_point, public_key.to_g1())

    return lhs == rhs
