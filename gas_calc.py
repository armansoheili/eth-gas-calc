#!/usr/bin/env python3
"""eth-gas-calc — Ethereum transaction gas-cost calculator.

Pure Python, zero dependencies. Implements the gas accounting rules from the
Ethereum Yellow Paper and the EIPs that changed them:

  Intrinsic gas
  -------------
  * G_TRANSACTION            = 21_000                     (every tx pays this)
  * Calldata: 4 gas per zero byte, 16 gas per non-zero byte (EIP-2028)
  * Contract creation:      + 32_000                     (G_TXCREATE)
  * Init-code cost:         + 2 gas per 32-byte word      (EIP-3860,
                            creation txs only)
  * Access list (EIP-2930): 2_400 per address +
                            1_900 per storage key
  * New account creation:   + 25_000                     (G_NEWACCOUNT; a
                            value transfer to a non-existent account needs a
                            state look-up, so this is an opt-in flag)

  Fee math (EIP-1559)
  -------------------
  * effective_gas_price = min(max_fee_per_gas,
                              base_fee_per_gas + max_priority_fee_per_gas)
  * max possible cost   = gas_limit * max_fee_per_gas

Run the doctests with:  python3 gas_calc.py --test
Run the CLI demo with:  python3 gas_calc.py --demo
"""

import argparse
import doctest
import sys

# ---------------------------------------------------------------- units ----
GWEI = 10 ** 9
WEI_PER_ETHER = 10 ** 18

# ------------------------------------------------- intrinsic gas constants --
TX_BASE_GAS = 21_000
ZERO_BYTE_GAS = 4          # G_TXDATAZERO    (EIP-2028)
NONZERO_BYTE_GAS = 16      # G_TXDATANONZERO (EIP-2028)
TX_CREATE_GAS = 32_000      # G_TXCREATE
INITCODE_WORD_GAS = 2       # G_INITCODEWORD  (EIP-3860)
ACCESS_LIST_ADDRESS_GAS = 2_400   # G_ACCESSLISTADDRESS (EIP-2930)
ACCESS_LIST_STORAGE_KEY_GAS = 1_900  # G_ACCESSLISTSTORAGEKEY (EIP-2930)
NEW_ACCOUNT_GAS = 25_000    # G_NEWACCOUNT


def calldata_gas(data: bytes) -> int:
    """Gas cost of transaction calldata (EIP-2028).

    >>> calldata_gas(b"")
    0
    >>> calldata_gas(bytes(100))          # 100 zero bytes
    400
    >>> calldata_gas(b"\\xff" * 10)      # 10 non-zero bytes
    160
    """
    zeros = data.count(0)
    return zeros * ZERO_BYTE_GAS + (len(data) - zeros) * NONZERO_BYTE_GAS


def access_list_gas(access_list) -> int:
    """Gas cost of an EIP-2930 access list.

    Each entry is ``(address_bytes, [storage_key_bytes, ...])``.

    >>> access_list_gas([])
    0
    >>> access_list_gas([(b"\\x11" * 20, [b"\\x22" * 32, b"\\x33" * 32])])
    6200
    """
    total = 0
    for _address, storage_keys in access_list:
        total += ACCESS_LIST_ADDRESS_GAS
        total += len(storage_keys) * ACCESS_LIST_STORAGE_KEY_GAS
    return total


def intrinsic_gas(calldata: bytes = b"", *, is_creation: bool = False,
                  access_list=(), creates_new_account: bool = False) -> int:
    """Intrinsic (up-front) gas of a transaction, before execution.

    >>> intrinsic_gas()                      # plain ETH transfer
    21000
    >>> intrinsic_gas(bytes(100))
    21400
    >>> intrinsic_gas(is_creation=True)      # empty contract deployment
    53000
    >>> # ERC-20 transfer(to, 1e18): 0xa9059cbb + padded args = 68 bytes
    >>> _data = bytes.fromhex("a9059cbb" + "00" * 12 + "11" * 20
    ...                       + "00" * 24 + "0de0b6b3a7640000")
    >>> intrinsic_gas(_data)
    21632
    >>> intrinsic_gas(b"\\xff" * 100, is_creation=True)
    54608
    """
    total = TX_BASE_GAS + calldata_gas(calldata) + access_list_gas(access_list)
    if is_creation:
        total += TX_CREATE_GAS
        # EIP-3860: 2 gas per 32-byte init-code word, rounded up.
        total += ((len(calldata) + 31) // 32) * INITCODE_WORD_GAS
    if creates_new_account:
        total += NEW_ACCOUNT_GAS
    return total


def effective_gas_price(base_fee_wei: int, max_fee_wei: int,
                        max_priority_fee_wei: int) -> int:
    """EIP-1559 effective gas price in wei.

    >>> effective_gas_price(20 * GWEI, 50 * GWEI, 2 * GWEI) == 22 * GWEI
    True
    >>> # the max-fee cap binds when base fee + tip exceeds it
    >>> effective_gas_price(20 * GWEI, 21 * GWEI, 2 * GWEI) == 21 * GWEI
    True
    >>> # priority fee can never exceed max_fee - base_fee
    >>> effective_gas_price(20 * GWEI, 20 * GWEI, 5 * GWEI) == 20 * GWEI
    True
    """
    return min(max_fee_wei, base_fee_wei + max_priority_fee_wei)


def tx_cost_wei(gas: int, gas_price_wei: int) -> int:
    """Total transaction cost in wei."""
    return gas * gas_price_wei


def fmt_wei(wei: int) -> str:
    """Human-readable wei amount, e.g. ``'0.000462 ETH'``.

    >>> fmt_wei(21_000 * 22 * GWEI)
    '0.000462 ETH (462,000,000,000,000 wei)'
    >>> fmt_wei(0)
    '0 ETH'
    """
    if wei == 0:
        return "0 ETH"
    eth = wei / WEI_PER_ETHER
    text = f"{eth:.6f}".rstrip("0").rstrip(".")
    return f"{text} ETH ({wei:,} wei)"


def demo() -> None:
    print("== eth-gas-calc demo ==\n")

    # 1) Plain ETH transfer.
    gas = intrinsic_gas()
    print(f"1. Plain ETH transfer:          {gas:,} gas")

    # 2) ERC-20 transfer(to, 1e18).
    erc20 = bytes.fromhex("a9059cbb" + "00" * 12 + "11" * 20
                          + "00" * 24 + "0de0b6b3a7640000")
    zeros = erc20.count(0)
    print(f"2. ERC-20 transfer calldata:      {len(erc20)} bytes "
          f"({zeros} zero, {len(erc20) - zeros} non-zero)")
    print(f"   intrinsic gas:                {intrinsic_gas(erc20):,} gas")

    # 3) Contract deployment with an access list.
    initcode = b"\x60\x80\x60\x40\x52" * 200  # 1_000 bytes of init code
    al = [(b"\xde" * 20, [b"\x00" * 32, b"\x01" * 32])]
    gas = intrinsic_gas(initcode, is_creation=True, access_list=al)
    print(f"3. Contract deployment (1_000B init code + access list):")
    print(f"   intrinsic gas:                {gas:,} gas")

    # 4) EIP-1559 fee breakdown for a 21_000-gas tx.
    base, tip, cap = 20 * GWEI, 2 * GWEI, 50 * GWEI
    eff = effective_gas_price(base, cap, tip)
    max_cost = tx_cost_wei(21_000, cap)
    print(f"4. EIP-1559 (base 20 / tip 2 / cap 50 gwei, 21_000 gas):")
    print(f"   effective gas price:          {eff // GWEI} gwei")
    print(f"   expected cost:                {fmt_wei(tx_cost_wei(21_000, eff))}")
    print(f"   max possible cost:            {fmt_wei(max_cost)}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Ethereum transaction gas-cost calculator.")
    parser.add_argument("--test", action="store_true",
                        help="run the doctests and exit")
    parser.add_argument("--demo", action="store_true",
                        help="print a worked example breakdown")
    parser.add_argument("--calldata", default="",
                        help="hex calldata, e.g. a9059cbb (0x prefix ok)")
    parser.add_argument("--creation", action="store_true",
                        help="transaction creates a contract")
    parser.add_argument("--base-fee-gwei", type=float, default=20.0)
    parser.add_argument("--max-priority-gwei", type=float, default=2.0)
    parser.add_argument("--max-fee-gwei", type=float, default=50.0)
    args = parser.parse_args(argv)

    if args.test:
        results = doctest.testmod(verbose=False)
        print(f"doctests: {results.attempted} run, {results.failed} failed")
        return 1 if results.failed else 0

    if args.demo or not args.calldata:
        demo()
        return 0

    data = bytes.fromhex(args.calldata.removeprefix("0x"))
    gas = intrinsic_gas(data, is_creation=args.creation)
    eff = effective_gas_price(int(args.base_fee_gwei * GWEI),
                             int(args.max_fee_gwei * GWEI),
                             int(args.max_priority_gwei * GWEI))
    print(f"calldata:        {len(data)} bytes "
          f"({data.count(0)} zero, {len(data) - data.count(0)} non-zero)")
    print(f"intrinsic gas:   {gas:,}")
    print(f"effective price: {eff / GWEI:g} gwei")
    print(f"expected cost:   {fmt_wei(tx_cost_wei(gas, eff))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
