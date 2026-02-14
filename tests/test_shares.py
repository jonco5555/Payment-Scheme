from py_ecc.optimized_bls12_381 import curve_order

from payment.crypto.shares import (
    blind_message,
    combine_partial_signatures,
    evaluate_polynomial,
    generate_blinding_factor,
    generate_polynomial,
    generate_shares,
    lagrange_coefficient,
    partial_blind_sign,
    partial_sign,
    reconstruct_secret,
    unblind_signature,
    verify_signature,
)


def test_generate_polynomial_length():
    coeffs = generate_polynomial(3)
    assert len(coeffs) == 4


def test_generate_polynomial_randomness():
    poly1 = generate_polynomial(5)
    poly2 = generate_polynomial(5)
    assert poly1 != poly2


def test_evaluate_polynomial_constant():
    coeffs = [42]
    assert evaluate_polynomial(coeffs, 0) == 42
    assert evaluate_polynomial(coeffs, 100) == 42


def test_evaluate_polynomial_linear():
    coeffs = [5, 3]  # g(x) = 5 + 3x
    assert evaluate_polynomial(coeffs, 0) == 5
    assert evaluate_polynomial(coeffs, 1) == 8
    assert evaluate_polynomial(coeffs, 2) == 11


def test_lagrange_coefficient_sum():
    points = [1, 2, 3]
    lambda_1 = lagrange_coefficient(1, points)
    lambda_2 = lagrange_coefficient(2, points)
    lambda_3 = lagrange_coefficient(3, points)
    assert (lambda_1 + lambda_2 + lambda_3) % curve_order == 1


def test_lagrange_reconstruction():
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
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)
    assert len(shares) == n


def test_generate_shares_ids():
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)
    ids = [share.id for share in shares]
    assert ids == [1, 2, 3, 4, 5]


def test_reconstruct_with_threshold():
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)

    subset = shares[: f + 1]
    reconstructed = reconstruct_secret(subset)

    assert reconstructed == secret_key


def test_reconstruct_with_all_shares():
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)
    reconstructed = reconstruct_secret(shares)
    assert reconstructed == secret_key


def test_insufficient_shares_fails():
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)

    subset = shares[:f]
    reconstructed = reconstruct_secret(subset)

    assert reconstructed != secret_key


def test_partial_sign_deterministic():
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)

    message = b"test message"
    sig1 = partial_sign(message, shares[0])
    sig2 = partial_sign(message, shares[0])

    assert sig1.signature == sig2.signature


def test_combine_and_verify():
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)

    message = b"test message"
    partial_sigs = [partial_sign(message, share) for share in shares[: f + 1]]
    combined_sig = combine_partial_signatures(partial_sigs)

    public_key = shares[0].public_key
    assert verify_signature(message, combined_sig, public_key)


def test_different_subsets_same_signature():
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
    n, f = 5, 2
    secret_key, shares = generate_shares(n, f)

    message1 = b"original"
    message2 = b"tampered"

    partial_sigs = [partial_sign(message1, share) for share in shares[: f + 1]]
    signature = combine_partial_signatures(partial_sigs)

    public_key = shares[0].public_key
    assert not verify_signature(message2, signature, public_key)


def test_signature_invalid_for_wrong_key():
    n, f = 5, 2

    secret_key1, shares1 = generate_shares(n, f)
    secret_key2, shares2 = generate_shares(n, f)

    message = b"test"
    partial_sigs = [partial_sign(message, share) for share in shares1[: f + 1]]
    signature = combine_partial_signatures(partial_sigs)

    wrong_key = shares2[0].public_key
    assert not verify_signature(message, signature, wrong_key)


# ---------------------------------------------------------------------------
# Blind signing
# ---------------------------------------------------------------------------


def test_blind_sign_end_to_end():
    n, f = 5, 2
    _sk, shares = generate_shares(n, f)
    pk = shares[0].public_key

    message = b"token-public-key-bytes"
    r = generate_blinding_factor()

    # Client blinds
    blinded = blind_message(message, r)

    # f+1 servers each partially sign the blinded point
    partial_sigs = [partial_blind_sign(blinded, share) for share in shares[: f + 1]]

    # Client combines and unblinds
    combined_blind = combine_partial_signatures(partial_sigs)
    signature = unblind_signature(combined_blind, r)

    # Resulting signature is a valid BLS signature on the original message
    assert verify_signature(message, signature, pk)


def test_blind_sign_different_blinding_factors():
    n, f = 5, 2
    _sk, shares = generate_shares(n, f)

    message = b"same-message"
    r1 = generate_blinding_factor()
    r2 = generate_blinding_factor()

    def blind_sign_flow(r):
        blinded = blind_message(message, r)
        partials = [partial_blind_sign(blinded, s) for s in shares[: f + 1]]
        combined = combine_partial_signatures(partials)
        return unblind_signature(combined, r)

    sig1 = blind_sign_flow(r1)
    sig2 = blind_sign_flow(r2)

    assert sig1 == sig2


def test_blinded_points_are_unlinkable():
    message = b"token-pk"
    r1 = generate_blinding_factor()
    r2 = generate_blinding_factor()

    b1 = blind_message(message, r1)
    b2 = blind_message(message, r2)

    assert b1 != b2


def test_blind_signature_invalid_for_wrong_message():
    n, f = 5, 2
    _sk, shares = generate_shares(n, f)
    pk = shares[0].public_key

    r = generate_blinding_factor()
    blinded = blind_message(b"real-message", r)
    partials = [partial_blind_sign(blinded, s) for s in shares[: f + 1]]
    combined = combine_partial_signatures(partials)
    signature = unblind_signature(combined, r)

    assert not verify_signature(b"other-message", signature, pk)
