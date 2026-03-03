import os
import secrets

from py_ecc.bls.ciphersuites import G2Basic, hash_to_G2
from py_ecc.optimized_bls12_381 import G1, Z2, add, curve_order, multiply
from py_ecc.optimized_bls12_381.optimized_pairing import pairing

from payment.crypto.models import G1_Point, G2_Point, KeyShare, PartialSignature


def generate_polynomial(degree: int) -> list[int]:
    """Generate a random polynomial of specified degree over Z_q.

    Creates g(x) = a_0 + a_1·x + ... + a_degree·x^degree where coefficients are
    randomly sampled from [0, q) with q being the BLS12-381 curve order.

    Args:
        degree: Polynomial degree (number of coefficients = degree + 1).

    Returns:
        List of coefficients [a_0, a_1, ..., a_degree].
    """

    return [secrets.randbelow(curve_order - 1) + 1 for _ in range(degree + 1)]


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


def generate_shares_to_files(n: int, f: int, shares_dir: str) -> None:
    """Generate shares and save them to files.

    Args:
        n: Total number of shares.
        f: Polynomial degree (threshold = f+1).
        shares_dir: Directory to save shares.
    """

    _, shares = generate_shares(n, f)
    for i, share in enumerate(shares):
        with open(os.path.join(shares_dir, f"share_{i}.bin"), "wb") as file:
            file.write(share.model_dump_json().encode())
    with open(os.path.join(shares_dir, "system_public_key.bin"), "wb") as file:
        file.write(shares[0].public_key.model_dump_json().encode())


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


def generate_blinding_factor() -> int:
    """Sample a random blinding factor r ∈ Z_q \\ {0}.

    Used by clients to blind a message before sending it for threshold
    signing, so that servers never see the real message point.

    Returns:
        Random non-zero scalar in [1, q).
    """

    r = secrets.randbelow(curve_order - 1) + 1  # avoid r = 0
    return r


def blind_message(message: bytes, blinding_factor: int) -> G2_Point:
    """Blind a message for threshold blind signing.

    Computes M' = r · H(m) where H maps the message to G2 and r is the
    blinding factor.  The resulting point is indistinguishable from a
    uniformly random G2 element to anyone who does not know r.

    Args:
        message: The message whose hash-to-curve point will be blinded.
        blinding_factor: Random scalar r ∈ Z_q \\ {0}.

    Returns:
        Blinded message point M' ∈ G2.
    """

    h = hash_to_G2(message, G2Basic.DST, G2Basic.xmd_hash_function)
    blinded = multiply(h, blinding_factor)
    return G2_Point.from_g2(blinded)


def partial_blind_sign(
    blinded_point: G2_Point, key_share: KeyShare
) -> PartialSignature:
    """Produce a partial signature on an already-blinded G2 point.

    Computes σ'_i = s_i · M' where s_i is the server's key share and
    M' is the blinded message point received from the client.  This is
    the only operation a server performs during blind minting or blind
    payment — it never needs to see the original message.

    Args:
        blinded_point: Blinded message M' ∈ G2 (from :func:`blind_message`).
        key_share: Server's key share with id and scalar s_i.

    Returns:
        Partial blind signature with server id and σ'_i ∈ G2.
    """

    sig = multiply(blinded_point.to_g2(), key_share.share)
    return PartialSignature(id=key_share.id, signature=G2_Point.from_g2(sig))


def unblind_signature(blinded_signature: G2_Point, blinding_factor: int) -> G2_Point:
    """Remove the blinding factor from a combined blind signature.

    Computes σ = r⁻¹ · σ' where σ' is the combined (still-blinded)
    threshold signature.  The result is a standard BLS signature
    σ = H(m)^{SK} that verifies under :func:`verify_signature`.

    The algebraic identity is:
        σ' = SK · (r · H(m)) = r · (SK · H(m))
        σ  = r⁻¹ · σ' = SK · H(m)

    Args:
        blinded_signature: Combined blinded signature σ' ∈ G2.
        blinding_factor: The same scalar r used in :func:`blind_message`.

    Returns:
        Unblinded BLS signature σ ∈ G2, valid under the system public key.
    """

    r_inv = pow(blinding_factor, curve_order - 2, curve_order)
    sig = multiply(blinded_signature.to_g2(), r_inv)
    return G2_Point.from_g2(sig)


def create_fresh_key_pair() -> tuple[G1_Point, int]:
    """Create a new public/private key pair for a client.

    Returns:
        Tuple of (public key, private key).
    """

    private_key = secrets.randbelow(curve_order - 1) + 1
    public_key = multiply(G1, private_key)
    return G1_Point.from_g1(public_key), private_key


def sign_message(message: bytes, private_key: int) -> G2_Point:
    """Sign a message using a private key.

    Returns:
        Signature as G2_Point.
    """

    message_point = hash_to_G2(message, G2Basic.DST, G2Basic.xmd_hash_function)
    signature = multiply(message_point, private_key)
    return G2_Point.from_g2(signature)
