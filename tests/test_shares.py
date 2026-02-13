"""Unit tests for threshold signature shares module."""

from payment.crypto.shares import (
    generate_polynomial,
    evaluate_polynomial,
    lagrange_coefficient,
    reconstruct_secret,
    generate_shares,
    partial_sign,
    combine_partial_signatures,
    verify_signature,
)
from py_ecc.optimized_bls12_381 import curve_order


def test_generate_polynomial_length():
    """Polynomial has correct number of coefficients."""
    coeffs = generate_polynomial(3)
    assert len(coeffs) == 4


def test_generate_polynomial_randomness():
    """Generated polynomials are random."""
    poly1 = generate_polynomial(5)
    poly2 = generate_polynomial(5)
    assert poly1 != poly2


def test_evaluate_polynomial_constant():
    """Constant polynomial evaluates correctly."""
    coeffs = [42]
    assert evaluate_polynomial(coeffs, 0) == 42
    assert evaluate_polynomial(coeffs, 100) == 42


def test_evaluate_polynomial_linear():
    """Linear polynomial evaluates correctly."""
    coeffs = [5, 3]  # g(x) = 5 + 3x
    assert evaluate_polynomial(coeffs, 0) == 5
    assert evaluate_polynomial(coeffs, 1) == 8
    assert evaluate_polynomial(coeffs, 2) == 11


def test_lagrange_coefficient_sum():
    """Lagrange coefficients sum to 1 for constant polynomial."""
    points = [1, 2, 3]
    lambda_1 = lagrange_coefficient(1, points)
    lambda_2 = lagrange_coefficient(2, points)
    lambda_3 = lagrange_coefficient(3, points)
    assert (lambda_1 + lambda_2 + lambda_3) % curve_order == 1


def test_lagrange_reconstruction():
    """Lagrange interpolation reconstructs polynomial at 0."""
    coeffs = [5, 2, 3]  # g(x) = 5 + 2x + 3x^2
    secret = coeffs[0]

    points = [1, 2, 3]
    values = [evaluate_polynomial(coeffs, x) for x in points]

    reconstructed = (
        sum(
            values[i] * lagrange_coefficient(points[i], points) % curve_order
            for i in range(len(points))
        )
        % curve_order
    )

    assert reconstructed == secret


def test_generate_shares_count():
    """Correct number of shares generated."""
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)
    assert len(shares) == n


def test_generate_shares_ids():
    """Share IDs are sequential from 1 to n."""
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)
    ids = [share.id for share in shares]
    assert ids == [1, 2, 3, 4, 5]


def test_reconstruct_with_threshold():
    """Reconstruct secret with f+1 shares."""
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)

    subset = shares[: f + 1]
    reconstructed = reconstruct_secret(subset)

    assert reconstructed == secret_key


def test_reconstruct_with_all_shares():
    """Reconstruct secret with all shares."""
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)
    reconstructed = reconstruct_secret(shares)
    assert reconstructed == secret_key


def test_insufficient_shares_fails():
    """Reconstruction fails with fewer than f+1 shares."""
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)

    subset = shares[:f]
    reconstructed = reconstruct_secret(subset)

    assert reconstructed != secret_key


def test_partial_sign_deterministic():
    """Partial signing is deterministic."""
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)

    message = b"test message"
    sig1 = partial_sign(message, shares[0])
    sig2 = partial_sign(message, shares[0])

    assert sig1.signature == sig2.signature


def test_combine_and_verify():
    """Combine partial signatures and verify."""
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)

    message = b"test message"
    partial_sigs = [partial_sign(message, share) for share in shares[: f + 1]]
    combined_sig = combine_partial_signatures(partial_sigs)

    public_key = shares[0].public_key
    assert verify_signature(message, combined_sig, public_key)


def test_different_subsets_same_signature():
    """Different subsets produce the same signature."""
    n, f = 7, 3
    secret_key, shares = generate_shares(n, f)

    message = b"test message"
    all_partial_sigs = [partial_sign(message, share) for share in shares]

    subset1 = all_partial_sigs[0:4]
    subset2 = all_partial_sigs[3:7]

    combined1 = combine_partial_signatures(subset1)
    combined2 = combine_partial_signatures(subset2)

    assert combined1 == combined2


def test_signature_invalid_for_different_message():
    """Signature invalid for different message."""
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)

    message1 = b"original"
    message2 = b"tampered"

    partial_sigs = [partial_sign(message1, share) for share in shares[: f + 1]]
    signature = combine_partial_signatures(partial_sigs)

    public_key = shares[0].public_key
    assert not verify_signature(message2, signature, public_key)


def test_signature_invalid_for_wrong_key():
    """Signature invalid for different public key."""
    n, f = 5, 2

    secret_key1, shares1 = generate_shares(n, f)
    secret_key2, shares2 = generate_shares(n, f)

    message = b"test"
    partial_sigs = [partial_sign(message, share) for share in shares1[: f + 1]]
    signature = combine_partial_signatures(partial_sigs)

    wrong_key = shares2[0].public_key
    assert not verify_signature(message, signature, wrong_key)
