from py_ecc.optimized_bls12_381 import curve_order

from payment.crypto.shares import (
    blind_message,
    combine_partial_signatures,
    create_fresh_key_pair,
    evaluate_polynomial,
    generate_polynomial,
    generate_shares,
    lagrange_coefficient,
    partial_sign_blinded_message,
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


def test_partial_sign_blinded_message_deterministic():
    n, f = 5, 2
    _, shares = generate_shares(n, f)

    message = b"test message"
    blinded_message, _ = blind_message(message)
    sig1 = partial_sign_blinded_message(blinded_message, shares[0])
    sig2 = partial_sign_blinded_message(blinded_message, shares[0])

    assert sig1.signature == sig2.signature


def test_combine_and_verify():
    n, f = 5, 2
    _, shares = generate_shares(n, f)

    message = b"test message"
    blinded_message, r = blind_message(message)

    partial_sigs = [
        partial_sign_blinded_message(blinded_message, share)
        for share in shares[: f + 1]
    ]
    combined_sig = combine_partial_signatures(partial_sigs)
    unblinded_sig = unblind_signature(combined_sig, r)
    public_key = shares[0].public_key

    assert verify_signature(message, unblinded_sig, public_key)


def test_different_subsets_same_signature():
    n, f = 7, 3
    _, shares = generate_shares(n, f)

    message = b"test message"
    blinded_message, _ = blind_message(message)
    all_partial_sigs = [
        partial_sign_blinded_message(blinded_message, share) for share in shares
    ]

    subset1 = all_partial_sigs[0:4]
    subset2 = all_partial_sigs[3:7]

    combined1 = combine_partial_signatures(subset1)
    combined2 = combine_partial_signatures(subset2)

    assert combined1 == combined2


def test_signature_invalid_for_different_message():
    n, f = 5, 2
    _, shares = generate_shares(n, f)

    message1 = b"original"
    message2 = b"tampered"
    blinded_message1, r = blind_message(message1)

    partial_sigs = [
        partial_sign_blinded_message(blinded_message1, share)
        for share in shares[: f + 1]
    ]
    combined_sig = combine_partial_signatures(partial_sigs)
    unblinded_sig = unblind_signature(combined_sig, r)
    public_key = shares[0].public_key
    assert not verify_signature(message2, unblinded_sig, public_key)


def test_signature_invalid_for_wrong_key():
    n, f = 5, 2

    _, shares1 = generate_shares(n, f)
    _, shares2 = generate_shares(n, f)

    message = b"test"
    blinded_message, r = blind_message(message)
    partial_sigs = [
        partial_sign_blinded_message(blinded_message, share)
        for share in shares1[: f + 1]
    ]
    combined_sig = combine_partial_signatures(partial_sigs)
    unblinded_sig = unblind_signature(combined_sig, r)
    public_key = shares2[0].public_key
    assert not verify_signature(message, unblinded_sig, public_key)


def test_end_to_end_blind_signing_flow():
    n, f = 5, 2
    _, shares = generate_shares(n, f)
    public_key = shares[0].public_key

    pk, _ = create_fresh_key_pair()
    pk_bytes = pk.model_dump_json().encode()
    blinded_pk, r = blind_message(pk_bytes)

    partial_sigs = [
        partial_sign_blinded_message(blinded_pk, share) for share in shares[: f + 1]
    ]
    combined_sig = combine_partial_signatures(partial_sigs)
    unblinded_sig = unblind_signature(combined_sig, r)

    assert verify_signature(pk.model_dump_json().encode(), unblinded_sig, public_key)
